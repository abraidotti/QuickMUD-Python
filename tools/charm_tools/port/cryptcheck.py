"""charm_tools port crypt: glibc's crypt() against the Python game's, for game/tests/data/crypt.json (#30).

The cases are made here from a fixed seed, so they're the same every run:
- keys of 0 to 12 characters (DES crypt uses the first 8), made of letters, digits, punctuation, control bytes
  and bytes with the top bit set (it uses 7 bits of each)
- every salt character at least once, in each place
Before cut-over, tools/oracle/cryptcheck.c (at the c-final tag) ran them through glibc. The fixture keeps the cases
and glibc's answers, and this compares the Python game's crypt with them.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..paths import game_dir, use_game

COUNT = 2000
def fixture_path(root: Path | None = None) -> Path:
    return game_dir(root) / "tests" / "data" / "crypt.json"


def cases(count: int = COUNT) -> list[tuple[str, str]]:
    from_alpha = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    rnd = random.Random(20261118)
    pool = [chr(c) for c in range(1, 256)]
    out = [("psswrd", "Sh"), ("", "Sh"), ("password", "ab"), ("passwordLONGER", "ab")]  # 8+ characters: same hash
    for a in from_alpha:  # every salt character, in both places
        out.append(("charm", a + "Z"))
        out.append(("charm", "Z" + a))
    while len(out) < count:
        n = rnd.randint(0, 12)
        if rnd.random() < 0.5:
            key = "".join(rnd.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in
                          range(n))
        else:
            key = "".join(rnd.choice(pool) for _ in range(n))
        out.append((key, rnd.choice(from_alpha) + rnd.choice(from_alpha)))
    return out


def compare(expected: list[list[str]]) -> list[str]:
    use_game()
    from charm.core.crypt import crypt
    diffs = []
    for key, salt, want in expected:
        got = crypt(key, salt)
        if got != want:
            diffs.append(f"crypt({key!r}, {salt!r}): glibc {want}, Python {got}")
    return diffs


def run() -> int:
    expected = json.loads(fixture_path().read_text(encoding="utf-8"))
    diffs = compare(expected)
    for d in diffs[:10]:
        print(f"  differs  {d}")
    print(f"{len(expected)} cases: " + ("SAME as glibc" if not diffs else f"{len(diffs)} differ"))
    return 1 if diffs else 0
