"""The differential harness's goldens, replayed in pure Python: no Docker, no C build (#35, decision 4).

Each game/tests/data/scenarios/NAME.scn has a NAME.golden: what the C game printed for it, through
tools/oracle/scenario.c (charm_tools port scenarios --docker charm:build --save). Here the Python game plays the
same file, and every line must match, after the on-purpose differences (charm.testing.scenario.SUBSTITUTIONS).
A golden whose first line names other C sources is stale: change the C, then save it again.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import unittest
from pathlib import Path

from charm.testing.scenario import comparable, esc, play_fresh, source_hash

REPO = Path(__file__).resolve().parents[2]
SCENARIOS = Path(__file__).parent / "data" / "scenarios"


class Goldens(unittest.TestCase):
    def test_every_scenario_has_a_fresh_golden(self):
        digest = source_hash(REPO)
        files = sorted(SCENARIOS.glob("*.scn"))
        self.assertTrue(files)
        for scn in files:
            with self.subTest(scenario=scn.stem):
                golden = scn.with_suffix(".golden")
                self.assertTrue(golden.exists(), "no golden: charm_tools port scenarios --docker charm:build --save")
                first = golden.read_text(encoding="latin-1").splitlines()[0]
                self.assertEqual(first, f"sources {digest}", "stale: the C changed since the golden was saved")

    def test_python_matches_the_c(self):
        for scn in sorted(SCENARIOS.glob("*.scn")):
            golden = scn.with_suffix(".golden")
            if not golden.exists():
                continue
            with self.subTest(scenario=scn.stem):
                want = comparable(golden.read_text(encoding="latin-1").splitlines()[1:])
                got = play_fresh(scn.read_text(encoding="latin-1"), REPO)
                for i, (a, b) in enumerate(zip(want, got)):
                    self.assertEqual(b, a, f"line {i + 1} of {scn.stem}")
                self.assertEqual(len(got), len(want))


class Format(unittest.TestCase):
    def test_esc(self):
        self.assertEqual(esc(b'a"\\\n\r\xff\x01~'), '"a\\"\\\\\\n\\r\\xff\\x01~"')
