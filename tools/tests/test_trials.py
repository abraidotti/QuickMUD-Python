"""Unit tests for the lobby and churn trials' own logic. The live runs are: python -m charm_tools sim lobby
--python, and python -m charm_tools sim churn --python."""

import re
import unittest

from charm_tools.paths import game_dir
from charm_tools.sim import churn, lobby
from charm_tools.sim.games import bug_lines
from charm_tools.sim.smoke import Fail


class FakeSession:
    """Plays a game's side of the lobby: each send gets the next canned output."""

    def __init__(self, outputs):
        self.outputs, self.sent = list(outputs), []

    def expect(self, pattern, timeout=None):
        if not self.outputs or not re.search(pattern, self.outputs[0]):
            raise Fail(f"no {pattern!r}")
        return self.outputs.pop(0)

    def send(self, line):
        self.sent.append(line)


class LobbyTest(unittest.TestCase):
    def test_every_state_the_nanny_handles_has_a_case(self):
        text = (game_dir() / "charm" / "net" / "nanny.py").read_text(encoding="utf-8")
        handled = set(re.findall(r"state == C\.(CON_\w+)", text))
        self.assertEqual(handled, set(lobby.STATES.values()))
        self.assertEqual({t[0] for t in lobby.TARGETS} | {"ansi"}, set(lobby.STATES))

    def test_each_case_stops_at_its_own_step(self):
        for label, steps, stop in lobby.TARGETS:
            with self.subTest(label=label):
                self.assertEqual(label, stop)
                self.assertIn(stop, [step for step, _, _ in steps])

    def test_walk_answers_up_to_the_target_and_stops_there(self):
        s = FakeSession(["Name: ...right, Bob (Y/N)?", "Give me a password", "Retype password", "What is your race"])
        lobby.walk(s, lobby.NEW, "race", "Lobbyaa", "By what name do you wish to be known?")
        self.assertEqual(s.sent, ["Lobbyaa", "y", lobby.PASSWORD, lobby.PASSWORD])

    def test_walk_fails_when_a_prompt_never_comes(self):
        with self.assertRaises(Fail):
            lobby.walk(FakeSession(["Illegal name, try another."]), lobby.NEW, "race", "X", "By what name")

    def test_names_are_letters_and_distinct(self):
        gen = lobby.names()
        names = [next(gen) for _ in range(600)]
        self.assertEqual(len(set(names)), 600)
        self.assertTrue(all(n.isalpha() and len(n) <= 12 for n in names))

    def test_a_case_that_went_down_is_a_finding(self):
        recs = [{"case": "sex/empty", "game": "Python", "up": False, "why": "exit status 1"},
                {"case": "(log)", "game": "Python", "up": True, "bugs": []}]
        self.assertEqual(lobby.report(recs), 1)
        self.assertEqual(lobby.report([dict(recs[0], up=True), recs[1]]), 0)


class ChurnTest(unittest.TestCase):
    def test_bot_names_are_letters_distinct_and_short(self):
        bots = [churn.Bot(n, 0, None, None, []) for n in range(6)]
        names = [b.name(k) for b in bots for k in range(0, 26 ** 4, 997)]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(n.isalpha() and len(n) <= 12 for n in names))
        self.assertNotEqual(bots[0].name(1), bots[0].name(1 + 26 ** 3))  # distinct for 26^4 quits per bot

    def test_going_down_or_bot_errors_are_findings(self):
        rec = {"game": "C", "quits": 3, "errors": [], "down": None, "bugs": [], "tail": []}
        self.assertEqual(churn.report(rec), 0)
        self.assertEqual(churn.report(dict(rec, down="exit status 139 (SIGSEGV)")), 1)
        self.assertEqual(churn.report(dict(rec, errors=["bot 0: timed out"])), 1)


class GamesTest(unittest.TestCase):
    def test_bug_lines_drop_the_timestamp(self):
        log = "Sat Nov 21 10:00:00 2026 :: [*****] BUG: Fix_exits: 1:2 -> 3.\nnot a bug\n"
        self.assertEqual(bug_lines(log), ["BUG: Fix_exits: 1:2 -> 3."])


if __name__ == "__main__":
    unittest.main()
