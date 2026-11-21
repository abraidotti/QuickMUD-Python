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


class StringEditor(unittest.TestCase):
    def test_format_string(self):
        from charm.olc.strings import format_string

        self.assertEqual(format_string("hello.  there\n\r"), "Hello.  There \n\r")  # the trailing space stays
        self.assertEqual(format_string('a (b.) c "d." e'), 'A (b.)  C "d."  E\n\r')
        self.assertEqual(format_string("x... y"), "X...  Y\n\r")
        wrapped = format_string("word " * 30)
        self.assertTrue(all(len(line) <= 77 for line in wrapped.split("\n\r")))
        with log.capture() as lines:
            self.assertEqual(format_string("a" * 80)[:78], "A" + "a" * 74 + "-\n\r")  # a character is lost
        self.assertIn("No spaces", "".join(lines))

    def test_format_string_reads_before_its_buffer(self):
        from charm.olc.strings import format_string

        for text in ("", " leading", "\nx", ". x"):
            with self.subTest(text=text), self.assertRaises(CWouldCrash):
                format_string(text)

    def test_lines(self):
        from charm.olc.strings import first_arg, merc_getline, numlines, string_lineadd, string_linedel

        text = "one\n\rtwo\n\rthree\n\r"
        self.assertEqual(string_linedel(text, 2), "one\n\rthree\n\r")
        self.assertEqual(string_linedel(text, 9), text)
        self.assertEqual(string_lineadd(text, "new", 1), "new\n\r" + text)
        self.assertEqual(string_lineadd(text, "new", 4), text + "new\n\r")  # one past the last line
        self.assertEqual(string_lineadd(text, "new", 9), text)
        self.assertEqual(string_lineadd("", "new", 1), "new\n\r")
        self.assertEqual(numlines(text), " 1. one\n\r 2. two\n\r 3. three\n\r")
        self.assertEqual(merc_getline("no end"), ("", "no end"))
        self.assertEqual(merc_getline("a\nb"), ("b", "a"))
        self.assertEqual(first_arg("  (two words) rest", False), ("rest", "two words"))
        self.assertEqual(first_arg("%Pct% x", True), ("x", "pct"))

    def test_too_long_and_none(self):
        from charm.olc.strings import string_add, string_append
        from charm.net.descriptor import new_descriptor
        from charm.entities.things import new_char
        from charm.world.index import ExtraDescr

        ch = new_char(0)
        ch.desc = new_descriptor()
        ed = ExtraDescr("k", None)
        string_append(ch, (ed, "description"))
        self.assertEqual(ed.description, "")  # a NULL string is made empty
        ed.description = "x" * (C.MAX_STRING_LENGTH - 10)
        string_add(ch, "123456")
        self.assertIsNone(ch.desc.pString)  # "String too long, last line skipped." and out of the editor
        self.assertIn("String too long", ch.desc.outbuf)


class RoomEditor(unittest.TestCase):
    def setUp(self):
        from tests.test_commands import Commands

        self.case = Commands()
        self.case.setUp()
        self.game, self.ch = self.case.game, self.case.ch
        self.ch.pcdata.security = 9
        self.room = self.ch.in_room

    def tearDown(self):
        self.case.tearDown()

    def test_add_reset_slots(self):
        from charm.olc.olc import add_reset

        room = self.room
        room.resets = []
        a, b, c, d, e = (Reset(x, 0, 0, 0, 0) for x in "ABCDE")
        add_reset(room, a, 5)  # the first reset goes in whatever the slot
        add_reset(room, b, 1)  # slot 1: first
        add_reset(room, c, 0)  # 0: last
        add_reset(room, d, 2)  # slot 2
        add_reset(room, e, -3)  # negative: last
        self.assertEqual([r.command for r in room.resets], ["B", "D", "A", "C", "E"])

    def test_an_exit_to_nowhere_crashes(self):
        from charm.olc.act import change_exit
        from charm.olc.mem import new_exit

        self.room.exit[1] = new_exit()  # to_room None
        for line in ("door", "delete"):
            with self.subTest(line), self.assertRaises(CWouldCrash):
                change_exit(self.ch, line, 1)

    def test_removing_no_shop_crashes(self):
        from charm.olc.act import medit_shop

        self.ch.desc.pEdit = next(iter(self.game.index.mobs.values()))
        self.ch.desc.pEdit.shop = None
        with self.assertRaises(CWouldCrash):
            medit_shop(self.ch, "remove")
        medit_shop(self.ch, "assign")
        with self.assertRaises(CWouldCrash):
            medit_shop(self.ch, "type -1 food")  # before the array in the C, not its last slot

    def test_dice_are_cut_at_non_digits(self):
        from charm.olc.act import _dice_parts

        self.assertEqual(_dice_parts("2d6+10"), ("2", "6", "10"))
        self.assertEqual(_dice_parts("3 d 4 + 5x9"), ("3", "4", "5"))
        self.assertEqual(_dice_parts("d6"), ("", "6", ""))

    def test_resets_inside_nothing_crashes(self):
        from charm.olc.olc import do_resets

        self.room.area.security = 0
        with self.assertRaises(CWouldCrash):
            do_resets(self.ch, "1 obj 1 inside 99999")


class StringSpaceAndOdds(unittest.TestCase):
    def test_strings_are_kept_once(self):
        from charm.world.areafile.reader import Reader, StringSpace

        space = StringSpace()
        r = Reader("one~ two~ one~ ~ three\n")
        r.space = space
        for _ in range(4):
            r.read_string()
        r.read_string_eol()
        self.assertEqual((space.count, space.used), (3, (8 + 3 + 1) * 2 + (8 + 5 + 1)))  # "" and a repeat take nothing

    def test_the_space_runs_out(self):
        from charm.world.areafile.reader import MAX_STRING, AreaParseError, Reader, StringSpace

        space = StringSpace()
        space.used = MAX_STRING - C.MAX_STRING_LENGTH - 8  # just room for one more check
        r = Reader("a~ b~\n")
        r.space = space
        r.read_string()
        with self.assertRaises(AreaParseError) as e:
            r.read_string()
        self.assertIn("Fread_string: MAX_STRING 1413120 exceeded.", str(e.exception))

    def test_slot_lookup(self):
        from charm.data.skills import SKILL_TABLE
        from charm.systems.magic import slot_lookup

        sn = next(k for k, s in enumerate(SKILL_TABLE) if s.slot > 0)
        self.assertEqual(slot_lookup(SKILL_TABLE[sn].slot), sn)
        self.assertEqual(slot_lookup(0), -1)
        self.assertEqual(slot_lookup(99999), -1)
        with log.capture(), self.assertRaises(SystemExit):
            slot_lookup(99999, booting=True)

    def test_a_dazed_exotic_weapon_reads_before_the_table(self):
        from charm.entities.handler import get_skill
        from charm.entities.things import new_char

        ch = new_char(0)
        ch.daze = 1
        with self.assertRaises(CWouldCrash):
            get_skill(ch, -1)

    def test_improving_an_exotic_weapon_reads_before_the_table(self):
        from charm.entities.things import new_char, new_pcdata
        from charm.systems.skills import check_improve

        ch = new_char(0)
        ch.pcdata = new_pcdata()
        with self.assertRaises(CWouldCrash):  # not the last skill, as Python's [-1] would read
            check_improve(ch, -1, False, 2)  # latent: no caller passes -1 (#104)


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
