"""quickmud_tools port coverage: the lines it finds for a ported function, and the ones it sees run."""

import io
import unittest

from quickmud_tools.paths import use_game
from quickmud_tools.port import coverage


class Coverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_game()
        cls.funcs = {f.c_name: f for f in coverage.functions({"db.c"})}

    def test_finds_marked_functions_and_their_lines(self):
        f = self.funcs["str_prefix"]
        self.assertEqual((f.c_file, f.module, f.name), ("db.c", "quickmud/core/strings.py", "str_prefix"))
        self.assertNotIn(f.first, f.lines)  # the def line has no line event; PY_START says it was called
        self.assertGreater(len(f.lines), 0)

    def test_a_branch_not_taken_is_missing(self):
        from quickmud.core.strings import str_suffix

        f = self.funcs["str_suffix"]
        # A longer suffix stops at the length test, so str_cmp is never called; the line itself still runs.
        hits = coverage.record(lambda: str_suffix("long suffix", "%c"))
        out = io.StringIO()
        coverage.report([f], hits, out)
        self.assertEqual((f.called, f.missing), (True, []), out.getvalue())
        g = self.funcs["str_cmp"]
        out = io.StringIO()
        coverage.report([g], hits, out)
        self.assertFalse(g.called)  # the length test stopped it before str_cmp
        self.assertIn("never called", out.getvalue())

    def test_a_function_not_called_misses_every_line(self):
        from quickmud.core.strings import atoi

        f = self.funcs["str_prefix"]
        hits = coverage.record(lambda: atoi("12"))
        out = io.StringIO()
        coverage.report([f], hits, out)
        self.assertFalse(f.called)
        self.assertEqual(f.missing, f.lines)

    def test_only_the_named_c_files(self):
        self.assertTrue(all(f.c_file == "db.c" for f in self.funcs.values()))


if __name__ == "__main__":
    unittest.main()
