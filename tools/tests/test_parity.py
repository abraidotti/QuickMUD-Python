"""T1's done criterion: the loader agrees with the real game.

Compares load_world() with captures from the game itself (tools/fixtures/boot): the stock world's 'memory'
totals and boot log, and each broken area in cases/ with the bug() lines the game printed for it. Refresh the
captures with: python -m charm_tools explore parity --docker charm --save
"""

import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from charm_tools import paths
from charm_tools.explore import parity
from charm_tools.explore.areafile.boot import Counts
from charm_tools.explore.areafile.world import load_world

FIXTURES = paths.find_root() / "tools" / "fixtures" / "boot"


class StockWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = load_world()
        cls.memory = (FIXTURES / "memory.txt").read_text(encoding="latin-1")
        cls.bugs = (FIXTURES / "boot-bugs.txt").read_text(encoding="latin-1")

    def test_boots(self):
        self.assertIsNone(self.world.fatal)

    def test_every_memory_total_matches(self):
        expected = parity.parse_memory(self.memory)
        for f in fields(Counts):
            if f.name != "mobprogs":
                with self.subTest(total=f.name):
                    self.assertEqual(getattr(self.world.counts, f.name), getattr(expected, f.name))

    def test_the_same_bug_lines_in_the_same_order(self):
        self.assertEqual(self.world.log_lines(), parity.bug_lines(self.bugs))
        self.assertEqual(len(self.world.log_lines()), 4)


class BrokenAreaTest(unittest.TestCase):
    def test_each_case_matches_the_games_log(self):
        cases = sorted((FIXTURES / "cases").glob("*.are"))
        self.assertGreaterEqual(len(cases), 11)
        area_dir = paths.area_dir()
        for case in cases:
            with self.subTest(case=case.stem):
                expected = case.with_suffix(".log").read_text(encoding="latin-1").splitlines()
                with tempfile.TemporaryDirectory() as tmp:
                    w = load_world(area_dir=parity.case_area_dir(area_dir, case, Path(tmp)))
                self.assertEqual(w.log_lines(), expected)


class ParseTest(unittest.TestCase):
    def test_parse_memory_handles_the_games_line_endings(self):
        c = parity.parse_memory("Affects   1\n\rAreas 2\n\rExDes 3\n\rExits 4\n\rHelps 5\n\rSocials 6\n\r"
                                "Mobs      7(7 new format)\n\rObjs 8(6 new format)\n\rResets 9\n\rRooms 10\n\r"
                                "Shops 11\n\r")
        self.assertEqual((c.affects, c.mobs, c.objects_new, c.shops), (1, 7, 6, 11))

    def test_bug_lines_drop_timestamps_and_stop_at_ready(self):
        log = ("Tue Nov 17 18:17:08 2026 :: [*****] BUG: one\n"
               "Tue Nov 17 18:17:08 2026 :: ROM is ready to rock on port 4000 (0.0.0.0).\n"
               "Tue Nov 17 18:17:09 2026 :: [*****] BUG: later\n")
        self.assertEqual(parity.bug_lines(log), ["[*****] BUG: one"])


if __name__ == "__main__":
    unittest.main()
