"""charm_tools port crypt: glibc's crypt() against the Python game's, for game/tests/data/crypt.json (#30).

The cases are made here from a fixed seed, so they're the same every run:
- keys of 0 to 12 characters (DES crypt uses the first 8), made of letters, digits, punctuation, control bytes
  and bytes with the top bit set (it uses 7 bits of each)
- every salt character at least once, in each place
tools/oracle/cryptcheck.c runs them through glibc in the build-stage image. The fixture keeps the cases and
glibc's answers, so the game's test needs no Docker.
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from ..paths import find_root, game_dir, use_game

COUNT = 2000
BUILD = r"""
set -e
gcc -O -Wall -o /tmp/cryptcheck /oracle/cryptcheck.c -lcrypt
/tmp/cryptcheck
"""


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


def capture(image: str, root: Path | None = None) -> list[str]:
    root = root or find_root()
    oracle = root / "tools" / "oracle"
    text = "".join(f"{k.encode('latin-1').hex()} {s}\n" if k else f" {s}\n" for k, s in cases())
    cmd = ["docker", "run", "--rm", "-i", "-v", f"{oracle}:/oracle:ro", image, "sh", "-c", BUILD]
    run = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="latin-1")
    if run.returncode != 0:
        raise RuntimeError(f"cryptcheck failed in {image}:\n{run.stderr.strip()[-2000:]}")
    return run.stdout.splitlines()


def compare(expected: list[list[str]]) -> list[str]:
    use_game()
    from charm.core.crypt import crypt
    diffs = []
    for key, salt, want in expected:
        got = crypt(key, salt)
        if got != want:
            diffs.append(f"crypt({key!r}, {salt!r}): glibc {want}, Python {got}")
    return diffs


def run(image: str | None, save: bool) -> int:
    path = fixture_path()
    if image:
        try:
            hashes = capture(image)
        except (OSError, RuntimeError) as e:
            print(f"couldn't run the C side: {e}")
            return 2
        expected = [[k, s, h] for (k, s), h in zip(cases(), hashes)]
        if len(hashes) != len(cases()):
            print(f"glibc gave {len(hashes)} answers for {len(cases())} cases")
            return 1
        if save:
            path.write_text(json.dumps(expected, indent=0) + "\n", encoding="utf-8", newline="\n")
            print(f"saved {len(expected)} cases to {path}")
    else:
        expected = json.loads(path.read_text(encoding="utf-8"))
    diffs = compare(expected)
    for d in diffs[:10]:
        print(f"  differs  {d}")
    print(f"{len(expected)} cases: " + ("SAME as glibc" if not diffs else f"{len(diffs)} differ"))
    return 1 if diffs else 0
