"""The old area formats (#MOBOLD and #OBJOLD), made new.

load_old_mob and load_old_obj come in two halves, as load_mobiles and load_objects do: charm.world.areafile.boot
reads (OldMob, OldObj), and the functions here make the prototypes, which charm.world.index.build_index is given.
They live here, not in charm.world, because they need the game's one_argument, is_name and slot_lookup.

convert_mobile runs as each old-format mob is made, and draws a random number for its damage type, so the boot
draws once for each, in load order, as the C does while loading. convert_objects runs once every area has loaded:
it makes up each old-format object's level from the resets, then converts it (convert_object). Once the boot is
over every prototype is new-format, as in the C. No stock area is in the old format;
tools/fixtures/files/oldformat.are is.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/db2.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.cint import c_div, int32, sh_int
from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.core.rng import number_range
from charm.data import constants as C
from charm.data.races import RACE_TABLE
from charm.entities.handler import interpolate, is_name
from charm.systems.magic import slot_lookup
from charm.world import lookup
from charm.world.areafile.model import OldMob, OldObj
from charm.world.index import Affect, Area, ExtraDescr, Index, MobIndex, ObjIndex, _lower_first, _s, _upper_first

_BLANK_OFF = C.OFF_DODGE | C.OFF_DISARM | C.OFF_TRIP | C.ASSIST_VNUM
_BLANK_FORM = C.FORM_EDIBLE | C.FORM_SENTIENT | C.FORM_BIPED | C.FORM_MAMMAL
_BLANK_PARTS = C.PART_HEAD | C.PART_ARMS | C.PART_LEGS | C.PART_HEART | C.PART_BRAINS | C.PART_GUTS


# C: db.c load_old_mob
def old_mob_index(m: OldMob, area: Area) -> MobIndex:
    """The prototype load_old_mob leaves (areafile.boot's _load_old_mob is the reading): the race from the first
    keyword ("compute the race BS"), its flags set rather than ORed, then convert_mobile's dice, which draw a random
    number."""
    _, name = one_argument(m.keywords)
    race = lookup.race_lookup(name) if name else 0
    if race == 0:  # "fill in with blanks"
        race = lookup.race_lookup("human")
        off, imm, res, vuln, form, parts = _BLANK_OFF, 0, 0, 0, _BLANK_FORM, _BLANK_PARTS
    else:
        rt = RACE_TABLE[race]
        off = C.OFF_DODGE | C.OFF_DISARM | C.OFF_TRIP | C.ASSIST_RACE | rt.off
        imm, res, vuln, form, parts = rt.imm, rt.res, rt.vuln, rt.form, rt.parts
    p = MobIndex(
        vnum=m.vnum, area=area, player_name=_s(m.keywords), short_descr=_s(m.short_descr),
        long_descr=_upper_first(_s(m.long_descr)), description=_upper_first(_s(m.description)), race=race,
        act=m.act | C.ACT_IS_NPC, affected_by=m.affected_by, alignment=sh_int(m.alignment), group=0,
        level=sh_int(m.level), hitroll=0, hit=(0, 0, 0), mana=(0, 0, 0), damage=(0, 0, 0), dam_type=0,
        ac=(0, 0, 0, 0), off_flags=off, imm_flags=imm, res_flags=res, vuln_flags=vuln, start_pos=m.start_pos,
        default_pos=m.default_pos, sex=m.sex, wealth=m.wealth, form=form, parts=parts, size=0, material=None,
        new_format=False)
    convert_mobile(p)
    return p



# C: db.c load_old_obj
def old_obj_index(o: OldObj, area: Area) -> ObjIndex:
    """The prototype load_old_obj leaves (areafile.boot's _load_old_obj is the reading). It stays old-format, with
    level 0, until convert_objects."""
    v = list(o.values)
    if o.item_type == C.ITEM_WEAPON and (is_name("two", o.keywords) or is_name("two-handed", o.keywords)
                                         or is_name("claymore", o.keywords)):
        v[4] |= C.WEAPON_TWO_HANDS
    if o.item_type == C.ITEM_ARMOR:  # "fix armors"
        v[1] = v[0]
        v[2] = v[1]
    if o.item_type in (C.ITEM_PILL, C.ITEM_POTION, C.ITEM_SCROLL):
        v[1:5] = [slot_lookup(x) for x in v[1:5]]
    elif o.item_type in (C.ITEM_STAFF, C.ITEM_WAND):
        v[3] = slot_lookup(v[3])
    return ObjIndex(
        vnum=o.vnum, area=area, name=_s(o.keywords), short_descr=_lower_first(_s(o.short_descr)),
        description=_upper_first(_s(o.description)), material="", item_type=sh_int(o.item_type),
        extra_flags=int32(o.extra_flags), wear_flags=int32(o.wear_flags), value=[int32(x) for x in v], level=0,
        weight=sh_int(o.weight), cost=int32(o.cost), condition=100,
        affected=[Affect(C.TO_OBJECT, -1, 20, -1, sh_int(a.location), sh_int(a.modifier), 0)  # "RT temp fix"
                  for a in o.affects],
        extra_descr=[ExtraDescr(_s(e.keywords), _s(e.description)) for e in o.extra_descr], new_format=False)


def _divide(a: int, b: int, where: str) -> int:
    """a / b, where b can come out 0 for a negative level: the C divides by zero (SIGFPE)."""
    if b == 0:
        raise CWouldCrash(f"db2.c {where}: divides by zero (a level below 0 makes the dice count 0)")
    return c_div(a, b)


# C: db2.c convert_mobile
def convert_mobile(p: MobIndex | None) -> None:
    """Hit, mana and damage dice, armour, wealth and the rest made up from the level (load_old_mob calls it). The
    damage type is a random draw, so the boot draws once for each old-format mob, in load order."""
    if p is None or p.new_format:
        return
    level = p.level
    p.act |= C.ACT_WARRIOR

    # "Calculate hit dice. Gives close to the hitpoints of old format mobs created with create_mobile() (db.c)"
    type_ = c_div(int32(level * level * 27), 40)
    number = min(c_div(type_, 40) + 1, 10)  # "how do they get 11 ???"
    type_ = max(2, _divide(type_, number, "convert_mobile"))
    bonus = int32(level * (8 + level)) * .9 - int32(number * type_)  # UMAX (0, ...) on a double, then an int
    bonus = int(bonus) if bonus > 0 else 0
    p.hit = (sh_int(number), sh_int(type_), sh_int(bonus))
    p.mana = (sh_int(level), 10, 100)

    # "Calculate dam dice. Gives close to the damage of old format mobs in damage() (fight.c)"
    type_ = c_div(level * 7, 4)
    number = min(c_div(type_, 8) + 1, 5)
    type_ = max(2, _divide(type_, number, "convert_mobile"))
    bonus = max(0, c_div(level * 9, 4) - number * type_)
    p.damage = (sh_int(number), sh_int(type_), sh_int(bonus))

    p.dam_type = {1: 3, 2: 7, 3: 11}[number_range(1, 3)]  # slash, pound, pierce
    p.ac = tuple(sh_int(interpolate(level, 100, -100)) for _ in range(3)) + (sh_int(interpolate(level, 100, 0)),)
    p.wealth = c_div(p.wealth, 100)
    p.size = C.SIZE_MEDIUM
    p.material = "none"
    p.new_format = True  # ++newmobs: charm.world.areafile.boot counts it as the mob loads


_SHOP_FLOOR = {C.ITEM_PILL: 5, C.ITEM_POTION: 5, C.ITEM_SCROLL: 10, C.ITEM_ARMOR: 10, C.ITEM_WEAPON: 10,
               C.ITEM_WAND: 15, C.ITEM_TREASURE: 15, C.ITEM_STAFF: 20}  # any other type: 0


# C: db2.c convert_objects
def convert_objects(index: Index, top) -> None:
    """Each old-format object's level, from the mob or container its resets put it with, then convert_object on
    each. ``top`` is the game's counts (newobjs is top.objects_new). "This function is not pretty.. Sorry about
    that :)" (Hugin): the last mob seen carries over from room to room and area to area, as in the C.

    Most of its bug() lines can't happen: fix_exits has already stopped the boot on a reset whose arg1 isn't there,
    and a 'G' or 'E' reset always follows an 'M' (load_resets puts it in that mob's room). A 'P' reset's container
    (arg3) isn't checked, and an 'O' before any 'M' has no mob."""
    if top.objects_new == top.objects:
        return  # "all objects in new format"
    mob = None
    for area in index.areas:
        for vnum in range(area.min_vnum, area.max_vnum + 1):
            room = index.get_room_index(vnum)
            if room is None:
                continue
            for rs in room.resets:
                cmd = rs.command
                if cmd == "M":
                    mob = index.get_mob_index(rs.arg1)
                    if mob is None:
                        bug("Convert_objects: 'M': bad vnum %d.", rs.arg1)
                elif cmd == "O":
                    obj = index.get_obj_index(rs.arg1)
                    if obj is None:
                        bug("Convert_objects: 'O': bad vnum %d.", rs.arg1)
                    elif obj.new_format:
                        pass
                    elif mob is None:
                        bug("Convert_objects: 'O': No mob reset yet.", 0)
                    else:
                        obj.level = sh_int(mob.level - 2 if obj.level < 1 else min(obj.level, mob.level - 2))
                elif cmd == "P":
                    obj = index.get_obj_index(rs.arg1)
                    if obj is None:
                        bug("Convert_objects: 'P': bad vnum %d.", rs.arg1)
                        continue
                    if obj.new_format:
                        continue
                    to = index.get_obj_index(rs.arg3)
                    if to is None:
                        bug("Convert_objects: 'P': bad vnum %d.", rs.arg3)
                        continue
                    obj.level = sh_int(to.level if obj.level < 1 else min(obj.level, to.level))
                elif cmd in ("G", "E"):
                    obj = index.get_obj_index(rs.arg1)
                    if obj is None:
                        bug("Convert_objects: 'E' or 'G': bad vnum %d.", rs.arg1)
                    elif mob is None:  # before the new_format test, so a new-format object logs it too
                        bug("Convert_objects: 'E' or 'G': null mob for vnum %d.", rs.arg1)
                    elif obj.new_format:
                        pass
                    elif mob.shop is not None:
                        obj.level = sh_int(max(_SHOP_FLOOR.get(obj.item_type, 0), obj.level))
                    else:
                        obj.level = sh_int(mob.level if obj.level < 1 else min(obj.level, mob.level))

    # "do the conversion:"
    for area in index.areas:
        for vnum in range(area.min_vnum, area.max_vnum + 1):
            obj = index.get_obj_index(vnum)
            if obj is not None and not obj.new_format:
                convert_object(obj, top)


_AS_IS = {C.ITEM_LIGHT, C.ITEM_TREASURE, C.ITEM_FURNITURE, C.ITEM_TRASH, C.ITEM_CONTAINER, C.ITEM_DRINK_CON,
          C.ITEM_KEY, C.ITEM_FOOD, C.ITEM_BOAT, C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC, C.ITEM_FOUNTAIN, C.ITEM_MAP,
          C.ITEM_CLOTHING, C.ITEM_SCROLL, C.ITEM_POTION, C.ITEM_PILL}


# C: db2.c convert_object
def convert_object(p: ObjIndex | None, top) -> None:
    """An old-format object's cost and values made up from its level (convert_objects calls it)."""
    if p is None or p.new_format:
        return
    level = p.level
    p.level = sh_int(max(0, p.level))  # "just to be sure"
    p.cost = int32(10 * level)
    t = p.item_type
    v = p.value
    if t in _AS_IS:
        pass
    elif t in (C.ITEM_WAND, C.ITEM_STAFF):
        v[2] = v[1]
    elif t == C.ITEM_WEAPON:
        # the dice one_hit (fight.c) would roll, a little wider: 1d8 at level 1 up to 5d11 at 50
        number = min(c_div(level, 4) + 1, 5)
        v[1] = number
        v[2] = _divide(level + 7, number, "convert_object")
    elif t == C.ITEM_ARMOR:
        v[0] = c_div(level, 5) + 3
        v[1] = v[0]
        v[2] = v[0]
    elif t == C.ITEM_MONEY:
        v[0] = p.cost
    else:
        bug("Obj_convert: vnum %d bad type.", p.item_type)  # the C prints the type, not the vnum
    p.new_format = True
    top.objects_new += 1
