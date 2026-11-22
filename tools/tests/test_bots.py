"""charm_tools sim bots without a game: it reads the line the game's --pulse-stats writes, which decides pass or
fail."""

import sys
import unittest

from charm_tools.paths import game_dir
from charm_tools.sim import bots


class Bots(unittest.TestCase):
    def test_reads_the_games_run_line(self):
        sys.path.insert(0, str(game_dir()))
        try:
            from charm.net.server import PulseStats
        finally:
            sys.path.remove(str(game_dir()))
        line = "Pulse work over the run: " + PulseStats.summary([0.001, 0.002, 0.030])
        m = bots.RUN_LINE.search("Wed Nov 18 10:28:22 2026 :: " + line)
        self.assertIsNotNone(m, line)
        self.assertEqual([float(x) for x in m.groups()], [2.0, 2.0, 30.0, 11.0, 3.0])
