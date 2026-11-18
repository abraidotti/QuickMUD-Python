"""charm_tools port scenarios: play scenario files through both games and compare every line (#35).

The scenarios are game/tests/data/scenarios/NAME.scn. The C side is tools/oracle/scenario.c, built in the game's
build-stage image against the game's own object files (as port world's worldcheck is), linked with
-Wl,--wrap=random so the random numbers are counted. The Python side is charm.testing.scenario. Both run from a
copy of the area directory with the fixture players (tools/fixtures/player) and qmconfig.rc.

    python -m charm_tools port scenarios --docker charm:build           # compare live
    python -m charm_tools port scenarios --docker charm:build --save    # and write NAME.golden for the tests

Without --docker, the Python side is compared with the saved goldens (as the game's unit tests do).
A golden starts with a line naming the hash of the C sources it came from, so a stale one shows.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..paths import find_root, game_dir, use_game

BUILD = r"""
set -e
cd /opt/charm/src
gcc -O -g3 -Wall -std=gnu17 -fcommon -Dmain=game_main -c -o /tmp/comm_nomain.o comm.c 2>/dev/null
gcc -O -g3 -Wall -std=gnu17 -fcommon -I. -o /tmp/scenario /oracle/scenario.c -Wl,--wrap=random \
    $(ls obj/*.o | grep -v '^obj/comm\.o$') /tmp/comm_nomain.o -lcrypt
mkdir -p /opt/charm/notes /opt/charm/log /opt/charm/player /opt/charm/gods
cp /fixtures/player/* /opt/charm/player/
cp /fixtures/qmconfig.rc /opt/charm/area/qmconfig.rc
cd /opt/charm/area
/tmp/scenario
"""
TIMEOUT = 300  # seconds for one scenario on either side (fail fast: a stuck one shows)


def scenario_dir(root: Path | None = None) -> Path:
    return game_dir(root) / "tests" / "data" / "scenarios"


def source_hash(root: Path | None = None) -> str:
    """A hash of the C game's sources and the driver, which a golden records (charm.testing.scenario's)."""
    root = root or find_root()
    use_game(root)
    from charm.testing.scenario import source_hash as game_source_hash
    return game_source_hash(root)


def c_play(image: str, text: str, root: Path | None = None) -> list[str]:
    root = root or find_root()
    cmd = ["docker", "run", "--rm", "-i", "--entrypoint", "sh",
           "-v", f"{root / 'tools' / 'oracle'}:/oracle:ro", "-v", f"{root / 'tools' / 'fixtures'}:/fixtures:ro",
           image, "-c", BUILD]
    out = subprocess.run(cmd, input=text.encode("latin-1"), capture_output=True, timeout=TIMEOUT)
    if out.returncode != 0:
        raise RuntimeError(f"scenario failed in {image}:\n{out.stderr.decode('latin-1').strip()[-2000:]}")
    return out.stdout.decode("latin-1").splitlines()


def py_play(text: str, root: Path | None = None) -> list[str]:
    """The Python side, from a throwaway copy of area/ with the fixture players (save writes player files)."""
    root = root or find_root()
    use_game(root)
    from charm.testing.scenario import play_fresh
    return play_fresh(text, root)


def first_difference(a: list[str], b: list[str]) -> str | None:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            step = next((a[j] for j in range(i, -1, -1) if a[j].startswith("step ")), "(before the first step)")
            return f"line {i + 1}, at {step}:\n    C:      {x[:300]}\n    Python: {y[:300]}"
    if len(a) != len(b):
        more = (a if len(a) > len(b) else b)[min(len(a), len(b))]
        return f"{len(a)} lines from C, {len(b)} from Python; the longer goes on with: {more[:300]}"
    return None


def run(image: str | None, save: bool = False, only: str | None = None) -> int:
    root = find_root()
    files = sorted(scenario_dir(root).glob("*.scn"))
    if only:
        files = [f for f in files if only.lower() in f.stem.lower()]
    if not files:
        print("no scenarios")
        return 2
    digest = source_hash(root)
    failed = 0
    for f in files:
        text = f.read_text(encoding="latin-1")
        golden_path = f.with_suffix(".golden")
        if image:
            c = c_play(image, text, root)
            if save:
                golden_path.write_text(f"sources {digest}\n" + "\n".join(c) + "\n", encoding="latin-1",
                                       newline="\n")
        else:
            if not golden_path.exists():
                print(f"MISSING   {f.stem}: no golden; run with --docker IMAGE --save")
                failed += 1
                continue
            lines = golden_path.read_text(encoding="latin-1").splitlines()
            if lines[0] != f"sources {digest}":
                print(f"STALE     {f.stem}: the golden is from other C sources ({lines[0]}); rerun with --save")
            c = lines[1:]
        py = py_play(text, root)
        from charm.testing.scenario import comparable
        diff = first_difference(comparable(c), py)
        steps = sum(1 for x in c if x.startswith("step "))
        print(f"{'SAME' if diff is None else 'DIFFERENT':9} {f.stem} ({steps} steps, {len(c)} lines)", flush=True)
        if diff:
            print("    " + diff)
            failed += 1
    print("all the same" if not failed else f"{failed} scenario(s) differ")
    return 1 if failed else 0
