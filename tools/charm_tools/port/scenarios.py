"""charm_tools port scenarios: play scenario files through the Python game and compare every line with its golden.

The scenarios are game/tests/data/scenarios/NAME.scn, and each NAME.golden is what the C game printed for it,
through tools/oracle/scenario.c at the c-final tag (#35; #112, decision 4). The Python side is
charm.testing.scenario, run from a copy of the area directory with the fixture players (tools/fixtures/player),
qmconfig.rc, and the files (tools/fixtures/files) that a scenario's @place lines put in place before boot.

    python -m charm_tools port scenarios                          # compare with the goldens
    python -m charm_tools port scenarios --save --only NAME       # after a deliberate change: save NAME's again

A golden's first line says where it came from: "c-final", or "python" once --save has written it from the Python
game. A deliberate change (a bug fix) saves the goldens it changes, and its PR shows the diff.
"""

from __future__ import annotations

from pathlib import Path

from ..paths import find_root, game_dir, use_game


def scenario_dir(root: Path | None = None) -> Path:
    return game_dir(root) / "tests" / "data" / "scenarios"


def golden_sources() -> tuple[str, ...]:
    use_game()
    from charm.testing.scenario import GOLDEN_SOURCES
    return GOLDEN_SOURCES


def py_play(text: str, root: Path | None = None) -> list[str]:
    """The Python side, from a throwaway copy of area/ with the fixture players (save writes player files)."""
    root = root or find_root()
    use_game(root)
    from charm.testing.scenario import play_fresh
    return play_fresh(text, root)


def difference(c: list[str], py: list[str], text: str = "") -> str | None:
    """charm.testing.scenario's comparison, which the game's tests use too."""
    use_game()
    from charm.testing.scenario import difference as game_difference
    return game_difference(c, py, text)


def run(save: bool = False, only: str | None = None) -> int:
    root = find_root()
    files = sorted(scenario_dir(root).glob("*.scn"))
    if only:
        files = [f for f in files if only.lower() in f.stem.lower()]
    if not files:
        print("no scenarios")
        return 2
    sources = golden_sources()
    failed = 0
    for f in files:
        text = f.read_text(encoding="latin-1")
        golden_path = f.with_suffix(".golden")
        py = py_play(text, root)
        if save:
            golden_path.write_text("python\n" + "\n".join(py) + "\n", encoding="latin-1", newline="\n")
            print(f"SAVED     {f.stem} ({len(py)} lines, from the Python game)", flush=True)
            continue
        if not golden_path.exists():
            print(f"MISSING   {f.stem}: no golden; save one with --save --only {f.stem}")
            failed += 1
            continue
        lines = golden_path.read_text(encoding="latin-1").splitlines()
        if lines[0] not in sources:
            print(f"UNKNOWN   {f.stem}: the golden's first line is {lines[0]!r}, not one of {', '.join(sources)}")
            failed += 1
            continue
        c = lines[1:]
        diff = difference(c, py, text)
        steps = sum(1 for x in c if x.startswith("step "))
        stop = " (stops on NotPorted, as expected)" if diff is None and py and py[-1].startswith("stopped") else ""
        print(f"{'SAME' if diff is None else 'DIFFERENT':9} {f.stem} ({steps} steps, {len(c)} lines){stop}",
              flush=True)
        if diff:
            print("    " + diff)
            failed += 1
    if save:
        print(f"saved {len(files)} golden(s); check the diff before committing")
        return 0
    print("all the same" if not failed else f"{failed} scenario(s) differ")
    return 1 if failed else 0
