"""The interpreter and the spike's commands, offline, on the small test area from test_entities.

What each command prints, byte for byte, is compared with the C game by charm_tools port commands (#32). These
pin down the pieces around it: the C's string helpers, number_argument, the command table's prefix order, what an
unported command does, and the lines that differ from the C on purpose.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from charm.commands import interp
from charm.commands.interp import interpret, number_argument
from charm.core import log
from charm.core.errors import NotPorted
from charm.core.strings import atoi, lower, str_cmp, str_prefix, str_suffix, upper
from charm.persist.player import capitalize
from charm.data import constants as C
from charm.data.commands import CMD_TABLE
from charm.entities import game as game_module
from charm.entities.boot import boot_db
from charm.entities.handler import char_to_room
from charm.entities.things import new_char, new_pcdata
from charm.net.descriptor import new_descriptor
from tests.test_entities import AREA


class Strings(unittest.TestCase):
    def test_case_is_ascii_only(self):
        self.assertTrue(str_cmp("HeLLo", "hello"))
        self.assertFalse(str_cmp("\xc9", "\xe9"))  # LOWER leaves bytes over 127 alone
        self.assertEqual(upper("stra\xdfe \xff"), "STRA\xdfE \xff")  # Python's .upper() gives "STRASSE Ÿ"
        self.assertEqual(lower("\xc9COLE"), "\xc9cole")
        self.assertEqual(capitalize("\xe9MILE"), "\xe9mile")  # db.c capitalize: UPPER leaves \xe9 alone
        self.assertTrue(str_prefix("", "anything"))
        self.assertTrue(str_prefix("NOR", "north"))
        self.assertFalse(str_prefix("northern", "north"))
        self.assertTrue(str_suffix("%C", "<%h %c"))
        self.assertFalse(str_suffix("long suffix", "%c"))

    def test_atoi(self):
        for text, n in (("", 0), ("+", 0), ("-", 0), ("  42x", 42), ("-7", -7), ("x1", 0), ("+3", 3)):
            self.assertEqual(atoi(text), n, text)

    def test_number_argument(self):
        self.assertEqual(number_argument("2.sword"), (2, "sword"))
        self.assertEqual(number_argument("sword"), (1, "sword"))
        self.assertEqual(number_argument("x.sword"), (0, "sword"))  # atoi("x")
        self.assertEqual(number_argument("1.2.sword"), (1, "2.sword"))  # the first dot only


class Table(unittest.TestCase):
    def test_order_decides_prefixes(self):
        names = [c.name for c in CMD_TABLE]
        self.assertEqual(names[:6], ["north", "east", "south", "west", "up", "down"])

        def first(prefix):
            return next(c.name for c in CMD_TABLE if c.name.startswith(prefix))
        self.assertEqual(first("sc"), "scan")  # before score: port commands found this
        self.assertEqual(first("l"), "look")
        self.assertNotIn("", names)  # the closing row isn't a command


def boot_game():
    text = AREA.replace("{trigger}", "").replace("{progs}", "")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "area.lst").write_text("t.are\n$\n")
        Path(d, "music.txt").write_text("#\n")  # load_songs crashes the C without one
        Path(d, "t.are").write_text(text)
        with log.capture():
            game = boot_db(Path(d), 1763400000, {"CHARM_SEED": "1"})
    return game


class Commands(unittest.TestCase):
    def setUp(self):
        self.game = boot_game()
        self.saved, game_module.current = game_module.current, self.game
        ch = new_char(self.game.current_time)
        ch.name, ch.pcdata, ch.level, ch.position = "Tester", new_pcdata(), 5, C.POS_STANDING
        ch.race = 1  # human
        ch.max_hit = ch.hit = 20
        ch.move = ch.max_move = 100
        ch.comm = C.COMM_PROMPT | C.COMM_COMBINE
        d = new_descriptor()
        d.connected, d.character, d.game, d.fcommand = C.CON_PLAYING, ch, self.game, True
        ch.desc = d
        self.game.char_list.insert(0, ch)
        char_to_room(ch, self.game.index.get_room_index(30001))
        self.ch, self.d = ch, d

    def tearDown(self):
        game_module.current = self.saved

    def say(self, line: str) -> str:
        self.d.outbuf = ""
        interpret(self.ch, line)
        return self.d.outbuf

    def test_huh_and_spaces(self):
        self.assertEqual(self.say("xyzzy"), "Huh?\n\r")
        self.assertEqual(self.say("   "), "")

    def test_an_unported_command_stops_the_game(self):
        # Every command is ported now (P5 PR 8), so take one away for the test.
        interp.command_function("do_score")  # fill the table first
        with mock.patch.dict(interp._COMMANDS):
            del interp._COMMANDS["do_score"]
            with self.assertRaises(NotPorted) as e:
                self.say("score")
        self.assertIn("do_score", str(e.exception))

    def test_every_command_is_ported(self):
        missing = sorted({c.do_fun for c in CMD_TABLE} - set(interp._commands()))
        self.assertEqual(missing, [])

    def test_every_ported_name_is_in_the_table(self):
        table = {c.do_fun for c in CMD_TABLE}
        self.assertTrue(set(interp._commands()) <= table)

    def test_look_and_walk_into_the_dark(self):
        out = self.say("look")
        self.assertIn("Light\n\r  A lit room.\n\r", out)
        self.assertIn("A sack lies here.\n\r", out)
        out = self.say("w")
        self.assertTrue(out.startswith("It is pitch black ... \n\r"), out)  # 30000 is dark
        self.assertEqual(self.ch.in_room.vnum, 30000)
        self.assertEqual(self.ch.wait, 1)  # WAIT_STATE (ch, 1)
        self.assertEqual(self.say("n"), "Alas, you cannot go that way.\n\r")

    def test_too_exhausted(self):
        self.ch.move = 0
        self.assertEqual(self.say("w"), "You are too exhausted.\n\r")
        self.assertEqual(self.ch.in_room.vnum, 30001)

    def test_title_and_prompt(self):
        self.assertEqual(self.say("title the Brave{"), "Ok.\n\r")
        self.assertEqual(self.ch.pcdata.title, " the Brave")
        self.assertEqual(self.say("title " + "a" * 60), "Ok.\n\r")
        self.assertEqual(self.ch.pcdata.title, " " + "a" * 45)
        self.assertEqual(self.say("prompt <%h %c"), "Prompt set to <%h %c\n\r")  # ends in %c: no space added
        self.assertEqual(self.say("prompt <%h>"), "Prompt set to <%h> \n\r")
        self.assertEqual(self.say("prompt"), "You will no longer see prompts.\n\r")
        self.assertFalse(self.ch.comm & C.COMM_PROMPT)

    def test_save_says_charm_and_lags(self):
        with mock.patch("charm.persist.player.save_char_obj") as save:
            self.assertEqual(self.say("save"), "Saving. Remember that Charm has automatic saving now.\n\r")
        save.assert_called_once()
        self.assertEqual(self.ch.wait, 4 * C.PULSE_VIOLENCE)

    def test_a_typo_can_be_a_social(self):
        self.game.index.socials = [type("Social", (), {"name": "smile", "messages": [
            "You smile.", "$n smiles.", None, None, None, None, None, None]})()]
        self.assertEqual(self.say("smi"), "You smile.\n\r")


class Money(unittest.TestCase):
    """handler.c's create_money: the five coin objects of limbo.are, and zero money mended to 1 gold and 1 silver
    (drop and the rest never ask for zero, so no scenario reaches it)."""

    @classmethod
    def setUpClass(cls):
        with log.capture():
            cls.game = boot_db(Path(__file__).resolve().parents[2] / "area", 1763400000, {"CHARM_SEED": "1"})

    def test_each_shape(self):
        from charm.entities.handler import create_money

        def made(gold, silver):
            o = create_money(self.game, gold, silver)
            return o.index.vnum, o.short_descr, o.value[:2], o.cost, o.weight

        self.assertEqual(made(0, 1), (C.OBJ_VNUM_SILVER_ONE, "a silver coin", [1, 0], 0, 10))  # limbo.are's weight
        self.assertEqual(made(1, 0), (C.OBJ_VNUM_GOLD_ONE, "a gold coin", [0, 1], 0, 10))
        self.assertEqual(made(12, 0), (C.OBJ_VNUM_GOLD_SOME, "12 gold coins", [0, 12], 12, 2))
        self.assertEqual(made(0, 45), (C.OBJ_VNUM_SILVER_SOME, "45 silver coins", [45, 0], 45, 2))
        self.assertEqual(made(7, 41), (C.OBJ_VNUM_COINS, "41 silver coins and 7 gold coins", [41, 7], 741, 3))

    def test_zero_or_negative_money_is_mended_and_logged(self):
        from charm.entities.handler import create_money

        with mock.patch.object(log, "log_string") as logged:
            o = create_money(self.game, 0, 0)
        logged.assert_called_once_with("[*****] BUG: Create_money: zero or negative money.")
        self.assertEqual((o.index.vnum, o.value[:2]), (C.OBJ_VNUM_COINS, [1, 1]))
        with mock.patch.object(log, "log_string") as logged:
            create_money(self.game, -5, 3)
        logged.assert_called_once_with("[*****] BUG: Create_money: zero or negative money.")


class Buffers(unittest.TestCase):
    """recycle.c's BUFFER, which keeps tells for replay: it grows through buf_size, and holds 16382 characters at most."""

    def test_grows_then_overflows_and_stays_overflowed(self):
        from charm.entities.things import BUFFER_OVERFLOW, add_buf, clear_buf, new_buf

        buf = new_buf()
        self.assertEqual(buf.size, 1024)
        self.assertTrue(add_buf(buf, "x" * 1024))  # 1025 bytes with the NUL: the next size up
        self.assertEqual(buf.size, 2048)
        self.assertTrue(add_buf(buf, "x" * (16382 - 1024)))  # it grows while the length with the NUL is >= the size
        self.assertEqual(buf.size, 16384)
        with mock.patch.object(log, "log_string") as logged:
            self.assertFalse(add_buf(buf, "x"))
        logged.assert_called_once_with("[*****] BUG: buffer overflow past size 16384")
        self.assertEqual((buf.size, buf.state, len(buf.string)), (16384, BUFFER_OVERFLOW, 16382))
        self.assertFalse(add_buf(buf, ""))  # an overflowed buffer takes nothing more
        clear_buf(buf)
        self.assertTrue(add_buf(buf, "again"))
        self.assertEqual(buf.string, "again")


class Updates(unittest.TestCase):
    """CHARM_UPDATES's names, read as update.c's update_runs reads them (#74)."""

    def test_names_pick_the_updates(self):
        from charm.systems.update import UPDATES, updates_named

        self.assertEqual(updates_named(None), frozenset(UPDATES))
        self.assertEqual(updates_named("all"), frozenset(UPDATES))
        self.assertEqual(updates_named("area"), {"area"})
        self.assertEqual(updates_named("Area,,VIOLENCE"), {"area", "violence"})
        with log.capture():
            self.assertEqual(updates_named("area,nonsense"), {"area"})

    def test_every_update_is_ported(self):
        # P4 PR 6 (#74): nothing is left for a scenario's @updates to stop at, or for boot to log as not running.
        from charm.systems.update import NOT_RUNNING, PORTED, UPDATES

        self.assertEqual(PORTED, frozenset(UPDATES))
        self.assertEqual(NOT_RUNNING, ())
