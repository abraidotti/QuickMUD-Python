"""The game loop on real sockets, and the pieces around it: qmconfig.rc, one_argument, the pulse stats.

What comm.c's input and output functions do, byte for byte, is compared with the C game by charm_tools port io
(tools/oracle/iocases.txt), and the live greeting by port greeting. These check the loop itself: a connection gets
the greeting, a shutdown signal says goodbye and closes it, and a line of input reaches nanny. Logging in, byte for
byte, is charm_tools port login's.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from charm.commands.interp import one_argument
from charm.core import log
from charm.entities.boot import boot_db
from charm.net import server
from charm.net.config import Config, qmconfig_read
from tests.test_entities import AREA

GREETING_AREA = AREA.replace("#MOBILES", "#HELPS\n-1 greeting~\n.  Hello, test!\n~\n0 $~\n\n#MOBILES", 1)


def boot():
    text = GREETING_AREA.replace("{trigger}", "").replace("{progs}", "")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "area.lst").write_text("t.are\n$\n")
        Path(d, "t.are").write_text(text)
        with log.capture():
            game = boot_db(Path(d), 1763400000, {"CHARM_SEED": "1"})
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


if __name__ == "__main__":
    unittest.main()
