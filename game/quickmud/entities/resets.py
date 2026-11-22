"""Resets: area_update ages the areas and resets them; reset_room runs a room's resets in order.

A line-by-line port of db.c, side effects included. In a 'P' reset the C assigns LastObj and count in the middle
of one condition and stops at the first test that fails, so the same happens here. And UMIN is a macro that
evaluates its argument twice, so ``UMIN(number_fuzzy(level), ...)`` usually draws two random numbers
(_umin_fuzzy).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div, sh_int
from quickmud.core.errors import CWouldCrash
from quickmud.core.log import bug, log_f
from quickmud.core.rng import number_fuzzy, number_range
from quickmud.data import constants as C
from quickmud.entities.create import create_mobile, create_object
from quickmud.entities.game import Game
from quickmud.entities.handler import (
    count_obj_list, equip_char, get_obj_type, obj_to_char, obj_to_obj, obj_to_room, room_is_dark,
    char_to_room,
)
from quickmud.entities.things import Char
from quickmud.net.wiznet import wiznet
from quickmud.world.index import Area, Room

REV_DIR = (2, 3, 0, 1, 5, 4)  # act_move.c rev_dir[]


def _urange(a: int, b: int, c: int) -> int:
    return a if b < a else (c if b > c else b)


def _umin_fuzzy(level: int) -> int:
    """``UMIN(number_fuzzy(level), LEVEL_HERO - 1)``, exactly as the macro expands: ``((a) < (b) ? (a) : (b))``
    evaluates ``a`` a second time when it's the smaller, so number_fuzzy draws twice and the second draw is the
    level. One draw only when the first is LEVEL_HERO - 1 or more."""
    cap = C.LEVEL_HERO - 1
    if number_fuzzy(level) < cap:
        return number_fuzzy(level)
    return cap


# C: db.c area_update
def area_update(game: Game) -> None:
    school = game.index.get_room_index(C.ROOM_VNUM_SCHOOL)
    for area in game.index.areas:
        area.age = sh_int(area.age + 1)
        if area.age < 3:
            continue
        if (not area.empty and (area.nplayer == 0 or area.age >= 15)) or area.age >= 31:
            reset_area(game, area)
            wiznet(game, f"{area.name} has just been reset.", None, None, C.WIZ_RESETS, 0, 0)
            area.age = number_range(0, 3)
            if school is not None and area is school.area:
                area.age = 15 - 2
            elif area.nplayer == 0:
                area.empty = True


# C: db.c reset_area
def reset_area(game: Game, area: Area) -> None:
    for vnum in range(area.min_vnum, area.max_vnum + 1):
        room = game.index.get_room_index(vnum)
        if room is not None:
            reset_room(game, room)


def _old_goods_level(p) -> int:
    """reset_room's level for a shopkeeper's old-format goods: from the lowest level any class gets each spell, or
    a random draw for wands, staves, armour, weapons and treasure."""
    from quickmud.data.skills import SKILL_TABLE

    t = p.item_type
    if t in (C.ITEM_PILL, C.ITEM_POTION, C.ITEM_SCROLL):
        olevel = 53
        for i in range(1, 5):
            sn = p.value[i]
            if sn > 0:
                if sn >= C.MAX_SKILL:
                    raise CWouldCrash(f"db.c reset_room: skill_table[{sn}] is past the array")
                for j in range(C.MAX_CLASS):  # the rows after the last skill are zeros
                    olevel = min(olevel, SKILL_TABLE[sn].skill_level[j] if sn < len(SKILL_TABLE) else 0)
        return max(0, c_div(olevel * 3, 4) - 2)
    if t == C.ITEM_WAND:
        return number_range(10, 20)
    if t == C.ITEM_STAFF:
        return number_range(15, 25)
    if t in (C.ITEM_ARMOR, C.ITEM_WEAPON):  # "ROM patch weapon, treasure"
        return number_range(5, 15)
    if t == C.ITEM_TREASURE:
        return number_range(10, 20)
    return 0


# C: db.c reset_room
def reset_room(game: Game, room: Room | None) -> None:
    """A shopkeeper's old-format goods take a level from the spell table or a random draw (never, after the boot:
    every prototype is new-format by then)."""
    if room is None:
        return
    index = game.index
    last_mob: Char | None = None
    level = 0
    last = False

    for i in range(C.MAX_DIR):
        ex = room.exit[i]
        if ex is not None:
            ex.exit_info = sh_int(ex.rs_flags)
            if ex.to_room is not None:
                rev = ex.to_room.exit[REV_DIR[i]]
                if rev is not None:  # nail the other side
                    rev.exit_info = sh_int(rev.rs_flags)

    for rs in room.resets:
        cmd = rs.command
        if cmd == "M":
            p = index.get_mob_index(rs.arg1)
            if p is None:
                bug("Reset_room: 'M': bad vnum %d.", rs.arg1)
                continue
            target = index.get_room_index(rs.arg3)
            if target is None:
                bug("Reset_area: 'R': bad vnum %d.", rs.arg3)
                continue
            if p.count >= rs.arg2:
                last = False
                continue
            count = 0
            for m in target.people:
                if m.index is p:
                    count += 1
                    if count >= rs.arg4:
                        last = False
                        break
            if count >= rs.arg4:
                continue
            mob = create_mobile(game, p)
            if room_is_dark(room, game.weather_info):  # "some more hard coding"
                mob.affected_by |= C.AFF_INFRARED
            prev = index.get_room_index(room.vnum - 1)  # pet shop mobiles get ACT_PET
            if prev is not None and prev.room_flags & C.ROOM_PET_SHOP:
                mob.act |= C.ACT_PET
            char_to_room(mob, room)
            last_mob = mob
            level = _urange(0, mob.level - 2, C.LEVEL_HERO - 1)
            last = True

        elif cmd == "O":
            p = index.get_obj_index(rs.arg1)
            if p is None:
                bug("Reset_room: 'O' 1 : bad vnum %d", rs.arg1)
                bug(f"{rs.arg1} {rs.arg2} {rs.arg3} {rs.arg4}", 1)
                continue
            if index.get_room_index(rs.arg3) is None:
                bug("Reset_room: 'O' 2 : bad vnum %d.", rs.arg3)
                bug(f"{rs.arg1} {rs.arg2} {rs.arg3} {rs.arg4}", 1)
                continue
            if room.area.nplayer > 0 or count_obj_list(p, room.contents) > 0:
                last = False
                continue
            obj = create_object(game, p, _umin_fuzzy(level))  # UMIN - ROM OLC
            obj.cost = 0
            obj_to_room(obj, room)
            last = True

        elif cmd == "P":
            p = index.get_obj_index(rs.arg1)
            if p is None:
                bug("Reset_room: 'P': bad vnum %d.", rs.arg1)
                continue
            to = index.get_obj_index(rs.arg3)
            if to is None:
                bug("Reset_room: 'P': bad vnum %d.", rs.arg3)
                continue
            if rs.arg2 > 50:  # old format
                limit = 6
            elif rs.arg2 == -1:  # no limit
                limit = 999
            else:
                limit = rs.arg2
            # The C's one condition, in its order: each test runs only if the ones before it passed.
            if room.area.nplayer > 0:
                last = False
                continue
            last_obj = get_obj_type(game, to)
            if last_obj is None or (last_obj.in_room is None and not last) or p.count >= limit:
                last = False
                continue
            count = count_obj_list(p, last_obj.contains)
            if count > rs.arg4:
                last = False
                continue
            while count < rs.arg4:
                obj = create_object(game, p, number_fuzzy(last_obj.level))
                obj_to_obj(obj, last_obj)
                count += 1
                if p.count >= limit:
                    break
            last_obj.value[1] = last_obj.index.value[1]  # fix object lock state!
            last = True

        elif cmd in ("G", "E"):
            p = index.get_obj_index(rs.arg1)
            if p is None:
                bug("Reset_room: 'E' or 'G': bad vnum %d.", rs.arg1)
                continue
            if not last:
                continue
            if last_mob is None:
                bug("Reset_room: 'E' or 'G': null mob for vnum %d.", rs.arg1)
                last = False
                continue
            if last_mob.index.shop is not None:  # shopkeeper
                obj = create_object(game, p, _old_goods_level(p) if not p.new_format else 0)
                obj.extra_flags |= C.ITEM_INVENTORY
            else:
                if rs.arg2 > 50:  # old format
                    limit = 6
                elif rs.arg2 in (-1, 0):  # no limit
                    limit = 999
                else:
                    limit = rs.arg2
                if p.count < limit or number_range(0, 4) == 0:
                    obj = create_object(game, p, _umin_fuzzy(level))
                    # error message if it is too high
                    if (obj.level > last_mob.level + 3
                            or (obj.item_type == C.ITEM_WEAPON and cmd == "E"
                                and obj.level < last_mob.level - 5 and obj.level < 45)):
                        log_f("Check Levels:")
                        log_f("  Object: (VNUM %5d)(Level %2d) %s", obj.index.vnum, obj.level, obj.short_descr)
                        log_f("     Mob: (VNUM %5d)(Level %2d) %s", last_mob.index.vnum, last_mob.level,
                              last_mob.short_descr)
                else:
                    continue
            obj_to_char(obj, last_mob)
            if cmd == "E":
                equip_char(last_mob, obj, rs.arg3)
            last = True

        elif cmd == "D":
            pass

        elif cmd == "R":
            target = index.get_room_index(rs.arg1)
            if target is None:
                bug("Reset_room: 'R': bad vnum %d.", rs.arg1)
                continue
            for d0 in range(rs.arg2 - 1):
                d1 = number_range(d0, rs.arg2 - 1)
                target.exit[d0], target.exit[d1] = target.exit[d1], target.exit[d0]

        else:
            bug("Reset_room: bad command %c.", cmd)
