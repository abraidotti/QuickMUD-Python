"""Player files and passwords: the pieces the round trip with the C game (quickmud_tools port players) builds on.

- crypt: the 2,000 cases glibc answered (game/tests/data/crypt.json, from quickmud_tools port crypt)
- the save format's quirks: print_flags, capitalize, the colour digits, objects written tail first and the ones
  a low-level character can't keep left out, the pet's Pos line, and own strings (the C's pointer comparison)

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import json
import unittest
from pathlib import Path

from quickmud.core.crypt import crypt
from quickmud.data import constants as C
from quickmud.entities.things import Char, Obj, PCData
from quickmud.persist import player
from quickmud.world.areafile.reader import Reader

DATA = Path(__file__).parent / "data"


class Crypt(unittest.TestCase):
    def test_matches_glibc(self):
        cases = json.loads((DATA / "crypt.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 2000)
        wrong = [(k, s, h) for k, s, h in cases if crypt(k, s) != h]
        self.assertEqual(wrong, [])

    def test_shemp(self):
        self.assertEqual(crypt("psswrd", "Sh"), "ShdJkE29AGHGg")  # tools/fixtures/player/Shemp
        self.assertEqual(crypt("password", "ab"), crypt("passwordLONGER", "ab"))  # 8 characters count


class Format(unittest.TestCase):
    def test_print_flags(self):
        self.assertEqual(player.print_flags(0), "0")
        self.assertEqual(player.print_flags(1 | 4 | (1 << 26) | (1 << 31)), "ACaf")

    def test_capitalize(self):
        self.assertEqual(player.capitalize("sHEMP"), "Shemp")
        self.assertEqual(player.capitalize(""), "")

    def test_colour_digits_round_trip(self):
        pc = PCData()
        for value, triple in ((7, [0, 7, 0]), (13, [1, 3, 0]), (113, [1, 3, 1]), (101, [0, 1, 1])):
            player._load_colour(pc, "prompt", value)
            self.assertEqual(pc.colours["prompt"], triple)
            self.assertEqual(int(player._colour(pc, "prompt")), value)
        # "100" (beep, normal, black) isn't > 100, so the C reads it as bright colour 90: kept.
        player._load_colour(pc, "prompt", 100)
        self.assertEqual(pc.colours["prompt"], [1, 90, 0])

    def test_objects_tail_first_and_castrated(self):
        index = type("Index", (), {"vnum": 0, "new_format": True, "extra_flags": 0, "wear_flags": 0, "item_type": 0,
                                   "weight": 0, "condition": 0, "level": 0, "value": [0] * 5})
        objs = []
        for vnum, kind, level in ((1, C.ITEM_TRASH, 0), (2, C.ITEM_KEY, 0), (3, C.ITEM_TRASH, 10), (4, 0, 0)):
            i = index()
            i.vnum, i.item_type = vnum, kind
            objs.append(Obj(index=i, item_type=kind, level=level, wear_loc=-1))
        ch = Char(level=5)
        text = player.fwrite_obj(ch, objs, 0)
        # Written tail first; the key, and the level-10 object a level-5 character can't keep, are left out.
        self.assertEqual([int(x.split()[1]) for x in text.splitlines() if x.startswith("Vnum")], [4, 1])

    def test_own_strings_are_written(self):
        i = type("Index", (), {"vnum": 1, "new_format": True, "extra_flags": 0, "wear_flags": 0, "item_type": 0,
                               "weight": 0, "condition": 0, "level": 0, "value": [0] * 5})()
        same = Obj(index=i, name="sword", wear_loc=-1)
        own = Obj(index=i, name="sword", wear_loc=-1, own_strings={"name"})  # read from a file: written again
        text = player.fwrite_obj(Char(level=5), [same, own], 0)
        self.assertEqual(text.count("Name sword~"), 1)


class Reading(unittest.TestCase):
    def test_pet_section_skips_unknown_words(self):
        r = Reader("Bogus 12 Sex 2 End\n")  # (fread_word needs the whitespace after a word, as files have)
        words = []
        while True:  # what fread_pet does with no match: nothing, so the next word is the value
            w = r.read_word()
            words.append(w)
            if w == "End":
                break
        self.assertEqual(words, ["Bogus", "12", "Sex", "2", "End"])


if __name__ == "__main__":
    unittest.main()
