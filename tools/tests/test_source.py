"""The narrow C readers (explore/source)."""

import tempfile
import unittest
from pathlib import Path

from charm_tools import paths
from charm_tools.explore.source.cdefs import Defines, SourceError
from charm_tools.explore.source.ctables import LookupTables, Str, prefix_lookup, read_array, str_prefix_matches


def write(text):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".h", delete=False, encoding="latin-1")
    tmp.write(text)
    tmp.close()
    return Path(tmp.name)


class DefinesTest(unittest.TestCase):
    def test_letters_names_and_operators(self):
        d = Defines(write("#define A 1\n#define B 2\n#define C 4\n#define X (A|C)  /* flags */\n"
                          "#define Y (X + 1)\n#define Z (1 << 4)\n#define FN(x) ((x)+1)\n"))
        self.assertEqual((d["X"], d["Y"], d["Z"]), (5, 6, 16))
        self.assertNotIn("FN", d)  # function-like macros are skipped

    def test_unknown_name_fails_loudly(self):
        d = Defines(write("#define X (NOPE)\n"))
        with self.assertRaises(SourceError):
            d["X"]
        with self.assertRaises(SourceError):
            d["MISSING"]

    def test_real_merc_h(self):
        d = Defines(paths.src_dir() / "merc.h")
        self.assertEqual(d["ROOM_LAW"], 1 << 18)  # (S)
        self.assertEqual(d["ROOM_VNUM_TEMPLE"], 3001)
        self.assertEqual(d["MAX_KEY_HASH"], 1024)


class ArrayTest(unittest.TestCase):
    def test_entries_fields_and_comments(self):
        p = write('const struct t tab[] = {\n  /* a comment, with commas */\n  {"one", A, {1, 2}},\n'
                  '  {"t\\"wo", B, {3, 4}},  // trailing\n  {NULL, 0, {0, 0}}\n};\n')
        rows = read_array(p, "tab")
        self.assertEqual(rows[0], [Str("one"), "A", "{1, 2}"])
        self.assertEqual(rows[1][0], Str('t"wo'))
        self.assertEqual(rows[2][0], "NULL")

    def test_missing_array_fails_loudly(self):
        with self.assertRaises(SourceError):
            read_array(write("int x;\n"), "tab")

    def test_real_tables(self):
        t = LookupTables.from_source(paths.src_dir())
        self.assertIn(("weapon", 5), t.item_types)
        self.assertEqual(t.sizes, ["tiny", "small", "medium", "large", "huge", "giant"])
        self.assertEqual(t.clans, ["", "loner", "rom"])
        self.assertIn("spec_cast_adept", t.specials)
        self.assertEqual(t.mprog_triggers[0], ("act", 1))


class LookupTest(unittest.TestCase):
    def test_rom_prefix_lookup(self):
        names = ["light", "lance", "scroll"]
        self.assertEqual(prefix_lookup("sc", names), 2)
        self.assertEqual(prefix_lookup("LIG", names), 0)
        self.assertEqual(prefix_lookup("l", names), 0)  # first match wins
        self.assertEqual(prefix_lookup("lights", names), -1)  # longer than the entry
        self.assertEqual(prefix_lookup("", names), -1)  # the first-letter check fails for ""

    def test_str_prefix(self):
        self.assertTrue(str_prefix_matches("ac", "act"))
        self.assertTrue(str_prefix_matches("", "act"))
        self.assertFalse(str_prefix_matches("acts", "act"))


if __name__ == "__main__":
    unittest.main()
