"""mem.c: OLC's constructors for new prototypes: areas, rooms, exits, resets, objects, mobs and shops. (A mob
program's code is a new entry in the index's mprog_code; the free_* functions only give memory back.)

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mem.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.world.index import Area, Exit, ExtraDescr, MobIndex, ObjIndex, Reset, Room, Shop


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


# C: mem.c new_obj_index
def new_obj_index(area) -> ObjIndex:
    """A blank object prototype (its level, which the C doesn't set, is fresh memory's 0)."""
    return ObjIndex(vnum=0, area=area, name="no name", short_descr="(no short description)",
                    description="(no description)", material="unknown", item_type=C.ITEM_TRASH, extra_flags=0,
                    wear_flags=0, value=[0, 0, 0, 0, 0], level=0, weight=0, cost=0, condition=100)


# C: mem.c new_mob_index
def new_mob_index(area) -> MobIndex:
    """A blank mob prototype: a human, standing, medium-sized (the C sets damage's number twice and not its bonus,
    which is fresh memory's 0 anyway)."""
    from charm.world.lookup import race_lookup

    return MobIndex(vnum=0, area=area, player_name="no name", short_descr="(no short description)",
                    long_descr="(no long description)\n\r", description="", race=race_lookup("human"),
                    act=C.ACT_IS_NPC, affected_by=0, alignment=0, group=0, level=0, hitroll=0, hit=(0, 0, 0),
                    mana=(0, 0, 0), damage=(0, 0, 0), dam_type=0, ac=(0, 0, 0, 0), off_flags=0, imm_flags=0,
                    res_flags=0, vuln_flags=0, start_pos=C.POS_STANDING, default_pos=C.POS_STANDING, sex=0,
                    wealth=0, form=0, parts=0, size=C.SIZE_MEDIUM, material="unknown")


# C: mem.c new_shop
def new_shop() -> Shop:
    return Shop(keeper=0, buy_type=(0,) * C.MAX_TRADE, profit_buy=100, profit_sell=100, open_hour=0, close_hour=23)
