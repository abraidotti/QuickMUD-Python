"""The room graph: where you can walk from where.

Adapted from xania-explorer 90cfc79 areafile/graph.py. Every exit with a real destination counts as walkable,
doors included (closed doors open; locked ones need a key that this doesn't track). ROM's level and privacy
restrictions on rooms (IMP_ONLY, GODS_ONLY, HEROES_ONLY, NEWBIES_ONLY, private rooms) and portals aren't applied
yet: what they change is unknown here until T2 reads those rules.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .model import DIRECTIONS
from .world import World


@dataclass(frozen=True)
class Step:
    from_vnum: int
    direction: int
    to_vnum: int
    door: bool

    @property
    def command(self) -> str:
        return DIRECTIONS[self.direction]


def steps_from(world: World, vnum: int) -> list[Step]:
    room = world.rooms.get(vnum)
    if room is None:
        return []
    is_door = world.tables.defines["EX_ISDOOR"]
    return [Step(vnum, d, ex.to_vnum, bool(ex.rs_flags & is_door))
            for d, ex in sorted(room.exits.items()) if ex.to_vnum > 0 and ex.to_vnum in world.rooms]


def distances(world: World, *starts: int) -> dict[int, int]:
    """Steps from the nearest start to every room reachable on foot."""
    dist = {s: 0 for s in starts if s in world.rooms}
    queue = deque(dist)
    while queue:
        v = queue.popleft()
        for st in steps_from(world, v):
            if st.to_vnum not in dist:
                dist[st.to_vnum] = dist[v] + 1
                queue.append(st.to_vnum)
    return dist


def reachable(world: World, *starts: int) -> set[int]:
    return set(distances(world, *starts))
