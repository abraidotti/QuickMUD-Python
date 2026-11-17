"""Parity: does the Python loader agree with the real game?

Boots a throwaway container from a Charm image, logs in as the immortal fixture, runs ``memory`` (db.c
do_memory) and reads the boot log's bug() lines, then compares both with ``load_world()`` on this checkout.
The image should be built from the same checkout, or the comparison means nothing.

A saved capture (tools/fixtures/boot/) lets the unit tests make the same comparison without Docker.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, fields
from pathlib import Path

from .areafile.boot import Counts
from .areafile.world import World

# The memory command's labels, mapped to Counts fields.
MEMORY_LINES = {
    "Affects": "affects", "Areas": "areas", "ExDes": "extra_descr", "Exits": "exits", "Helps": "helps",
    "Socials": "socials", "Resets": "resets", "Rooms": "rooms", "Shops": "shops",
}
_MOBS = re.compile(r"^Mobs\s+(\d+)\((\d+) new format\)", re.M)
_OBJS = re.compile(r"^Objs\s+(\d+)\((\d+) new format\)", re.M)
_TIMESTAMP = re.compile(r"^\w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4} :: ")


def parse_memory(text: str) -> Counts:
    text = text.replace("\r", "")  # the game ends lines with \n\r
    c = Counts()
    for label, attr in MEMORY_LINES.items():
        m = re.search(rf"^{label}\s+(\d+)", text, re.M)
        if not m:
            raise ValueError(f"no '{label}' line in the memory output")
        setattr(c, attr, int(m.group(1)))
    for rx, total, new in ((_MOBS, "mobs", "mobs_new"), (_OBJS, "objects", "objects_new")):
        m = rx.search(text)
        if not m:
            raise ValueError(f"no '{total}' line in the memory output")
        setattr(c, total, int(m.group(1)))
        setattr(c, new, int(m.group(2)))
    return c


def bug_lines(log: str) -> list[str]:
    """The bug() lines of a boot log, without timestamps, up to the end of boot ("ROM is ready to rock")."""
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


def capture(image: str, timeout: float = 10.0) -> tuple[str, str]:
    """(memory output, boot log) from a throwaway container."""
    from ..sim import smoke

    port = smoke.free_port()
    container = f"charm-parity-{port}"
    smoke.docker("create", "--init", "--name", container, "-p", f"127.0.0.1:{port}:4000", image)
    try:
        name, pw = smoke.IMMORTAL
        smoke.docker("cp", str(smoke.FIXTURES / "player" / name), f"{container}:/opt/charm/player/{name}")
        smoke.docker("cp", str(smoke.FIXTURES / "qmconfig.rc"), f"{container}:/opt/charm/area/qmconfig.rc")
        smoke.docker("start", container)
        s = smoke.connect("127.0.0.1", port, timeout, 30)
        try:
            smoke.old_character(s, name, pw)
            s.send("memory")
            memory = s.expect(r"Perms\s+\d+ blocks")
        finally:
            s.close()
        log = smoke.docker("exec", container, "sh", "-c", "cat /opt/charm/log/*.log").stdout
        return memory, log
    finally:
        smoke.docker("rm", "-f", container, check=False)


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


def capture_case(image: str, area_dir: Path, case: Path, timeout: float = 20.0) -> str:
    """Boot a throwaway container with the case file added to area.lst; return the first run's log once the boot
    has finished (ready, or stopped by a fatal error)."""
    import tempfile
    import time

    from ..sim import smoke

    port = smoke.free_port()
    container = f"charm-parity-case-{port}"
    smoke.docker("create", "--init", "--name", container, image)
    try:
        smoke.docker("cp", str(case), f"{container}:/opt/charm/area/{case.name}")
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "area.lst"
            lst.write_text(area_list_with(area_dir, case.name), encoding="latin-1", newline="\n")
            smoke.docker("cp", str(lst), f"{container}:/opt/charm/area/area.lst")
        smoke.docker("start", container)
        deadline, last, stable_since = time.monotonic() + timeout, None, time.monotonic()
        while time.monotonic() < deadline:
            log = smoke.docker("exec", container, "sh", "-c", "cat /opt/charm/log/1000.log 2>/dev/null",
                               check=False).stdout
            if "is ready to rock" in log:
                return log
            if log != last:
                last, stable_since = log, time.monotonic()
            elif log and time.monotonic() - stable_since > 2:  # stopped writing: a fatal exit (or a crash)
                return log
            time.sleep(0.5)
        raise TimeoutError(f"{case.name}: the boot didn't finish within {timeout}s")
    finally:
        smoke.docker("rm", "-f", container, check=False)


def save_capture(memory: str, log: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "memory.txt").write_text(memory.replace("\r", ""), encoding="latin-1", newline="\n")
    (directory / "boot-bugs.txt").write_text("\n".join(bug_lines(log)) + "\n", encoding="latin-1", newline="\n")


def print_report(rep: Report) -> None:
    for name, exp, act in rep.count_diffs:
        print(f"  DIFF  {name}: game {exp}, charm_tools {act}")
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


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "version"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
