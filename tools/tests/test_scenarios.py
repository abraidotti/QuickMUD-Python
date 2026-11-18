"""charm_tools port scenarios without Docker: the comparison, and the goldens against the Python game.

The game's own tests (game/tests/test_scenarios.py) replay the goldens too; this checks the tool's side of it.
"""

import unittest

from charm_tools.port import scenarios


class Difference(unittest.TestCase):
    def test_names_the_step(self):
        c = ["boot x", "step 1 \"look\"", "out a \"room\"", "rng 1 00000000"]
        py = ["boot x", "step 1 \"look\"", "out a \"rook\"", "rng 1 00000000"]
        self.assertIn('line 3, at step 1 "look"', scenarios.difference(c, py))

    def test_lengths(self):
        self.assertIsNone(scenarios.difference(["a"], ["a"]))
        self.assertIn("1 lines from C, 2 from Python", scenarios.difference(["a"], ["a", "b"]))


class Goldens(unittest.TestCase):
    def test_saved_goldens_match_the_python_game(self):
        self.assertEqual(scenarios.run(None), 0)
