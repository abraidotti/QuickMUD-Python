"""Load the whole world the way boot_db does: every file in area.lst, in order, then fix_exits and fix_mobprogs.

Adapted from xania-explorer 90cfc79 areafile/world.py. The checks Xania's version made by itself (dangling
references, bad resets) are part of the boot here, because ROM makes them fatal during boot_db.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .boot import Boot, Counts
from .lookups import LookupTables
from .model import AreaFile, AreaHeader, Mob, MobProg, Obj, Reset, Room, Shop
from .reader import AreaParseError, Diagnostic, Reader


@dataclass
class World:
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
    areas: list[AreaHeader] = field(default_factory=list)  # in load order, as the C's area list
    shops: dict[int, Shop] = field(default_factory=dict)  # keeper vnum -> shop
    mobprogs: dict[int, MobProg] = field(default_factory=dict)
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


# C: db.c boot_db [partial]
def load_world(area_dir: Path, tables: LookupTables | None = None) -> World:
    """Boot every area in area.lst. A fatal condition stops the boot, as in the game: the World is returned with
    ``fatal`` set and holds what was loaded before it.

    [partial]: this is boot_db's area loading only. The rest of boot_db (time and weather, skill numbers, the first
    area_update, notes, bans and songs) comes with the parts of the game that use it."""
    tables = tables or LookupTables.from_data()
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
    return World(area_dir, names, boot.files, boot.rooms, boot.mobs, boot.objects, boot.room_resets,
                 set(boot.shop_of), boot.counts, boot.diagnostics, tables, boot.areas, dict(boot.shop_of),
                 boot.mobprogs, fatal, unlisted)
