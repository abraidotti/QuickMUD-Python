"""The old area formats: the branches no golden can reach, checked against the C's text.

old-format.scn plays tools/fixtures/files/oldformat.are on both games, and explore parity's cases compare its boot
log. What neither can reach is the old-format branches of create_mobile, create_object and reset_room: the boot
converts every old-format prototype first, in the C as here. So these make prototypes old by hand, stub the random
draws (number_range returns its top, dice its maximum, number_fuzzy adds 1), and check every value and the order of
the draws against db.c.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from quickmud.core import log
from quickmud.core.errors import CWouldCrash
from quickmud.data import constants as C
from quickmud.data.skills import SKILL_TABLE
from quickmud.entities import create, oldformat, resets
from quickmud.entities.boot import boot_db
from quickmud.entities.handler import extract_char
from quickmud.world.areafile.world import load_world
from quickmud.world.index import build_index

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tools" / "fixtures" / "files" / "oldformat.are"


def boot_fixture():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "area.lst").write_text("oldformat.are\n$\n")
        Path(d, "music.txt").write_text("#\n")
        Path(d, "oldformat.are").write_bytes(FIXTURE.read_bytes())
        with log.capture() as lines:
            game = boot_db(Path(d), 1763400000, {"QUICKMUD_SEED": "1"})
        world = load_world(Path(d))
    return game, world, lines


class Draws:
    """Stubs for the random draws, recording each call in order."""

    def __init__(self):
        self.calls = []

    def number_range(self, a, b):
        self.calls.append(("range", a, b))
        return b

    def dice(self, n, s):
        self.calls.append(("dice", n, s))
        return max(0, n) * s

    def number_fuzzy(self, x):
        self.calls.append(("fuzzy", x))
        return x + 1

    def patch(self, module, *names):
        return [mock.patch.object(module, n, getattr(self, n)) for n in names]


class Boot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game, cls.world, cls.lines = boot_fixture()

    def test_every_prototype_is_new_format_after_the_boot(self):
        self.assertTrue(all(p.new_format for p in self.game.index.mobs.values()))
        self.assertTrue(all(p.new_format for p in self.game.index.objs.values()))
        t = self.game.top
        self.assertEqual((t.mobs, t.mobs_new, t.objects, t.objects_new), (5, 5, 15, 15))

    def test_the_boot_logs_what_the_c_logs(self):
        # loaded alone, the first 'O' reset has no mob before it (old-format.scn loads it first for the same line)
        bugs = [x for x in self.lines if x.startswith("[*****]")]
        self.assertEqual(bugs, ["[*****] BUG: Convert_objects: 'O': No mob reset yet.",
                                "[*****] BUG: Convert_objects: 'P': bad vnum 31098.",
                                "[*****] BUG: Obj_convert: vnum 32 bad type.",
                                "[*****] BUG: Reset_room: 'P': bad vnum 31098."])

    def test_the_index_needs_the_old_format_builders(self):
        with self.assertRaisesRegex(ValueError, "old-format"):
            build_index(self.world)

    def test_a_negative_level_divides_by_zero(self):
        # convert_object: UMIN (level / 4 + 1, 5) is 0 for levels -4 to -7, and the C divides by it (SIGFPE)
        p = replace(self.game.index.objs[31000], new_format=False, level=-5, value=[0, 0, 0, 3, 0])
        with self.assertRaises(CWouldCrash):
            oldformat.convert_object(p, replace(self.game.top))
        # convert_mobile: the damage dice's number is 0 for levels -5 to -9 (level * 7 / 4 / 8 + 1)
        m = replace(self.game.index.mobs[31000], new_format=False, level=-6)
        with self.assertRaises(CWouldCrash):
            oldformat.convert_mobile(m)

    def test_convert_object_skips_what_is_new_or_missing(self):
        top = replace(self.game.top)
        oldformat.convert_object(None, top)
        oldformat.convert_object(self.game.index.objs[31000], top)
        self.assertEqual(top.objects_new, self.game.top.objects_new)


class OldFormatBranches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game, _, _ = boot_fixture()

    def old_mob(self, **fields):
        return replace(self.game.index.mobs[31000], new_format=False, wealth=0, count=0, **fields)

    def old_obj(self, vnum, **fields):
        return replace(self.game.index.objs[vnum], new_format=False, count=0, affected=[], **fields)

    def test_create_mobile(self):
        p = self.old_mob(level=10, hitroll=3, start_pos=C.POS_RESTING, material="none", size=C.SIZE_LARGE)
        d = Draws()
        draws, rolls = d.patch(create, "number_range", "dice")
        with draws, rolls:
            mob = create.create_mobile(self.game, p)
        self.assertEqual(d.calls, [("range", 25, 100), ("dice", 10, 10), ("range", 1, 3)])
        self.assertEqual((mob.max_hit, mob.hit), (162, 162))  # (10 * 8 + 100) * .9
        self.assertEqual((mob.max_mana, mob.mana), (200, 200))  # 100 + dice (10, 10)
        self.assertEqual(mob.dam_type, 11)  # 3: pierce
        self.assertEqual(mob.armor, [38, 38, 38, 69])  # interpolate (10, 100, -100), and (10, 100, 0)
        self.assertEqual(mob.perm_stat, [13] * C.MAX_STATS)  # 11 + level / 4, with no class or size bonus
        self.assertEqual((mob.level, mob.hitroll, mob.damroll), (10, 3, 0))
        self.assertEqual((mob.size, mob.material), (C.SIZE_MEDIUM, ""))  # not the prototype's
        self.assertEqual(mob.position, C.POS_RESTING)
        self.assertEqual((mob.race, mob.off_flags, mob.form), (p.race, p.off_flags, p.form))
        self.assertEqual(mob.affected, [])  # the spell affects are the new format's
        self.assertIs(self.game.char_list[0], mob)
        self.assertEqual(p.count, 1)

    def create(self, p, level):
        d = Draws()
        with d.patch(create, "number_fuzzy")[0]:
            obj = create.create_object(self.game, p, level)
        return obj, [c[1] for c in d.calls]

    def test_create_object_weapon(self):
        obj, fuzz = self.create(self.old_obj(31000, cost=7), 12)
        self.assertEqual(fuzz, [10, 12, 12, 5, 6, 15, 16])  # cost, left to right; then each value fuzzed twice
        self.assertEqual(obj.level, 12)
        self.assertEqual(obj.cost, 11 * 13 * 13)
        self.assertEqual(obj.value[1:3], [7, 17])  # fuzzy (fuzzy (12 / 4 + 2)), fuzzy (fuzzy (3 * 12 / 4 + 6))

    def test_create_object_armour(self):
        obj, fuzz = self.create(self.old_obj(31001), 12)
        self.assertEqual(fuzz, [10, 12, 12, 5, 5, 5])
        self.assertEqual(obj.value[:3], [6, 6, 6])  # fuzzy (12 / 5 + 3) each

    def test_create_object_wand_and_staff(self):
        for vnum in (31004, 31005):
            with self.subTest(vnum=vnum):
                p = self.old_obj(vnum, value=[3, 4, 9, 30, 0])
                obj, fuzz = self.create(p, 5)
                self.assertEqual(fuzz, [10, 5, 5, 3, 4])
                self.assertEqual(obj.value[:4], [4, 5, 5, 30])  # charges: value[2] is value[1]
                self.assertEqual(obj.cost, 11 * 6 * 6 * 2)

    def test_create_object_potion_pill_and_scroll(self):
        for vnum, fuzz_v0 in ((31002, [12, 13]), (31012, [4, 5]), (31003, [8])):
            with self.subTest(vnum=vnum):
                p = self.old_obj(vnum)
                obj, fuzz = self.create(p, 7)
                self.assertEqual(fuzz, [10, 7, 7] + fuzz_v0)
                self.assertEqual(obj.value[0], p.value[0] + len(fuzz_v0))

    def test_create_object_cost_fifths_and_money(self):
        obj, _ = self.create(self.old_obj(31007), 3)  # a container
        self.assertEqual(obj.cost, 11 * 4 * 4 // 5)
        obj, _ = self.create(self.old_obj(31009), 3)  # money: value[0] is the cost
        self.assertEqual((obj.cost, obj.value[0]), (11 * 4 * 4, 11 * 4 * 4))
        obj, _ = self.create(self.old_obj(31006), 3)  # treasure: as it is
        self.assertEqual(obj.cost, 11 * 4 * 4)

    def test_create_object_level_minus_one_keeps_the_cost(self):
        # level -1 (do_oload with no level is 0, so only code passes -1): the prototype's cost, no fuzzing, but
        # the old format's cost changes still apply, and the level is at least 0
        obj, fuzz = self.create(self.old_obj(31004, cost=50), -1)
        self.assertEqual(fuzz, [])
        self.assertEqual((obj.level, obj.cost), (0, 100))
        obj, fuzz = self.create(self.old_obj(31007, cost=50), -1)
        self.assertEqual((obj.cost, fuzz), (10, []))

    def test_create_object_new_format_is_untouched(self):
        p = self.game.index.objs[31000]
        obj, fuzz = self.create(p, 30)
        self.assertEqual((fuzz, obj.level, obj.cost, obj.value), ([], p.level, p.cost, p.value))

    def test_old_goods_level(self):
        sn = {s.name: i for i, s in enumerate(SKILL_TABLE)}
        d = Draws()
        with d.patch(resets, "number_range")[0]:
            # the lowest level any class gets fireball is 22: 22 * 3 / 4 - 2
            self.assertEqual(resets._old_goods_level(self.old_obj(31002, value=[1, sn["fireball"], -1, -1, -1])), 14)
            # cure light is level 1 for clerics: UMAX (0, 1 * 3 / 4 - 2)
            self.assertEqual(resets._old_goods_level(self.old_obj(31012, value=[1, sn["cure light"], 0, 0, 0])), 0)
            # no spells at all: 53 * 3 / 4 - 2
            self.assertEqual(resets._old_goods_level(self.old_obj(31003, value=[1, -1, -1, -1, -1])), 37)
            # a row after the last skill is zeros
            self.assertEqual(resets._old_goods_level(self.old_obj(31003, value=[1, C.MAX_SKILL - 1, -1, -1, -1])), 0)
            for vnum, top in ((31004, 20), (31005, 25), (31001, 15), (31000, 15), (31006, 20)):
                self.assertEqual(resets._old_goods_level(self.old_obj(vnum)), top)
            self.assertEqual(resets._old_goods_level(self.old_obj(31007)), 0)  # anything else
        self.assertEqual(d.calls, [("range", 10, 20), ("range", 15, 25), ("range", 5, 15), ("range", 5, 15),
                                   ("range", 10, 20)])
        with self.assertRaises(CWouldCrash):
            resets._old_goods_level(self.old_obj(31003, value=[1, C.MAX_SKILL, -1, -1, -1]))

    def test_reset_room_gives_a_shopkeeper_old_goods_their_level(self):
        room = self.game.index.rooms[31001]
        # take the smith away, so the 'M' reset makes a new one and its 'G' resets run
        extract_char(self.game, next(c for c in room.people if c.index.vnum == 31001), True)
        new = self.game.index.objs[31004]
        self.game.index.objs[31004] = old = self.old_obj(31004)
        self.addCleanup(self.game.index.objs.__setitem__, 31004, new)
        seen = []
        real = create.create_object

        def spy(game, p, level):
            seen.append((p.vnum, level))
            return real(game, p, level)

        d = Draws()
        with mock.patch.object(resets, "create_object", spy), d.patch(resets, "number_range")[0]:
            resets.reset_room(self.game, room)
        self.assertIn((31004, 20), seen)  # number_range (10, 20) for a wand
        self.assertEqual(seen.count((31002, 0)), 1)  # new-format goods: level 0
        smith = next(c for c in room.people if c.index.vnum == 31001)
        made = next(o for o in smith.carrying if o.index is old)
        self.assertTrue(made.extra_flags & C.ITEM_INVENTORY)
        self.assertEqual(made.level, 20)


if __name__ == "__main__":
    unittest.main()
