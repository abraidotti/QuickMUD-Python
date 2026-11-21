"""mem.c: OLC's constructors for new prototypes. This PR has new_area; the room, exit, reset, object, mob, shop and
mob program ones come with the editors that make them.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mem.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.world.index import Area


# C: mem.c new_area
def new_area(game) -> Area:
    """A new area, numbered top_area (the areas never shrink, so that's how many there are). area_free is never
    filled, so the area is always fresh memory: its vnum is still 0 when the file name is made, so every new area
    is "area0.are". Its credits are never set (NULL, printed "(null)")."""
    top_area = len(game.index.areas) + 1  # top_area++
    return Area(vnum=top_area - 1, file_name="area%d.are" % 0, name="New area", credits=None, min_vnum=0,
                max_vnum=0, security=1, builders="None", age=0, nplayer=0, empty=True, area_flags=C.AREA_ADDED)
