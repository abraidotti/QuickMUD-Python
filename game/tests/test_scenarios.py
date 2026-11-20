"""The differential harness's goldens, replayed in pure Python: no Docker, no C build (#35, decision 4).

Each game/tests/data/scenarios/NAME.scn has a NAME.golden: what the C game printed for it, through
tools/oracle/scenario.c (charm_tools port scenarios --docker charm:build --save). Here the Python game plays the
same file, and every line must match.
A golden whose first line names other C sources is stale: change the C, then save it again.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import unittest
from pathlib import Path

from charm.testing.scenario import EXPECT_STOP, difference, esc, play_fresh, source_hash

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
                text = scn.read_text(encoding="latin-1")
                c = golden.read_text(encoding="latin-1").splitlines()[1:]
                self.assertIsNone(difference(c, play_fresh(text, REPO), text))


class WhereTheCCrashes(unittest.TestCase):
    """Steps that crash the C game, so they can't have a golden: the Python stops with CWouldCrash there instead."""

    def test_a_tell_to_an_awake_mob(self):
        # do_tell reads victim->desc->connected, and a mob has no connection (abraidotti/charm#49). The C
        # driver dies with a segmentation fault on this step.
        text = "@connect dec\nDecimus\npsswrd\n@return\n@mob 3011 3001\ntell hassan hello\nlook\n"
        out = play_fresh(text, REPO)
        self.assertEqual(out[-2], 'step 6 "tell hassan hello"')
        self.assertTrue(out[-1].startswith("stopped CWouldCrash: act_comm.c do_tell: a tell to a mob"), out[-1])

    def test_removing_note_0_from_an_empty_board(self):
        # find_note counts no notes, so count == num == 0, and it calls is_note_to with a NULL note
        # (abraidotti/charm#63).
        text = "@connect dec\nDecimus\npsswrd\n@return\n@return\nnote remove 0\nlook\n"
        out = play_fresh(text, REPO)
        self.assertEqual(out[-2], 'step 6 "note remove 0"')
        self.assertTrue(out[-1].startswith("stopped CWouldCrash: board.c find_note: note 0 of an empty board"), out[-1])

    def test_reading_a_long_note(self):
        # show_note_to_char formats the whole note into printf_to_char's buf[MAX_STRING_LENGTH] (4608), and a note
        # may hold 17,432 characters: 58 lines of 80 overflow it (abraidotti/charm#63). Posting it is fine.
        lines = "".join("%02d %s\n" % (i, "x" * 77) for i in range(58))
        text = "@connect dec\nDecimus\npsswrd\n@return\n@return\nnote write\nall\nLong\n" + lines + "~\np\nnote read 1\n"
        out = play_fresh(text, REPO)
        self.assertEqual(out[-2], 'step %d "note read 1"' % (66 + 3))
        self.assertTrue(out[-1].startswith("stopped CWouldCrash: comm.c printf_to_char:"), out[-1])

    def test_a_long_recipient_list_on_general(self):
        # General must include "all", and handle_con_note_to strcats " all" onto the 252 characters typed, in a
        # buf[MAX_INPUT_LENGTH] (256): glibc aborts with "buffer overflow detected" (abraidotti/charm#63).
        to = " ".join(["Quintus"] * 32)[:252]
        text = "@connect dec\nDecimus\npsswrd\n@return\n@return\nnote write\n" + to + "\nlook\n"
        out = play_fresh(text, REPO)
        self.assertEqual(out[-2], 'step 7 "%s"' % to)
        self.assertTrue(out[-1].startswith("stopped CWouldCrash: board.c handle_con_note_to:"), out[-1])

    def test_a_long_prefix(self):
        # do_prefix sprintfs "Prefix changed to %s.\r\n" into buf[MAX_INPUT_LENGTH] (256), and never sends it: a
        # 235-character prefix overflows it, and glibc aborts with "buffer overflow detected" (abraidotti/charm#69).
        text = "@connect god\nSmokegod\nsmoke123\n@return\n@return\nprefix say\nprefix %s\nlook\n" % ("x" * 235)
        out = play_fresh(text, REPO)
        self.assertEqual(out[-2], 'step 7 "prefix %s"' % ("x" * 235))
        self.assertTrue(out[-1].startswith("stopped CWouldCrash: act_wiz.c do_prefix:"), out[-1])


class Difference(unittest.TestCase):
    C = ['step 1 "look"', 'out a "Welcome to Charm."', "rng 1 0", 'step 2 "sc"', 'out a "scan"', "rng 1 0"]

    def test_lines_must_match(self):
        self.assertIsNone(difference(self.C, list(self.C), ""))
        py = self.C[:1] + ['out a "Welcome to ROM 2.4."'] + self.C[2:]
        self.assertIn("line 2", difference(self.C, py, ""))

    def test_a_stop_is_a_difference_unless_expected(self):
        py = self.C[:1] + ['out a "Welcome to Charm."', "rng 1 0", 'step 2 "sc"', "stopped NotPorted: do_scan"]
        self.assertIn("line 5", difference(self.C, py, ""))
        self.assertIsNone(difference(self.C, py, EXPECT_STOP + "\n"))
        self.assertIn("didn't", difference(self.C, self.C, EXPECT_STOP))


class Format(unittest.TestCase):
    def test_esc(self):
        self.assertEqual(esc(b'a"\\\n\r\xff\x01~'), '"a\\"\\\\\\n\\r\\xff\\x01~"')
