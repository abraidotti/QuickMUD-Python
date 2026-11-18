"""Prototypes, resets and the handler functions, on small synthetic areas booted through boot_db.

The stock areas are compared with the C game line by line by ``charm_tools port world`` (and its test, which uses
the saved capture). These cover what the stock areas don't reach, or reach too rarely to pin down: the 'F' line
after the race flags, the anti-alignment zap, a dark room's infrared, nested container weights, the UMIN double
draw, an area range of "0 0", and the NotPorted branches.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import tempfile
import unittest
from pathlib import Path

from charm.core import log, rng
from charm.core.errors import NotPorted
from charm.data import constants as C
from charm.data.races import RACE_TABLE
from charm.entities import handler
from charm.entities.boot import boot_db
from charm.entities.resets import _umin_fuzzy
from charm.entities.things import Obj
from charm.world import lookup
from charm.world.index import Affect

BAT = next(r for r in RACE_TABLE if r.name == "bat")
BAT_AFF_BIT = BAT.aff & -BAT.aff  # the lowest affect bit the race gives; the 'F' line below removes it

AREA = f"""#AREA
t.are~
Test~
{{ 1 5}} Me  Test~
0 0

#MOBILES
#30000
guard~
a guard~
a guard stands here.
~
he looks evil.
~
bat~
2 0 -1000 0
5 0 2d6+10 1d1+99 1d4+0 punch
1 2 3 4
0 0 0 0
stand stand male 100
0 0 medium flesh
F aff {BAT_AFF_BIT}
{{trigger}}#0

#OBJECTS
#30010
sack~
a sack~
A sack lies here.~
cloth~
container 0 1
50 0 0 10 50
1 10 0 P
#30011
sword holy~
a holy sword~
A holy sword lies here.~
steel~
weapon {C.ITEM_ANTI_EVIL} 8193
sword 1 6 slash 0
1 60 250 P
#30012
pebble~
a pebble~
A pebble lies here.~
stone~
trash 0 1
0 0 0 0 0
1 7 0 P
#0

#ROOMS
#30000
Dark~
A dark room.
~
0 {C.ROOM_DARK} 3
D1
~
~
0 -1 30001
S
#30001
Light~
A lit room.
~
0 0 0
D3
~
~
0 -1 30000
S
#0

#RESETS
M 0 30000 5 30000 2
E 0 30011 0 16
M 0 30000 5 30000 2
G 0 30012 0
M 0 30000 5 30000 2
O 0 30010 0 30001
P 0 30012 -1 30010 3
S

{{progs}}#$
"""

PROGS = "#MOBPROGS\n#30050\nsay hi~\n#0\n\n"


def boot_area(trigger: str = "", progs: str = "", seed: str = "1"):
    text = AREA.replace("{trigger}", trigger).replace("{progs}", progs)
    with tempfile.TemporaryDirectory() as d:
        Path(d, "area.lst").write_text("t.are\n$\n")
        Path(d, "t.are").write_text(text)
        with log.capture() as lines:
            game = boot_db(Path(d), 1763400000, {"CHARM_SEED": seed})
    return game, lines


class Prototypes(unittest.TestCase):
    def test_load_mobiles_transforms(self):
        game, _ = boot_area()
        m = game.index.get_mob_index(30000)
        self.assertEqual(m.act, 2 | C.ACT_IS_NPC | BAT.act)
        self.assertEqual(m.affected_by, BAT.aff & ~BAT_AFF_BIT)  # race flags in, then the 'F' line out
        self.assertEqual(m.race, lookup.race_lookup("bat"))
        self.assertEqual(m.long_descr, "A guard stands here.\n\r")  # upper-cased, and fread_string's \n\r
        self.assertEqual(m.description, "He looks evil.\n\r")
        self.assertEqual(m.ac, (10, 20, 30, 40))
        self.assertEqual(m.dam_type, lookup.attack_lookup("punch"))

    def test_assign_area_vnum(self):
        game, _ = boot_area()
        area = game.index.areas[0]
        self.assertEqual((area.min_vnum, area.max_vnum), (30000, 30012))  # "0 0" in the file


class Resets(unittest.TestCase):
    def setUp(self):
        self.game, self.log = boot_area()
        ix = self.game.index
        self.dark, self.lit = ix.get_room_index(30000), ix.get_room_index(30001)

    def test_room_limit_and_infrared(self):
        self.assertEqual(len(self.dark.people), 2)  # the third 'M' finds two there already
        for mob in self.dark.people:
            self.assertTrue(mob.affected_by & C.AFF_INFRARED)  # made in a dark room
        self.assertEqual(self.game.index.get_mob_index(30000).count, 2)

    def test_evil_guard_is_zapped_by_the_holy_sword(self):
        sword = next(o for o in self.game.object_list if o.index.vnum == 30011)
        self.assertIs(sword.in_room, self.dark)
        self.assertIsNone(sword.carried_by)
        self.assertEqual(sword.wear_loc, -1)
        first = self.game.char_list[-1]  # created first: the char list is newest first
        self.assertEqual((first.carry_number, first.carry_weight), (0, 0))
        self.assertEqual(first.armor, [10, 20, 30, 40])  # nothing was worn

    def test_given_item(self):
        second = self.game.char_list[0]
        pebble = second.carrying[0]
        self.assertEqual(pebble.index.vnum, 30012)
        self.assertEqual((pebble.wear_loc, second.carry_number, second.carry_weight), (-1, 1, 7))

    def test_container_filled(self):
        (sack,) = self.lit.contents
        self.assertEqual(sack.index.vnum, 30010)
        self.assertEqual(len(sack.contains), 3)
        self.assertEqual(sack.cost, 0)  # 'O' resets make it free
        # value[4] is 50%, applied to each item and truncated each time: 10 + 3 * 3, not 10 + 21 / 2
        self.assertEqual(handler.get_obj_weight(sack), 10 + 3 * (7 * 50 // 100))

    def test_act_trigger_in_the_room_is_not_ported(self):
        with self.assertRaises(NotPorted) as e:
            boot_area(trigger="M act 30050 hello~\n", progs=PROGS)
        self.assertIn("act_new", str(e.exception))


class Handler(unittest.TestCase):
    def test_weight_and_number_of_nested_containers(self):
        inner = Obj(item_type=C.ITEM_CONTAINER, weight=4, value=[0, 0, 0, 0, 50])
        stone = Obj(item_type=C.ITEM_TRASH, weight=7)
        inner.contains.append(stone)
        outer = Obj(item_type=C.ITEM_CONTAINER, weight=10, value=[0, 0, 0, 0, 100])
        outer.contains.append(inner)
        self.assertEqual(handler.get_obj_weight(inner), 4 + 3)  # 7 * 50 / 100, truncated
        self.assertEqual(handler.get_obj_weight(outer), 10 + 7)
        self.assertEqual(handler.get_obj_number(outer), 1)  # containers don't count; the stone does

    def test_affect_modify_adds_and_removes(self):
        game, _ = boot_area()
        mob = game.char_list[0]
        before = (mob.affected_by, list(mob.armor), mob.saving_throw)
        paf = Affect(C.TO_AFFECTS, -1, 1, -1, C.APPLY_AC, -5, C.AFF_HASTE)
        handler.affect_modify(mob, paf, True)
        self.assertTrue(mob.affected_by & C.AFF_HASTE)
        self.assertEqual(mob.armor, [a - 5 for a in before[1]])
        handler.affect_modify(mob, paf, False)
        self.assertEqual((mob.affected_by, mob.armor, mob.saving_throw), before)


class UminTwice(unittest.TestCase):
    def draws(self, fn):
        rng.srandom(7)
        out = fn()
        return out, rng.random()  # the next draw shows how many were used

    def test_two_draws_below_the_cap(self):
        expected = self.draws(lambda: (rng.number_fuzzy(10), rng.number_fuzzy(10))[1])
        self.assertEqual(self.draws(lambda: _umin_fuzzy(10)), expected)

    def test_one_draw_at_the_cap(self):
        expected = self.draws(lambda: (rng.number_fuzzy(60), C.LEVEL_HERO - 1)[1])
        self.assertEqual(self.draws(lambda: _umin_fuzzy(60)), expected)


class Lookups(unittest.TestCase):
    def test_what_each_returns_for_no_match(self):
        self.assertEqual(lookup.race_lookup("nonesuch"), 0)
        self.assertEqual(lookup.attack_lookup(""), 0)
        self.assertEqual(lookup.weapon_type("nonesuch"), C.WEAPON_EXOTIC)
        self.assertEqual(lookup.skill_lookup("nonesuch"), -1)
        self.assertEqual(lookup.item_lookup("nonesuch"), -1)

    def test_first_prefix_match_wins(self):
        self.assertEqual(lookup.position_lookup("st"), C.POS_STUNNED)  # before "standing" in position_table
        self.assertEqual(lookup.skill_lookup("sanct"), lookup.skill_lookup("sanctuary"))


if __name__ == "__main__":
    unittest.main()
