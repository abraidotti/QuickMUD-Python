"""The explore commands: areas, check, parity."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from .. import paths
from . import checks, parity
from .world import Counts, World, load_world

FIXTURE_DIR = paths.find_root() / "tools" / "fixtures" / "boot"


def _fatal_line(w: World) -> None:
    if w.fatal:
        print(f"FATAL {w.fatal}")
        print("      (boot_db stops here; everything after it is missing from the totals)")


def areas() -> int:
    """Per-area counts, the totals as the game's 'memory' prints them, and the boot's bug() lines."""
    w = load_world()
    rows = []
    for f in w.files:
        rows.append((f.filename, f.name if f.header else "-", len(f.rooms), len(f.mobs), len(f.objects),
                     len(f.resets), len(f.shops), len(f.helps), len(f.socials)))
    head = ("file", "area", "rooms", "mobs", "objs", "resets", "shops", "helps", "socials")
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    widths[1] = min(widths[1], 28)
    fmt = "  ".join(f"{{:{'<' if i < 2 else '>'}{w}}}" for i, w in enumerate(widths))
    print(fmt.format(*head))
    for r in rows:
        print(fmt.format(r[0], str(r[1])[:28], *r[2:]))
    c = w.counts
    print()
    print("totals, as the game's 'memory' command prints them:")
    print(f"  Affects {c.affects:5}  Areas {c.areas:5}  ExDes {c.extra_descr:5}  Exits {c.exits:5}  "
          f"Helps {c.helps:5}  Socials {c.socials:5}")
    print(f"  Mobs {c.mobs:5}({c.mobs_new} new format)  Objs {c.objects:5}({c.objects_new} new format)  "
          f"Resets {c.resets:5}  Rooms {c.rooms:5}  Shops {c.shops:5}")
    print()
    lines = w.log_lines()
    print(f"bug() lines at boot: {len(lines)}")
    for line in lines:
        print(f"  {line}")
    _fatal_line(w)
    return 1 if w.fatal else 0


def check() -> int:
    """The T1 data checks. Exit 0 whatever they find (findings aren't failures); 1 only if the world won't boot."""
    w = load_world()
    for r in checks.run(w):
        print(f"{'clean' if r.clean else len(r.occurrences):>5}  {r.id}: {r.title}")
        for o in r.occurrences:
            where = f"  [{o.where}]" if o.where else ""
            print(f"         {o.what}: {o.detail}{where}")
        if r.not_checked:
            print(f"         not checked: {r.not_checked}")
    _fatal_line(w)
    return 1 if w.fatal else 0


def run_parity() -> int:
    """Compare load_world() with the C game's capture in tools/fixtures/boot."""
    w = load_world()
    memory = (FIXTURE_DIR / "memory.txt").read_text(encoding="latin-1")
    log = (FIXTURE_DIR / "boot-bugs.txt").read_text(encoding="latin-1")
    print(f"charm_tools vs the C game's capture in {FIXTURE_DIR.relative_to(paths.find_root())}:")
    rep = parity.compare(w, memory, log)
    parity.print_report(rep)
    _fatal_line(w)
    cases_ok = run_cases()
    return 0 if rep.ok and cases_ok else 1


CASES_DIR = FIXTURE_DIR / "cases"


def run_cases() -> bool:
    """Each broken area in tools/fixtures/boot/cases, added to the end of area.lst: the C game's bug() lines (saved
    next to the case as <case>.log) must equal the Python game's boot's (parity.game_boot_bugs)."""
    import tempfile

    area_dir = paths.area_dir()
    all_ok = True
    print()
    print("broken-area and old-format cases (each added to the end of area.lst):")
    for case in sorted(CASES_DIR.glob("*.are")):
        saved = case.with_suffix(".log")
        expected = saved.read_text(encoding="latin-1").splitlines() if saved.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            actual = parity.game_boot_bugs(parity.case_area_dir(area_dir, case, Path(tmp)))
        ok = expected == actual
        all_ok &= ok
        tail = expected[-1] if expected else "(no capture)"
        print(f"  {'ok  ' if ok else 'DIFF'}  {case.stem:<16} {tail}")
        if not ok:
            for line in expected or []:
                print(f"          game   {line}")
            for line in actual:
                print(f"          tools  {line}")
    return all_ok


__all__ = ["areas", "check", "run_parity", "Counts", "fields"]
