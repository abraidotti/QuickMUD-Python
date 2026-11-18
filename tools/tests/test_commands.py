"""charm_tools port commands and sim bots without a game: the comparison and the pulse line they read.

port commands needs Docker and sim bots runs the game, so these check the parts that decide pass or fail: a difference
shows, and sim bots reads the line the game's --pulse-stats writes.
"""

import sys
import unittest

from charm_tools.paths import game_dir
from charm_tools.port import commands
from charm_tools.port.login import Scenario, Transcript, compare
from charm_tools.sim import bots


class Compare(unittest.TestCase):
    def test_any_other_difference_shows(self):
        sc = Scenario("x", [(0, "look")])
        diffs = compare(Transcript([b"hi", b"A room"]), Transcript([b"hi", b"A rook"]), sc)
        self.assertEqual(len(diffs), 1)
        self.assertIn("session 0 sends 'look'", diffs[0])

    def test_fixture_players_exist(self):
        from charm_tools.port.live import fixtures
        for who in commands.PLAYERS:
            self.assertTrue((fixtures() / "player" / who).is_file(), who)


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
