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
from charm.core.strings import atoi, str_cmp, str_prefix, str_suffix
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
        with self.assertRaises(NotPorted) as e:
            self.say("sc")
        self.assertIn("do_scan", str(e.exception))

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
