"""Parity: does the loader agree with what the C game printed?

tools/fixtures/boot/ holds captures from the C game, made before cut-over (the c-final tag has the live capture):
its ``memory`` totals (db.c do_memory) and its boot log's bug() lines for the stock world, and the bug() lines for
each deliberately broken area in cases/. This compares them with ``load_world()`` and the Python game's boot on this
checkout.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, fields
from pathlib import Path

from .world import Counts, World

# The memory command's labels, mapped to Counts fields.
MEMORY_LINES = {
    "Affects": "affects", "Areas": "areas", "ExDes": "extra_descr", "Exits": "exits", "Helps": "helps",
    "Socials": "socials", "Resets": "resets", "Rooms": "rooms", "Shops": "shops",
}
_MOBS = re.compile(r"^Mobs\s+(\d+)\((\d+) new format\)", re.M)
_OBJS = re.compile(r"^Objs\s+(\d+)\((\d+) new format\)", re.M)
_STRINGS = re.compile(r"^Strings\s+(\d+) strings of\s+(\d+) bytes", re.M)
_TIMESTAMP = re.compile(r"^\w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4} :: ")


def parse_memory(text: str) -> Counts:
    text = text.replace("\r", "")  # the game ends lines with \n\r
    c = Counts()
    for label, attr in MEMORY_LINES.items():
        m = re.search(rf"^{label}\s+(\d+)", text, re.M)
        if not m:
            raise ValueError(f"no '{label}' line in the memory output")
        setattr(c, attr, int(m.group(1)))
    for rx, total, new in ((_MOBS, "mobs", "mobs_new"), (_OBJS, "objects", "objects_new"),
                           (_STRINGS, "strings", "string_bytes")):
        m = rx.search(text)
        if not m:
            raise ValueError(f"no '{total}' line in the memory output")
        setattr(c, total, int(m.group(1)))
        setattr(c, new, int(m.group(2)))
    return c


def bug_lines(log: str) -> list[str]:
    """The bug() lines of a boot log, without timestamps, up to the end of boot ("QuickMUD-Python is ready to rock")."""
    out = []
    for line in log.splitlines():
        line = _TIMESTAMP.sub("", line)
        if "is ready to rock" in line:
            break
        if line.startswith("[*****]"):
            out.append(line)
    return out


@dataclass
class Report:
    expected: Counts
    actual: Counts
    expected_bugs: list[str]
    actual_bugs: list[str]

    @property
    def count_diffs(self) -> list[tuple[str, int, int]]:
        return [(f.name, getattr(self.expected, f.name), getattr(self.actual, f.name)) for f in fields(Counts)
                if f.name != "mobprogs" and getattr(self.expected, f.name) != getattr(self.actual, f.name)]

    @property
    def ok(self) -> bool:
        return not self.count_diffs and self.expected_bugs == self.actual_bugs


def compare(world: World, memory_text: str, log_text: str) -> Report:
    return Report(parse_memory(memory_text), world.counts, bug_lines(log_text), world.log_lines())


def area_list_with(area_dir: Path, extra: str) -> str:
    """area.lst with one more file added just before the closing '$'."""
    lines = (area_dir / "area.lst").read_text(encoding="latin-1").splitlines()
    end = next(i for i, line in enumerate(lines) if line.strip().startswith("$"))
    return "\n".join([*lines[:end], extra, *lines[end:]]) + "\n"


def case_area_dir(area_dir: Path, case: Path, tmp: Path) -> Path:
    """A copy of area/ with the case file added at the end of area.lst."""
    out = tmp / "area"
    out.mkdir()
    for p in area_dir.iterdir():
        if p.is_file() and p.name != "area.lst":
            shutil.copyfile(p, out / p.name)
    shutil.copyfile(case, out / case.name)
    (out / "area.lst").write_text(area_list_with(area_dir, case.name), encoding="latin-1", newline="\n")
    return out


def game_boot_bugs(area_dir: Path) -> list[str]:
    """The bug() lines of the Python game's whole boot (quickmud.entities.boot.boot_db) from area_dir, ending with the
    fatal one if the boot stops. That's the area loader's lines (World.log_lines) and then what comes after it, as
    in the game's log: convert_objects for old-format areas, and the first area_update's resets."""
    from quickmud.core import log
    from quickmud.entities.boot import BootFailed, boot_db

    for d in ("notes", "player", "gods", "log"):  # the boot reads (and save_notes writes) next to area/
        (area_dir.parent / d).mkdir(exist_ok=True)
    with log.capture() as lines:
        try:
            boot_db(area_dir)
        except BootFailed:
            pass
    return [line for line in lines if line.startswith("[*****]")]


def print_report(rep: Report) -> None:
    for name, exp, act in rep.count_diffs:
        print(f"  DIFF  {name}: game {exp}, quickmud_tools {act}")
    if not rep.count_diffs:
        print(f"  ok    counts: {len(fields(Counts)) - 1} totals equal the game's 'memory'")
    if rep.expected_bugs == rep.actual_bugs:
        print(f"  ok    bug() lines: the same {len(rep.actual_bugs)}, in the same order")
    else:
        print("  DIFF  bug() lines:")
        for line in rep.expected_bugs:
            print(f"          game   {line}")
        for line in rep.actual_bugs:
            print(f"          tools  {line}")
    print("PARITY" if rep.ok else "MISMATCH")
