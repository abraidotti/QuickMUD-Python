"""charm_tools port rng: capture the C game's random-number streams, for game/tests/test_rng.py.

The C side is tools/oracle/rngcheck.c, built in the game's build-stage image against the game's own object files
(comm.c compiled with -Dmain=game_main). Each stream is reseeded through init_mm and CHARM_SEED. The committed
fixture (game/tests/data/rng.json) keeps, for every seed and stream, how the arguments cycle, the first 100 values
and a SHA-256 of all of them, so everyday tests need no Docker.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from ..paths import find_root, game_dir

SEEDS = ("0", "1", "1763400000", "4294967295")
COUNT = 10_000
FIRST = 100

BUILD = r"""
set -e
cd /opt/charm/src
gcc -O -g3 -Wall -std=gnu17 -fcommon -Dmain=game_main -c -o /tmp/comm_nomain.o comm.c
gcc -O -g3 -Wall -std=gnu17 -fcommon -I. -o /tmp/rngcheck /oracle/rngcheck.c \
    $(ls obj/*.o | grep -v '^obj/comm\.o$') /tmp/comm_nomain.o -lcrypt
/tmp/rngcheck "$@"
"""


def fixture_path(root: Path | None = None) -> Path:
    return game_dir(root) / "tests" / "data" / "rng.json"


def digest(values: list[int]) -> str:
    return hashlib.sha256(" ".join(map(str, values)).encode()).hexdigest()


def parse(text: str, count: int) -> dict:
    """rngcheck's stdout -> {"count", "seeds": {seed: {stream: {"args", "first", "sha256"}}}}."""
    seeds: dict = {}
    lines = text.splitlines()
    for head, vals in zip(lines[0::2], lines[1::2]):
        _, seed, name, *args = head.split()
        assert vals.startswith("values"), vals
        values = [int(v) for v in vals.split()[1:]]
        if len(values) != count:
            raise ValueError(f"seed {seed} {name}: {len(values)} values, expected {count}")
        seeds.setdefault(seed, {})[name] = {
            "args": [] if args == ["-"] else args,
            "first": values[:FIRST],
            "sha256": digest(values),
        }
    return {"count": count, "seeds": seeds}


def capture(image: str, root: Path | None = None, count: int = COUNT) -> dict:
    root = root or find_root()
    oracle = root / "tools" / "oracle"
    cmd = ["docker", "run", "--rm", "-v", f"{oracle}:/oracle:ro", image, "sh", "-c", BUILD, "rngcheck",
           str(count), *SEEDS]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"rngcheck failed in {image}:\n{out.stderr.strip()}")
    return parse(out.stdout, count)


def compare(a: dict, b: dict) -> list[str]:
    """Differences between two captures, as readable lines (empty if they agree)."""
    diffs = []
    if a["count"] != b["count"]:
        diffs.append(f"count {a['count']} vs {b['count']}")
    for seed in sorted(set(a["seeds"]) | set(b["seeds"])):
        sa, sb = a["seeds"].get(seed, {}), b["seeds"].get(seed, {})
        for name in sorted(set(sa) | set(sb)):
            x, y = sa.get(name), sb.get(name)
            if x is None or y is None:
                diffs.append(f"seed {seed} {name}: only in one capture")
            elif x != y:
                at = next((i for i, (p, q) in enumerate(zip(x["first"], y["first"])) if p != q), None)
                where = f"first difference at draw {at}" if at is not None else "differs after the first values"
                diffs.append(f"seed {seed} {name}: {where}")
    return diffs


def run(image: str, save: bool) -> int:
    path = fixture_path()
    print(f"capturing {len(SEEDS)} seeds x {COUNT} draws per stream from the C game in {image}...", flush=True)
    try:
        got = capture(image)
    except (OSError, RuntimeError) as e:
        print(f"couldn't capture: {e}")
        return 2
    streams = sum(len(s) for s in got["seeds"].values())
    if save:
        path.write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"saved {streams} streams to {path}")
        return 0
    if not path.exists():
        print(f"no fixture at {path}; run with --save to create it")
        return 1
    diffs = compare(json.loads(path.read_text(encoding="utf-8")), got)
    for d in diffs:
        print(f"  differs  {d}")
    print("SAME as the fixture" if not diffs else f"{len(diffs)} stream(s) differ from the fixture")
    return 0 if not diffs else 1
