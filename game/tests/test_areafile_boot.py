"""The loaders (areafile/boot.py) on small synthetic areas. The real game's behaviour on the stock areas and on
broken ones is pinned by quickmud_tools' test_parity.py; these cover the details those don't show.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import unittest
from functools import lru_cache

from quickmud.world.areafile.boot import Boot
from quickmud.world.areafile.lookups import LookupTables
from quickmud.world.areafile.reader import AreaParseError, Reader

HEADER = "#AREA\nt.are~\nTest~\n{ 1 5} Me  Test~\n30000 30099\n\n"


@lru_cache(maxsize=1)
def tables():
    return LookupTables.from_data()


def boot(*texts, finish=True):
    b = Boot(tables())
    for i, text in enumerate(texts):
        b.load_text(Reader(text, f"t{i}.are"))
    if finish:
        b.finish()
    return b


ROOMS = """#ROOMS
#30000
One~
First.
~
0 0 0
D0
~
door~
1 -1 30001
E
sign~
A sign.
~
S
#30001
Two~
Second.
~
0 AB 1
H 150
M 200
O Bob~
D2
~
door~
1 -1 30000
S
#3100
Lawful~
In the 3000-3399 band.
~
0 0 0
S
#0

"""

MOB = """#MOBILES
#30000
guard~
the guard~
A guard is here.
~
A guard.
~
human~
ABC 0 0 0
5 2 3d8+20 1d1+100 2d4+1 slash
-1 -2 -3 4
0 0 0 0
stand stand male 30
0 0 medium iron
F act B
M greet 30050 hello~
M speech 30051 hi~
#0

"""

OBJECTS = """#OBJECTS
#30000
sword~
a sword~
A sword lies here.~
steel~
weapon 0 AN
sword 3 6 slash 0
5 10 100 G
A
18 2
F
A 0 0 B
E
sword~
Sharp.
~
#30001
potion~
a potion~
A potion.~
glass~
potion 0 A
10 'cure light' '' '' ''
1 1 10 P
#30002
lamp~
a lamp~
A lamp.~
brass~
light 0 A
0 0 AB 0 0
1 1 10 X
#0

"""


class BootTest(unittest.TestCase):
    def test_rooms_exits_and_the_law_hack(self):
        b = boot(HEADER + ROOMS + "#$\n")
        one, two, law = b.rooms[30000], b.rooms[30001], b.rooms[3100]
        self.assertEqual(one.exits[0].to_vnum, 30001)
        self.assertEqual((two.heal_rate, two.mana_rate, two.owner, two.room_flags, two.sector), (150, 200, "Bob", 3, 1))
        d = tables().defines
        self.assertTrue(law.effective_flags & d["ROOM_LAW"])
        self.assertFalse(one.effective_flags & d["ROOM_LAW"])
        self.assertTrue(law.effective_flags & d["ROOM_NO_MOB"])  # no exits: fix_exits sets NO_MOB
        self.assertEqual((b.counts.rooms, b.counts.exits, b.counts.extra_descr), (3, 2, 1))

    def test_d_resets_close_doors_and_reuse_their_block(self):
        text = HEADER + ROOMS + "#RESETS\nD 0 30000 0 2\nD 0 30001 2 1\nR 0 30000 6\nS\n\n#$\n"
        b = boot(text)
        d = tables().defines
        self.assertEqual(b.rooms[30000].exits[0].rs_flags, d["EX_ISDOOR"] | d["EX_CLOSED"] | d["EX_LOCKED"])
        self.assertEqual(b.rooms[30001].exits[2].rs_flags, d["EX_ISDOOR"] | d["EX_CLOSED"])
        # Three reset lines, one allocation: the first D's block is freed, the second D reuses and frees it, and
        # the R reuses it again (mem.c new_reset_data). top_reset is 1.
        self.assertEqual(b.counts.resets, 1)
        self.assertEqual([r.command for r in b.room_resets[30000]], ["R"])

    def test_mobs(self):
        b = boot(HEADER + MOB + ROOMS + "#$\n", finish=False)  # its mobprogs have no code: see the next test
        m = b.mobs[30000]
        self.assertEqual((m.race, m.level, str(m.hit), m.attack, m.ac), ("human", 5, "3d8+20", "slash",
                                                                          (-10, -20, -30, 40)))
        self.assertEqual((m.removals[0].field, m.removals[0].bits), ("act", 2))
        self.assertEqual([p.trigger for p in m.mobprogs], ["speech", "greet"])  # the game's list is reversed

    def test_missing_mobprog_code_is_fatal_in_fix_mobprogs(self):
        with self.assertRaises(AreaParseError) as e:
            boot(HEADER + MOB + ROOMS + "#$\n", finish=False).finish()
        self.assertEqual(e.exception.message, "Fix_mobprogs: code vnum 30051 not found.")

    def test_objects_values_by_type_and_condition(self):
        b = boot(HEADER + OBJECTS + "#$\n")
        sword, potion, lamp = b.objects[30000], b.objects[30001], b.objects[30002]
        self.assertEqual(sword.values, ["sword", 3, 6, "slash", 0])
        self.assertEqual(sword.condition, 90)
        self.assertEqual([a.where for a in sword.affects], ["affects", "object"])
        self.assertEqual(potion.values, [10, "cure light", "", "", ""])
        self.assertEqual(lamp.values, [0, 0, 3, 0, 0])
        self.assertEqual(lamp.condition, 100)  # an unknown letter means 100
        self.assertEqual((b.counts.objects, b.counts.affects, b.counts.extra_descr), (3, 2, 1))

    def test_section_names_are_case_insensitive(self):
        b = boot(HEADER.replace("#AREA", "#area") + "#$\n")
        self.assertEqual(b.counts.areas, 1)

    def test_rooms_before_any_area_is_fatal_with_the_games_message(self):
        with self.assertRaises(AreaParseError) as e:
            boot(ROOMS + "#$\n")
        self.assertEqual(e.exception.message, "Load_resets: no #AREA seen yet.")  # sic, as in db.c

    def test_shops_need_their_keeper_loaded_first(self):
        shop = "#SHOPS\n30000 0 0 0 0 0 100 100 0 23\n0\n\n"
        self.assertEqual(boot(HEADER + MOB.replace("M greet 30050 hello~\nM speech 30051 hi~\n", "") + shop
                              + "#$\n").counts.shops, 1)
        with self.assertRaises(AreaParseError) as e:
            boot(HEADER + shop + "#$\n")
        self.assertEqual(e.exception.message, "Get_mob_index: bad vnum 30000.")

    def test_socials(self):
        b = boot("#SOCIALS\nnod 0 0\nYou nod.\n$n nods.\n#\nwave\n$\n$n waves.\n$\n$\n$\n$\n$\n$\n#0\n\n#$\n")
        nod, wave = b.files[0].socials
        self.assertEqual(nod.messages[:3], ["You nod.", "$n nods.", None])
        self.assertEqual(wave.messages[:2], [None, "$n waves."])
        self.assertEqual(b.counts.socials, 2)

    def test_areadata_header(self):
        text = "#AREADATA\nName New Place~\nBuilders Me~\nVNUMs 30000 30099\nCredits { 1 5} Me~\n" \
               "Security 3\nUnknownKey\nEnd\n\n#$\n"
        b = boot(text)
        h = b.files[0].header
        self.assertEqual((h.name, h.builders, h.min_vnum, h.max_vnum, h.security, h.olc),
                         ("New Place", "Me", 30000, 30099, 3, True))
        self.assertEqual(h.level_band, ("1", "5"))

    OLD_MOB = ("#MOBOLD\n#30000\nelf sage~\nthe sage~\nA sage.\n~\nA sage.\n~\n"
               "B 0 300 {letter}\n12 0 5 2d6+30 1d4+2\n{gold} 99\n{start} 8 2\n#0\n")
    OLD_OBJ = ("#OBJOLD\n#30000\noldpotion~\nan old potion~\nA potion.\n~\nthe action~\n"
               "10 0 A\n12 {slot} 0 0\n1 50 7\nA\n1 2\nE\nkw~\ntext~\n#0\n")

    def test_an_old_format_mob_is_read(self):
        b = boot(HEADER + self.OLD_MOB.format(letter="S", gold=-130, start=3) + "#$\n")
        m = b.mobs[30000]
        self.assertEqual((m.keywords, m.act, m.alignment, m.level, m.sex), ("elf sage", 2, 300, 12, 2))
        self.assertEqual(m.wealth, -6)  # gold / 20, truncated toward zero as in C
        self.assertEqual((m.start_pos, m.default_pos), (8, 8))  # 3 is below POS_SLEEPING: standing
        self.assertEqual((b.counts.mobs, b.counts.mobs_new), (1, 1))  # convert_mobile counts it as it loads

    def test_an_old_format_mob_needs_its_s(self):
        with self.assertRaises(AreaParseError) as e:
            boot(HEADER + self.OLD_MOB.format(letter="X", gold=0, start=8) + "#$\n")
        self.assertEqual(e.exception.message, "Load_mobiles: vnum 30000 non-S.")

    def test_an_old_format_object_is_read(self):
        b = boot(HEADER + self.OLD_OBJ.format(slot=16) + "#$\n")
        o = b.objects[30000]
        self.assertEqual((o.item_type, o.type_word, o.values, o.weight, o.cost),
                         (10, "potion", [12, 16, 0, 0, 0], 1, 50))
        self.assertEqual((len(o.affects), len(o.extra_descr)), (1, 1))
        self.assertEqual((b.counts.objects, b.counts.objects_new, b.counts.affects, b.counts.extra_descr), (1, 0, 1, 1))

    def test_old_format_errors_are_the_new_formats(self):
        mob = self.OLD_MOB.format(letter="S", gold=0, start=8)
        cases = [
            (mob.replace("#0\n", mob.split("\n", 1)[1]), "Load_mobiles: vnum 30000 duplicated."),
            ("#MOBOLD\n30000\n", "Load_mobiles: # not found."),
            (self.OLD_OBJ.format(slot=16).replace("#0\n", "#30000\n"), "Load_objects: vnum 30000 duplicated."),
            ("#OBJOLD\nx\n", "Load_objects: # not found."),
        ]
        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(AreaParseError) as e:
                    boot(HEADER + text + "#$\n")
                self.assertEqual(e.exception.message, message)
        for section, what in (("#MOBOLD\n#30000\nname~\nshort~\n", "the long description"),
                              ("#OBJOLD\n#30000\nname~\n", "the short description")):
            with self.subTest(what=what):
                with self.assertRaises(AreaParseError) as e:
                    boot(HEADER + section)
                self.assertIn(what, e.exception.message)  # NULL from Fread_string at EOF, dereferenced

    def test_a_bad_spell_slot_stops_the_boot(self):
        with self.assertRaises(AreaParseError) as e:
            boot(HEADER + self.OLD_OBJ.format(slot=9999) + "#$\n")
        self.assertEqual(e.exception.message, "Slot_lookup: bad slot 9999.")


if __name__ == "__main__":
    unittest.main()
