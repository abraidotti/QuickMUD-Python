"""Data checks on the loaded world (tools-port T1).

Ported from the format-neutral checks in xania-explorer 90cfc79 bugs/checks.py. Checks that point at Xania code
lines stay behind; their questions get asked again of ROM's code in later phases. Checks that need the T2/T3
models (unobtainable gear, mobs whose loot vanishes on save) come with those phases.

Each check reports what it found and what it didn't look at, so "nothing found" never reads as "fixed".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .areafile import graph
from .areafile.world import World


@dataclass
class Occurrence:
    what: str
    detail: str
    where: str = ""  # area name or file


@dataclass
class Result:
    id: str
    title: str
    kind: str  # "boot" (what the loader says), "data" (content), "info"
    occurrences: list[Occurrence] = field(default_factory=list)
    not_checked: str = ""  # what this check can't see

    @property
    def clean(self) -> bool:
        return not self.occurrences


def _boot_fatal(w: World) -> Result:
    r = Result("boot.fatal", "The game can't boot these areas", "boot")
    if w.fatal:
        r.occurrences.append(Occurrence(w.fatal.message, "boot_db stops here (exit 1, or a hang or crash)",
                                        f"{w.fatal.file}:{w.fatal.line}" if w.fatal.file else ""))
    return r


def _boot_bugs(w: World) -> Result:
    r = Result("boot.bug", "Warnings the game logs at boot (bug())", "boot")
    for d in w.diagnostics:
        r.occurrences.append(Occurrence(d.message, "logged, boot carries on", f"{d.file}:{d.line}" if d.file else ""))
    return r


def _unlisted(w: World) -> Result:
    return Result("area.unlisted", "Area files on disk that area.lst doesn't load", "info",
                  [Occurrence(n, "never loaded", f"area/{n}") for n in w.unlisted])


def _never_spawn(w: World) -> Result:
    """reset_room 'M' (db.c): a reset spawns nothing when its world limit (arg2) or room limit (arg4) is <= 0."""
    spawns: dict[int, bool] = {}
    for rs in w.resets:
        if rs.command == "M":
            spawns[rs.arg1] = spawns.get(rs.arg1, False) or (rs.arg2 > 0 and rs.arg4 > 0)
    r = Result("mob.never-spawns", "Mobs that no reset ever creates", "data",
               not_checked="mobs created by mobprogs (mpmload) or code (e.g. MOB_VNUM_*) aren't counted")
    code_mobs = set(w.tables.defines.with_prefix("MOB_VNUM_").values())
    for vnum, mob in sorted(w.mobs.items()):
        if spawns.get(vnum) or vnum in code_mobs:
            continue
        why = "every M reset for it has a limit <= 0" if vnum in spawns else "no M reset"
        r.occurrences.append(Occurrence(f"#{vnum} {mob.short_descr}", f"level {mob.level}; {why}",
                                        _area_of(w, mob.file)))
    return r


def _never_placed(w: World) -> Result:
    placed = {rs.arg1 for rs in w.resets if rs.command in ("O", "P", "G", "E")}
    code_objs = set(w.tables.defines.with_prefix("OBJ_VNUM_").values())
    r = Result("obj.never-placed", "Objects that no reset places", "data",
               not_checked="objects created by mobprogs (mpoload), spells or other code paths (only OBJ_VNUM_* "
                           "constants are excluded)")
    for vnum, obj in sorted(w.objects.items()):
        if vnum not in placed and vnum not in code_objs:
            r.occurrences.append(Occurrence(f"#{vnum} {obj.short_descr}", f"{obj.type_word}, level {obj.level}",
                                            _area_of(w, obj.file)))
    return r


def _unreachable(w: World) -> Result:
    d = w.tables.defines
    starts = (d["ROOM_VNUM_TEMPLE"], d["ROOM_VNUM_SCHOOL"])
    seen = graph.reachable(w, *starts)
    # A pet shop keeps its stock in the next room (act_obj.c do_buy/do_list: in_room->vnum + 1), which players
    # aren't meant to reach.
    pet_shop = d["ROOM_PET_SHOP"]
    storage = {v + 1 for v, room in w.rooms.items() if room.room_flags & pet_shop}
    r = Result("room.unreachable", "Rooms with no walking route from the temple or the mud school", "data",
               not_checked="portals, teleports, recall points other than the temple, and room restrictions "
                           "(see graph.py); pet-shop storage rooms (the room after a pet shop) are left out")
    for vnum, room in sorted(w.rooms.items()):
        if vnum not in seen and vnum not in storage:
            r.occurrences.append(Occurrence(f"#{vnum} {room.name}", "no route on foot", room.area))
    return r


def _area_of(w: World, filename: str) -> str:
    for f in w.files:
        if f.filename == filename:
            return f.name
    return filename


CHECKS = (_boot_fatal, _boot_bugs, _unlisted, _never_spawn, _never_placed, _unreachable)


def run(w: World) -> list[Result]:
    return [check(w) for check in CHECKS]
