"""The online builder, offline: bit.c's flag helpers and the parts of olc_save.c no scenario can reach.

What asave writes is compared with the C game byte for byte by charm_tools port asave (every stock area) and the
asave-* scenarios (a fixture area in OLC's format). These pin down fix_string's quirks, flag_value, and the paths
where the C would crash or can't open a file.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import io
import tempfile
import unittest
from pathlib import Path

from charm.core import log
from charm.core.errors import CWouldCrash
from charm.data import constants as C
from charm.data import flags as F
from charm.entities import game as game_module
from charm.olc import bits, save
from charm.world.index import Reset
from tests.test_commands import boot_game


class Bits(unittest.TestCase):
    def test_stat_or_flags(self):
        self.assertTrue(bits.is_stat(F.SECTOR_FLAGS))
        self.assertFalse(bits.is_stat(F.ROOM_FLAGS))
        self.assertFalse(bits.is_stat(F.PLR_FLAGS))  # not in flag_stat_table at all
        self.assertFalse(bits.is_stat(list(F.SECTOR_FLAGS)))  # by identity, as the C compares pointers

    def test_flag_value(self):
        self.assertEqual(bits.flag_value(F.ROOM_FLAGS, "dark indoors"), C.ROOM_DARK | C.ROOM_INDOORS)
        self.assertEqual(bits.flag_value(F.ROOM_FLAGS, "dark nonsense"), C.ROOM_DARK)
        self.assertEqual(bits.flag_value(F.ROOM_FLAGS, "nonsense"), C.NO_FLAG)
        self.assertEqual(bits.flag_value(F.ROOM_FLAGS, ""), C.NO_FLAG)
        self.assertEqual(bits.flag_value(F.SECTOR_FLAGS, "forest"), C.SECT_FOREST)  # a stat: the whole argument
        self.assertEqual(bits.flag_value(F.SECTOR_FLAGS, "forest city"), C.NO_FLAG)

    def test_flag_string(self):
        self.assertEqual(bits.flag_string(F.ROOM_FLAGS, C.ROOM_DARK | C.ROOM_INDOORS), "dark indoors")
        self.assertEqual(bits.flag_string(F.ROOM_FLAGS, 0), "none")
        self.assertEqual(bits.flag_string(F.SECTOR_FLAGS, C.SECT_FOREST), "forest")
        self.assertEqual(bits.flag_string(F.SECTOR_FLAGS, 99), "none")
        self.assertEqual(bits.flag_string(F.AREA_FLAGS, 0), "none")  # "none" is bit 0, which equals 0
        self.assertEqual(bits.flag_string(F.WEAR_LOC_STRINGS, -1), "in the inventory")


class FixString(unittest.TestCase):
    def test_strips_returns_and_tildes(self):
        self.assertEqual(save.fix_string("one\n\rtwo\n\r"), "one\ntwo\n")
        self.assertEqual(save.fix_string("a~b"), "ab")
        self.assertIsNone(save.fix_string(None))
        self.assertEqual(save._s(save.fix_string(None)), "(null)")

    def test_the_character_after_a_skip_stays(self):
        self.assertEqual(save.fix_string("a\r\rb"), "a\rb")
        self.assertEqual(save.fix_string("a~~b"), "a~b")
        self.assertEqual(save.fix_string("a\r~b"), "a~b")
        self.assertEqual(save.fix_string("ab~"), "ab")

    def test_its_buffer_overflows(self):
        self.assertEqual(len(save.fix_string("x" * (save.STRFIX - 1))), save.STRFIX - 1)
        with self.assertRaises(CWouldCrash):
            save.fix_string("x" * save.STRFIX)

    def test_fwrite_flag(self):
        self.assertEqual(save.fwrite_flag(0), "0")
        self.assertEqual(save.fwrite_flag(1 | (1 << 25) | (1 << 26) | (1 << 31)), "AZaf")
        self.assertEqual(save.fwrite_flag(-1), "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef")
        self.assertEqual(save.fwrite_flag(1 << 32), "")  # past the 32 bits it looks at: nothing (the C's long)


class Strings(unittest.TestCase):
    def test_string_replace(self):
        from charm.olc.strings import string_replace

        self.assertEqual(string_replace("Planner Delver", "Del", ""), "Planner ver")  # strstr: inside a word
        self.assertEqual(string_replace("a b a", "a", "c"), "c b a")  # the first only
        self.assertEqual(string_replace("abc", "x", "y"), "abc")
        with self.assertRaises(CWouldCrash):
            string_replace("x" * C.MAX_STRING_LENGTH, "x", "")

    def test_unpad_and_proper(self):
        from charm.olc.strings import string_proper, string_unpad

        self.assertEqual(string_unpad("  a b  "), "a b")
        self.assertEqual(string_unpad("\ta "), "\ta")  # spaces only
        self.assertEqual(string_unpad("   "), "")
        self.assertEqual(string_proper("ver ver  planner"), "Ver Ver  Planner")
        self.assertEqual(string_proper(""), "")


class Saving(unittest.TestCase):
    def setUp(self):
        self.game = boot_game()
        self.saved, game_module.current = game_module.current, self.game
        self.dir = tempfile.TemporaryDirectory()
        self.game.area_dir = self.dir.name
        self.area = self.game.index.areas[0]

    def tearDown(self):
        game_module.current = self.saved
        self.dir.cleanup()

    def resets(self, *resets) -> str:
        room = next(r for r in self.game.index.rooms.values() if r.area is self.area)
        room.resets = list(resets)
        out = io.StringIO()
        with log.capture() as lines:
            save.save_resets(out, self.area)
        return out.getvalue(), lines

    def test_resets_with_no_mob_and_bad_commands(self):
        obj = next(iter(self.game.index.objs))
        text, lines = self.resets(Reset("G", obj, 0, 0, 0), Reset("D", 0, 0, 0, 0), Reset("X", 0, 0, 0, 0))
        self.assertIn("is given to !NO_MOB!\n", text)
        self.assertIn("Save_resets: !NO_MOB! in [t.are]", "".join(lines))
        self.assertIn("Save_resets: bad command X.", "".join(lines))

    def test_resets_to_nothing_crash(self):
        for rs in (Reset("M", 99999, 0, 0, 0), Reset("O", 99999, 0, 0, 0), Reset("R", 99999, 0, 0, 0)):
            with self.subTest(rs.command), self.assertRaises(CWouldCrash):
                self.resets(rs)

    def test_an_invalid_affect_where(self):
        obj = next(iter(self.game.index.objs.values()))
        obj.affected = [save_affect(where=9)]
        out = io.StringIO()
        with log.capture() as lines:
            save.save_object(out, obj)
        self.assertIn("F\n1 2 C\n", out.getvalue())  # the where letter is left out
        self.assertIn("olc_save: Invalid Affect->where", "".join(lines))

    def test_a_file_that_wont_open(self):
        self.game.area_dir = str(Path(self.dir.name) / "missing")
        with log.capture() as lines:
            save.save_area_list(self.game)
        self.assertIn("Save_area_list: fopen", "".join(lines))
        with log.capture(), self.assertRaises(CWouldCrash):
            save.save_area(self.area)

    def test_changed_help_files(self):
        ha = save_help_area(self.game)
        save.do_asave(None, "world")  # with no character: saves the changed help file, and says nothing
        text = (Path(self.dir.name) / "h.hlp").read_text(encoding="latin-1")
        self.assertEqual(text, "#HELPS\n0 TEST~\nSome text.\n~\n\n-1 $~\n\n#$\n")
        self.assertFalse(ha.changed)

    def test_changed_areas_from_no_character(self):
        self.area.area_flags |= C.AREA_CHANGED
        with log.capture() as lines:
            save.do_asave(None, "changed")
        text = "".join(lines)
        self.assertIn("Saved zones:", text)
        self.assertIn("%24s - '%s'" % (self.area.name, self.area.file_name), text)
        self.assertNotIn("None.", text)
        self.assertFalse(self.area.area_flags & C.AREA_CHANGED)
        with log.capture() as lines:
            save.do_asave(None, "changed")
        self.assertIn("None.", "".join(lines))


def save_affect(where):
    from charm.world.index import Affect

    return Affect(where, -1, 1, -1, 1, 2, 4)


def save_help_area(game):
    from charm.world.index import Help, HelpArea

    ha = HelpArea("h.hlp", None, [Help(0, "TEST", "Some text.\n\r")], changed=True)
    game.index.had_list.insert(0, ha)
    return ha


if __name__ == "__main__":
    unittest.main()
