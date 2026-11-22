"""The RNG port against the C game's own numbers (game/tests/data/rng.json, captured before cut-over).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import hashlib
import json
import unittest
from pathlib import Path

from quickmud.core import rng

FIXTURE = json.loads((Path(__file__).parent / "data" / "rng.json").read_text(encoding="utf-8"))


def quiet(line):
    pass


def pairs(args):
    return [tuple(int(x) for x in a.split(",")) for a in args]


def draw(name, args, count):
    """The same draws the C capture made (rngcheck.c, at c-final): each draw's arguments cycle through args."""
    if name == "random":
        return [rng.random() for _ in range(count)]
    if name in ("number_mm", "number_percent", "number_door"):
        f = getattr(rng, name)
        return [f() for _ in range(count)]
    if name in ("number_range", "dice"):
        f, ps = getattr(rng, name), pairs(args)
        return [f(*ps[i % len(ps)]) for i in range(count)]
    if name in ("number_bits", "number_fuzzy"):
        f, xs = getattr(rng, name), [int(a) for a in args]
        return [f(xs[i % len(xs)]) for i in range(count)]
    raise ValueError(f"unknown stream {name}")


class MatchesTheCGame(unittest.TestCase):
    def test_every_stream_on_every_seed(self):
        count = FIXTURE["count"]
        self.assertEqual(count, 10_000)
        self.assertEqual(sorted(FIXTURE["seeds"]), sorted(["0", "1", "1763400000", "4294967295"]))
        for seed, streams in FIXTURE["seeds"].items():
            self.assertEqual(len(streams), 8)
            for name, want in streams.items():
                with self.subTest(seed=seed, stream=name):
                    # rngcheck reseeds through init_mm and QUICKMUD_SEED before each stream, so this does too.
                    rng.init_mm({"QUICKMUD_SEED": seed}, log=quiet)
                    got = draw(name, want["args"], count)
                    self.assertEqual(got[: len(want["first"])], want["first"])
                    self.assertEqual(hashlib.sha256(" ".join(map(str, got)).encode()).hexdigest(), want["sha256"])


class InitMm(unittest.TestCase):
    def seed(self, value):
        lines = []
        got = rng.init_mm({} if value is None else {"QUICKMUD_SEED": value}, log=lines.append)
        return got, lines

    def test_charm_seed_is_used_and_logged(self):
        self.assertEqual(self.seed("42"), (42, ["Random seed: 42 (QUICKMUD_SEED)"]))
        self.assertEqual(self.seed("4294967295")[0], 4294967295)

    def test_zero_gives_the_same_numbers_as_one(self):
        rng.init_mm({"QUICKMUD_SEED": "0"}, log=quiet)
        a = [rng.random() for _ in range(5)]
        rng.init_mm({"QUICKMUD_SEED": "1"}, log=quiet)
        self.assertEqual(a, [rng.random() for _ in range(5)])

    def test_bad_values_fall_back_to_the_clock(self):
        for bad in ("-1", "4294967296", "12x", "x"):
            with self.subTest(value=bad):
                _, lines = self.seed(bad)
                self.assertIn("isn't a number from 0 to 4294967295; using the clock.", lines[0])
                self.assertRegex(lines[1], r"^Random seed: \d+ \(clock\)$")

    def test_unset_uses_the_clock(self):
        _, lines = self.seed(None)
        self.assertRegex(lines[0], r"^Random seed: \d+ \(clock\)$")


if __name__ == "__main__":
    unittest.main()
