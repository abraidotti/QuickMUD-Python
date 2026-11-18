"""charm_tools port: the C function finder, the marker scan, and the RNG capture's parsing and comparing."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from charm_tools import paths
from charm_tools.port import rng, status


def functions_in(source):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.c"
        p.write_text(textwrap.dedent(source))
        return [(f.name, f.start, f.end) for f in status.c_functions(p)]


class CFunctions(unittest.TestCase):
    def test_definitions_not_prototypes(self):
        self.assertEqual(functions_in("""\
            int number_range args ((int from, int to));
            int number_range (int from, int to)
            {
                return from;
            }
            """), [("number_range", 2, 5)])

    def test_parameters_over_several_lines(self):
        self.assertEqual(functions_in("""\
            void act_new (const char *format, CHAR_DATA * ch,
                          const void *arg1, int type)
            {
            }
            """), [("act_new", 1, 4)])

    def test_olc_macro_definitions(self):
        self.assertEqual(functions_in("""\
            #define REDIT( fun )        bool fun( CHAR_DATA *ch, char *argument )
            REDIT (redit_show)
            {
                return FALSE;
            }
            """), [("redit_show", 2, 5)])

    def test_commented_out_code_is_not_counted(self):
        self.assertEqual(functions_in("""\
            /*
            void do_old (CHAR_DATA * ch)
            {
            }
            */
            void do_new (CHAR_DATA * ch)
            {
            }
            """), [("do_new", 6, 8)])

    def test_tables_are_not_functions(self):
        self.assertEqual(functions_in("""\
            const struct x table[] = {
                {"a", 1},
            };
            """), [])


class RealTree(unittest.TestCase):
    def test_markers_all_name_c_functions(self):
        st = status.status()
        self.assertEqual(st.bad_markers, [])
        ported = {(p.c_file, p.c_name): p.module for p in st.ports}
        for name in ("init_mm", "number_mm", "number_range", "number_percent", "number_door", "number_bits",
                     "number_fuzzy", "dice"):
            self.assertEqual(ported.get(("db.c", name)), "charm/core/rng.py", name)

    def test_finds_the_editor_functions(self):
        names = {(f.file, f.name) for f in status.status().functions}
        self.assertIn(("olc_act.c", "redit_show"), names)
        self.assertIn(("hedit.c", "hedit_show"), names)
        self.assertIn(("comm.c", "game_loop_unix"), names)

    def test_report(self):
        text = status.report(status.status())
        self.assertIn("charm/core/rng.py", text)
        self.assertRegex(text, r"\d+ of \d+ C functions ported \(\d+\.\d%\), \d+ more partly")
        self.assertIn("All hand-written Python in game/charm", text)

    def test_partial_markers(self):
        st = status.status()
        partial = {(p.c_file, p.c_name) for p in st.ports if p.partial}
        self.assertIn(("db.c", "boot_db"), partial)
        self.assertIn(("db.c", "create_mobile"), partial)
        self.assertNotIn(("db.c", "load_rooms"), partial)
        self.assertIn(("db.c", "reset_room"), partial)
        full = {(p.c_file, p.c_name) for p in st.ports if not p.partial}
        for name in (("db2.c", "load_mobiles"), ("db2.c", "load_objects"), ("db.c", "reset_area"),
                     ("db.c", "assign_area_vnum"), ("handler.c", "obj_to_obj")):
            self.assertIn(name, full)
        self.assertTrue(status.MARKER.match("    # C: db2.c load_objects [partial]").group(3))
        self.assertIsNone(status.MARKER.match("# C: db.c load_rooms [partly]"))

    def test_use_game_makes_charm_importable(self):
        paths.use_game()
        from charm.core import rng as game_rng  # noqa: F401  (the import is the test)


class Capture(unittest.TestCase):
    OUT = ("stream 1 random -\nvalues 5 6 7\n"
           "stream 1 number_range 1,6 0,99\nvalues 3 40 2\n")

    def test_parse(self):
        got = rng.parse(self.OUT, 3)
        self.assertEqual(got["count"], 3)
        self.assertEqual(got["seeds"]["1"]["random"]["args"], [])
        self.assertEqual(got["seeds"]["1"]["number_range"]["args"], ["1,6", "0,99"])
        self.assertEqual(got["seeds"]["1"]["number_range"]["first"], [3, 40, 2])
        self.assertEqual(got["seeds"]["1"]["random"]["sha256"], rng.digest([5, 6, 7]))

    def test_parse_checks_the_count(self):
        with self.assertRaises(ValueError):
            rng.parse(self.OUT, 4)

    def test_compare_names_the_first_difference(self):
        a = rng.parse(self.OUT, 3)
        b = rng.parse(self.OUT.replace("values 3 40 2", "values 3 41 2"), 3)
        self.assertEqual(rng.compare(a, a), [])
        self.assertEqual(rng.compare(a, b), ["seed 1 number_range: first difference at draw 1"])


if __name__ == "__main__":
    unittest.main()
