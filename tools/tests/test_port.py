"""charm_tools port status: the C functions frozen at c-final, and the marker scan."""

import unittest

from charm_tools import paths
from charm_tools.port import status


class FrozenCFunctions(unittest.TestCase):
    def test_the_list_frozen_at_c_final(self):
        functions, c_lines = status.c_functions()
        self.assertEqual(len(functions), 950)
        self.assertEqual(len(c_lines), 41)
        self.assertEqual(len({(f.file, f.name) for f in functions}), 950)
        self.assertTrue(all(f.file in c_lines and 0 < f.start <= f.end <= c_lines[f.file] for f in functions))


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
        self.assertIn(("db.c", "boot_db"), partial)  # charm.world.areafile.world's half; charm.entities.boot is whole
        self.assertNotIn(("comm.c", "game_loop_unix"), partial)  # whole, with a kept difference (#112)
        for name in ("load_rooms", "create_mobile", "create_object", "reset_room", "bug"):
            self.assertNotIn(("db.c", name), partial)
        full = {(p.c_file, p.c_name) for p in st.ports if not p.partial}
        for name in (("db2.c", "load_mobiles"), ("db2.c", "load_objects"), ("db.c", "reset_area"),
                     ("db.c", "assign_area_vnum"), ("handler.c", "obj_to_obj")):
            self.assertIn(name, full)
        self.assertTrue(status.MARKER.match("    # C: db2.c load_objects [partial]").group(3))
        self.assertIsNone(status.MARKER.match("# C: db.c load_rooms [partly]"))

    def test_kept_differences(self):
        st = status.status()
        self.assertEqual(set(st.kept), {("comm.c", "game_loop_unix"), ("db.c", "do_memory"), ("db.c", "do_dump")})
        self.assertIn("kept on purpose (3, charm/core/kept_differences.py)", status.report(st))

    def test_a_bad_kept_entry_is_an_error(self):
        real = status.kept_differences
        cases = {("comm.c", "no_such_fn"): "names no C function",
                 ("db.c", "boot_db"): "still has a [partial] marker",
                 ("db.c", "alloc_mem"): "has no '# C:' marker",
                 ("db.c", "do_memory"): "cites no issue"}
        for key, error in cases.items():
            with self.subTest(key=key):
                status.kept_differences = lambda root, key=key: {key: "kept, no reason given"}
                try:
                    bad = status.status().bad_markers
                finally:
                    status.kept_differences = real
                self.assertTrue(any(error in b for b in bad), bad)

    def test_later_notes(self):
        st = status.status()
        self.assertTrue(st.later)
        self.assertTrue(all(n.text for n in st.later))
        self.assertTrue(any(n.module == "charm/entities/handler.py" for n in st.later))
        self.assertIn("Improvements noted for later", status.report(st))
        lists = next(n for n in st.later if "insert(0)" in n.text)
        self.assertTrue(lists.text.endswith("carrying, contains)"))  # joined over its second comment line
        self.assertEqual(status.LATER.search("    x = 1  # LATER: a deque").group(1).strip(), "a deque")

    def test_use_game_makes_charm_importable(self):
        paths.use_game()
        from charm.core import rng as game_rng  # noqa: F401  (the import is the test)


if __name__ == "__main__":
    unittest.main()
