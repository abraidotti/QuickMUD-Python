"""The game loop on real sockets, and the pieces around it: qmconfig.rc, one_argument, the pulse stats.

What comm.c's input and output functions do, byte for byte, is compared with the C game's saved results by
quickmud_tools port io (tools/tests/data/iocases.txt). These check the loop itself: a connection gets the greeting, a
shutdown signal says goodbye and closes it, and a line of input reaches nanny. Until cut-over, port greeting and port
login compared the greeting and logging in with the C game live (the c-final tag).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from quickmud.commands.interp import one_argument
from quickmud.core import log
from quickmud.entities.boot import boot_db
from quickmud.net import server
from quickmud.net.config import Config, qmconfig_read
from tests.test_entities import AREA

GREETING_AREA = AREA.replace("#MOBILES", "#HELPS\n-1 greeting~\n.  Hello, test!\n~\n0 $~\n\n#MOBILES", 1)


def boot():
    text = GREETING_AREA.replace("{trigger}", "").replace("{progs}", "")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "area.lst").write_text("t.are\n$\n")
        Path(d, "music.txt").write_text("#\n")  # load_songs crashes the C without one
        Path(d, "t.are").write_text(text)
        with log.capture():
            game = boot_db(Path(d), 1763400000, {"QUICKMUD_SEED": "1"})
    game.config = Config()
    return game


def recv_until(sock, marker: bytes, limit: float = 10.0) -> bytes:
    sock.settimeout(limit)
    data = b""
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


class Loop(unittest.TestCase):
    def run_loop(self, client):
        """Run game_loop here (it sets signal handlers, so it needs the main thread) and client in a thread."""
        game = boot()
        with log.capture():
            control = server.init_socket(0, "127.0.0.1")
        port = control.getsockname()[1]
        results = {}

        def talk():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                    client(game, s, results)
            except Exception as e:  # noqa: BLE001 (reported by the test)
                results["error"] = e
            finally:
                if not game.shutdown_signal:  # whatever happened, the loop stops: a test can't hang the suite
                    game.shutdown_signal = 15

        t = threading.Thread(target=talk)
        t.start()
        try:
            with log.capture() as lines:
                try:
                    server.game_loop(game, control)
                finally:
                    for d in list(game.descriptor_list):
                        d.sock.close()
        finally:
            control.close()
            t.join(10)
        self.assertNotIn("error", results)
        return game, results, lines

    def test_greeting_then_shutdown(self):
        def client(game, s, results):
            results["greeting"] = recv_until(s, b"Hello, test!")
            game.shutdown_signal = 15
            results["goodbye"] = recv_until(s, b"shutting down.")

        game, results, lines = self.run_loop(client)
        self.assertEqual(results["greeting"], b"\n\r  Hello, test!\n\r")  # the leading '.' is dropped
        self.assertEqual(results["goodbye"], b"\n\rThe game is shutting down.\n\r")
        self.assertIn("Caught signal 15, shutting down.", lines)
        self.assertEqual(game.descriptor_list, [])
        self.assertTrue(game.merc_down)

    def test_a_name_goes_to_nanny(self):
        def client(game, s, results):
            recv_until(s, b"Hello, test!")
            s.sendall(b"bob\n")
            results["question"] = recv_until(s, b"(Y/N)? ")

        _, results, _ = self.run_loop(client)
        self.assertTrue(results["question"].endswith(b"Did I get that right, Bob (Y/N)? "))


class PulseStats(unittest.TestCase):
    def test_logs_each_minute_and_the_run(self):
        stats = server.PulseStats(every=0)
        with log.capture() as lines:
            stats.add(0.002)
        self.assertEqual(lines, ["Pulse work: median 2.00 ms, p95 2.00 ms, max 2.00 ms, mean 2.00 ms over 1 pulses"])
        stats.every = 3600
        for ms in range(1, 101):  # 1 to 100 ms, after the 2 above
            stats.add(ms / 1000)
        with log.capture() as lines:
            stats.finish()
        # 101 pulses: the median is the 51st, the 95th percentile the 96th (nearest rank on index 0.95 * 100)
        self.assertEqual(lines, ["Pulse work over the run: median 50.00 ms, p95 95.00 ms, max 100.00 ms, "
                                 "mean 50.02 ms over 101 pulses"])


class QmConfig(unittest.TestCase):
    def test_reads_keys_skips_comments_and_logs_unknowns(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "qmconfig.rc")
            path.write_text("# a comment\nAnsiprompt 1\nansicolor 1\nBogus 3\nTelnetga 0\nEND\n")
            with log.capture() as lines:
                config = qmconfig_read(path)
        self.assertEqual((config.ansiprompt, config.ansicolor, config.telnetga), (1, 1, 0))
        self.assertIn("qmconfig_read: no match for Bogus!", lines)

    def test_missing_file_keeps_the_defaults(self):
        with log.capture() as lines:
            config = qmconfig_read(Path(tempfile.gettempdir(), "no-such-qmconfig.rc"))
        self.assertEqual(config, Config())
        self.assertIn("qmconfig.rc not found. Using compiled-in defaults.", lines)


class OneArgument(unittest.TestCase):
    def test_words_quotes_and_case(self):
        self.assertEqual(one_argument("  Get SWORD  "), ("SWORD  ", "get"))
        self.assertEqual(one_argument("'big sword' now"), ("now", "big sword"))
        self.assertEqual(one_argument('"unclosed'), ("", "unclosed"))
        self.assertEqual(one_argument(""), ("", ""))


class Copyover(unittest.TestCase):
    """copyover_recover, which a scenario can't reach (it needs a real exec): connections picked up from
    copyover.data, over socketpairs, in the stock world with the Shemp fixture."""

    def setUp(self):
        import shutil

        from quickmud.entities import game as game_module

        repo = Path(__file__).resolve().parents[2]
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        shutil.copytree(repo / "area", root / "area")
        (root / "player").mkdir()
        shutil.copy(repo / "tools" / "fixtures" / "player" / "Shemp", root / "player" / "Shemp")
        with log.capture():
            self.game = boot_db(root / "area", 1763400000, {"QUICKMUD_SEED": "1"})
        self.game.config = Config()
        self.saved, game_module.current = game_module.current, self.game
        self.area = root / "area"

    def tearDown(self):
        from quickmud.entities import game as game_module

        game_module.current = self.saved
        self.tmp.cleanup()

    def test_recover_a_player_and_drop_the_lost(self):
        from quickmud.commands.copyover import COPYOVER_FILE, copyover_recover
        from quickmud.data import constants as C

        game_end, ours = socket.socketpair()
        lost_end, lost_ours = socket.socketpair()
        fd, lost = game_end.detach(), lost_end.detach()
        ours.settimeout(5)  # a mutant that sends nothing fails, rather than hanging
        lost_ours.settimeout(5)
        (self.area / COPYOVER_FILE).write_text(f"{fd} Shemp somehost\n{lost} Nobody otherhost\n-1\n")
        with log.capture() as lines:
            copyover_recover(self.game)
        self.assertFalse((self.area / COPYOVER_FILE).exists())  # removed before reading on
        self.assertIn("Copyover recovery initiated", "".join(lines))
        d = next(d for d in self.game.descriptor_list if d.character is not None)
        self.assertEqual((d.connected, d.host, d.character.name), (C.CON_PLAYING, "somehost", "Shemp"))
        # (assertIn would print the lists, whose dataclass reprs never end)
        self.assertTrue(any(c is d.character for c in self.game.char_list), "not in char_list")
        self.assertTrue(any(c is d.character for c in d.character.in_room.people), "not in the room")
        got = ours.recv(65536).decode("latin-1")
        self.assertIn("Restoring from copyover...", got)
        self.assertIn("Copyover recovery complete.", got)
        lost_got = lost_ours.recv(65536).decode("latin-1")
        self.assertIn("Somehow, your character was lost in the copyover. Sorry.", lost_got)
        self.assertEqual(len([x for x in self.game.descriptor_list if not x.closed]), 1)
        for s in (ours, lost_ours, d.sock):
            s.close()

    def test_no_copyover_file_stops_the_game(self):
        from quickmud.commands.copyover import copyover_recover

        with log.capture() as lines, self.assertRaises(SystemExit):
            copyover_recover(self.game)
        self.assertIn("Copyover file not found. Exitting.", "".join(lines))

    def test_copyover_file_not_writeable(self):
        from quickmud.commands.copyover import do_copyover
        from quickmud.entities.things import new_char

        self.game.area_dir = self.area / "missing"
        ch = new_char(0)
        ch.desc = None
        sent = []
        import quickmud.commands.copyover as co

        real, co.send_to_char = co.send_to_char, lambda text, c: sent.append(text)
        try:
            with log.capture():
                do_copyover(ch, "")
        finally:
            co.send_to_char = real
        self.assertEqual(sent, ["Copyover file not writeable, aborted.\n\r"])


if __name__ == "__main__":
    unittest.main()
