"""Load the whole world the way boot_db does: every file in area.lst, in order, then fix_exits and fix_mobprogs.

Adapted from xania-explorer 90cfc79 areafile/world.py. The checks Xania's version made by itself (dangling
references, bad resets) are part of the boot here, because ROM makes them fatal during boot_db.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ... import paths
from ..source.ctables import LookupTables
from .boot import Boot, Counts
from .model import AreaFile, Mob, Obj, Reset, Room
from .reader import AreaParseError, Diagnostic, Reader


@dataclass
class World:
    root: Path
    area_dir: Path
    area_list: list[str]  # file names, in area.lst order
    files: list[AreaFile]
    rooms: dict[int, Room]
    mobs: dict[int, Mob]
    objects: dict[int, Obj]
    room_resets: dict[int, list[Reset]]
    shop_keepers: set[int]
    counts: Counts
    diagnostics: list[Diagnostic]
    tables: LookupTables
    fatal: AreaParseError | None = None  # set if boot_db would have stopped; the world is then partial
    unlisted: list[str] = field(default_factory=list)  # *.are files on disk that area.lst doesn't name

    def log_lines(self) -> list[str]:
        """The bug() lines a real boot prints, in order (no timestamps), ending with the fatal one if any."""
        out = [line for d in self.diagnostics for line in d.log_lines()]
        return out + (self.fatal.log if self.fatal else [])

    @property
    def resets(self) -> list[Reset]:
        return [rs for f in self.files for rs in f.resets]


def read_area_list(area_dir: Path) -> list[str]:
    """area.lst as boot_db reads it: fread_word until a word starting with '$'."""
    r = Reader.from_path(area_dir / "area.lst")
    names = []
    while True:
        word = r.read_word()
        if word.startswith("$"):
            return names
        names.append(word)


def load_world(root: Path | None = None, area_dir: Path | None = None) -> World:
    """Boot every area in area.lst. A fatal condition stops the boot, as in the game: the World is returned with
    ``fatal`` set and holds what was loaded before it. ``area_dir`` boots another copy of area/ (for tests)."""
    root = root or paths.find_root()
    area_dir, src_dir = area_dir or paths.area_dir(root), paths.src_dir(root)
    tables = LookupTables.from_source(src_dir)
    boot = Boot(tables)
    names = read_area_list(area_dir)
    fatal = None
    try:
        for name in names:
            if name == "-":
                raise AreaParseError("area.lst names '-' (read an area from stdin): not modelled", "area.lst")
            path = area_dir / name
            if not path.is_file():
                raise AreaParseError(f"{name}: No such file or directory (boot_db: perror, exit 1)", "area.lst",
                                     log=[f"{name}: No such file or directory"])
            boot.load_file(path, name)
        boot.finish()
    except AreaParseError as e:
        fatal = e
    listed = set(names)
    unlisted = sorted(p.name for p in area_dir.glob("*.are") if p.name not in listed)
    return World(root, area_dir, names, boot.files, boot.rooms, boot.mobs, boot.objects, boot.room_resets,
                 set(boot.shop_of), boot.counts, boot.diagnostics, tables, fatal, unlisted)
