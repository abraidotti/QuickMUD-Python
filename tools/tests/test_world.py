"""quickmud_tools port world: the Python game's world against the C game's, from the saved capture (no Docker).

The capture is tools/tests/data/world-20261117.txt.xz: the C game booted by tools/oracle/worldcheck.c with
QUICKMUD_SEED=20261117 and a fixed clock, then three more area_update passes, dumped after each, before cut-over
(the c-final tag has the driver).
"""

import unittest
from functools import lru_cache

from quickmud_tools.port import world


@lru_cache(maxsize=1)
def both():
    return world.load(world.fixture_path()), world.python_world()


class SavedCapture(unittest.TestCase):
    def test_python_world_is_the_c_world(self):
        c, py = both()
        self.assertGreater(len(c.dump), 70_000)
        self.assertEqual(world.compare(c, py), [])

    def test_the_capture_covers_boot_and_three_updates(self):
        c, _ = both()
        self.assertEqual([x for x in c.dump if x.startswith("dump ")], ["dump 0", "dump 1", "dump 2", "dump 3"])
        self.assertTrue(any(x.startswith("Check Levels") for x in c.log))


class Compare(unittest.TestCase):
    A = world.Capture(["dump 0", "char 0 vnum=1 hit=10/10", "  aff where=0", "rng 1 2 3"], ["x"])

    def test_same(self):
        self.assertEqual(world.compare(self.A, self.A), [])

    def test_names_the_line_and_column(self):
        b = world.Capture(["dump 0", "char 0 vnum=1 hit=11/11", "  aff where=0", "rng 1 2 3"], ["x"])
        (d,) = world.compare(self.A, b)
        self.assertIn("dump line 2 (char 0), from column 20", d)

    def test_length_and_log(self):
        b = world.Capture(self.A.dump[:-1], ["y"])
        diffs = world.compare(self.A, b)
        self.assertIn("dump length: C 4 lines, Python 3", diffs)
        self.assertTrue(any(d.startswith("log line 1") for d in diffs))


if __name__ == "__main__":
    unittest.main()
