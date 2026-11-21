"""mem.c: OLC's constructors for new prototypes: areas, and the room editor's rooms, exits and resets. The object,
mob, shop and mob program ones come with the editors that make them. (The free_* functions only give memory back.)

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mem.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.world.index import Area, Exit, ExtraDescr, Reset, Room


# C: mem.c new_area
def new_area(game) -> Area:
    """A new area, numbered top_area (the areas never shrink, so that's how many there are). area_free is never
    filled, so the area is always fresh memory: its vnum is still 0 when the file name is made, so every new area
    is "area0.are". Its credits are never set (NULL, printed "(null)")."""
    top_area = len(game.index.areas) + 1  # top_area++
    return Area(vnum=top_area - 1, file_name="area%d.are" % 0, name="New area", credits=None, min_vnum=0,
                max_vnum=0, security=1, builders="None", age=0, nplayer=0, empty=True, area_flags=C.AREA_ADDED)


# C: mem.c new_reset_data
def new_reset_data() -> Reset:
    return Reset("X", 0, 0, 0, 0)


# C: mem.c new_exit
def new_exit() -> Exit:
    return Exit(vnum=0, to_room=None, exit_info=0, rs_flags=0, key=0, keyword="", description="", orig_door=0)


# C: mem.c new_room_index
def new_room_index() -> Room:
    return Room(vnum=0, name="", description="", area=None, room_flags=0, sector_type=0)


# C: recycle.c new_extra_descr
def new_extra_descr() -> ExtraDescr:
    return ExtraDescr("", "")
