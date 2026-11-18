"""handler.c's functions that move characters and objects about, and apply affects: the ones resets reach.

Several are [partial]. Each unported branch raises NotPorted instead of doing something else. These are the PC-only
branch (the wield-weight check in affect_modify), the ones that need spells (plague spreading in char_to_room),
and unequip_char, which nothing reaches yet. A boot never reaches them; the differential check would fail if it
did. equip_char's anti-alignment zap is ported: boot reaches it, and its act() messages reach nobody.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/handler.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, int32, sh_int
from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.net.act import act
from charm.data import constants as C
from charm.entities.game import Game, WeatherInfo
from charm.entities.things import Char, Obj
from charm.world.index import Affect, ObjIndex, Room
from charm.world.lookup import skill_lookup


def is_affected(ch: Char, bit: int) -> bool:
    """IS_AFFECTED."""
    return bool(ch.affected_by & bit)


def is_obj_stat(obj: Obj, bit: int) -> bool:
    """IS_OBJ_STAT."""
    return bool(obj.extra_flags & bit)


def weight_mult(obj: Obj) -> int:
    """WEIGHT_MULT: a container's value[4] percent, else 100."""
    return obj.value[4] if obj.item_type == C.ITEM_CONTAINER else 100


# C: handler.c get_obj_number
def get_obj_number(obj: Obj) -> int:
    number = 0 if obj.item_type in (C.ITEM_CONTAINER, C.ITEM_MONEY, C.ITEM_GEM, C.ITEM_JEWELRY) else 1
    for o in obj.contains:
        number += get_obj_number(o)
    return int32(number)


# C: handler.c get_obj_weight
def get_obj_weight(obj: Obj) -> int:
    weight = obj.weight
    for t in obj.contains:
        weight += c_div(get_obj_weight(t) * weight_mult(obj), 100)
    return int32(weight)


# C: handler.c get_eq_char
def get_eq_char(ch: Char | None, wear: int) -> Obj | None:
    if ch is None:
        return None
    for obj in ch.carrying:
        if obj.wear_loc == wear:
            return obj
    return None


_SET_FIELD = {C.TO_AFFECTS: "affected_by", C.TO_IMMUNE: "imm_flags", C.TO_RESIST: "res_flags",
              C.TO_VULN: "vuln_flags"}
_STAT = {C.APPLY_STR: C.STAT_STR, C.APPLY_DEX: C.STAT_DEX, C.APPLY_INT: C.STAT_INT, C.APPLY_WIS: C.STAT_WIS,
         C.APPLY_CON: C.STAT_CON}
_NOTHING = {C.APPLY_NONE, C.APPLY_CLASS, C.APPLY_LEVEL, C.APPLY_AGE, C.APPLY_HEIGHT, C.APPLY_WEIGHT, C.APPLY_GOLD,
            C.APPLY_EXP, C.APPLY_SPELL_AFFECT}
_SAVES = {C.APPLY_SAVES, C.APPLY_SAVING_ROD, C.APPLY_SAVING_PETRI, C.APPLY_SAVING_BREATH, C.APPLY_SAVING_SPELL}


# C: handler.c affect_modify [partial]
def affect_modify(ch: Char, paf: Affect, add: bool) -> None:
    """[partial]: the wield-weight check at the end is for players only, and isn't ported."""
    mod = paf.modifier
    name = _SET_FIELD.get(paf.where)
    if add:
        if name:
            setattr(ch, name, getattr(ch, name) | paf.bitvector)
    else:
        if name:
            setattr(ch, name, getattr(ch, name) & ~paf.bitvector)
        mod = -mod
    loc = paf.location
    if loc in _STAT:
        ch.mod_stat[_STAT[loc]] = sh_int(ch.mod_stat[_STAT[loc]] + mod)
    elif loc in _NOTHING:
        pass
    elif loc == C.APPLY_SEX:
        ch.sex = sh_int(ch.sex + mod)
    elif loc == C.APPLY_MANA:
        ch.max_mana = sh_int(ch.max_mana + mod)
    elif loc == C.APPLY_HIT:
        ch.max_hit = sh_int(ch.max_hit + mod)
    elif loc == C.APPLY_MOVE:
        ch.max_move = sh_int(ch.max_move + mod)
    elif loc == C.APPLY_AC:
        for i in range(4):
            ch.armor[i] = sh_int(ch.armor[i] + mod)
    elif loc == C.APPLY_HITROLL:
        ch.hitroll = sh_int(ch.hitroll + mod)
    elif loc == C.APPLY_DAMROLL:
        ch.damroll = sh_int(ch.damroll + mod)
    elif loc in _SAVES:
        ch.saving_throw = sh_int(ch.saving_throw + mod)
    else:
        bug("Affect_modify: unknown location %d.", loc)
        return
    if not ch.is_npc and get_eq_char(ch, C.WEAR_WIELD) is not None:
        raise NotPorted("handler.c affect_modify: a player's wield-weight check")


# C: handler.c affect_to_char
def affect_to_char(ch: Char, paf: Affect) -> None:
    new = paf.copy()
    ch.affected.insert(0, new)
    affect_modify(ch, new, True)


# C: handler.c affect_to_obj
def affect_to_obj(obj: Obj, paf: Affect) -> None:
    obj.affected.insert(0, paf.copy())
    if paf.bitvector:
        if paf.where == C.TO_OBJECT:
            obj.extra_flags = int32(obj.extra_flags | paf.bitvector)
        elif paf.where == C.TO_WEAPON and obj.item_type == C.ITEM_WEAPON:
            obj.value[4] = int32(obj.value[4] | paf.bitvector)


# C: handler.c char_to_room [partial]
def char_to_room(ch: Char, room: Room) -> None:
    """[partial]: a NULL room (sent to the temple) and plague spreading to the room aren't ported."""
    if room is None:
        raise NotPorted("handler.c char_to_room: NULL room")
    ch.in_room = room
    room.people.insert(0, ch)
    if not ch.is_npc:
        if room.area.empty:
            room.area.empty = False
            room.area.age = 0
        room.area.nplayer = sh_int(room.area.nplayer + 1)
    obj = get_eq_char(ch, C.WEAR_LIGHT)
    if obj is not None and obj.item_type == C.ITEM_LIGHT and obj.value[2] != 0:
        room.light = sh_int(room.light + 1)
    if is_affected(ch, C.AFF_PLAGUE):
        # Without a plague affect the bit is just cleared, which is what a mob made with AFF_PLAGUE gets.
        if not any(af.type == skill_lookup("plague") for af in ch.affected):  # gsn_plague
            ch.affected_by &= ~C.AFF_PLAGUE
            return
        raise NotPorted("handler.c char_to_room: plague spreading")


# C: handler.c obj_to_char
def obj_to_char(obj: Obj, ch: Char) -> None:
    ch.carrying.insert(0, obj)
    obj.carried_by = ch
    obj.in_room = None
    obj.in_obj = None
    ch.carry_number = sh_int(ch.carry_number + get_obj_number(obj))
    ch.carry_weight = sh_int(ch.carry_weight + get_obj_weight(obj))


# C: handler.c obj_from_char [partial]
def obj_from_char(obj: Obj) -> None:
    """[partial]: taking off worn equipment (unequip_char) isn't ported."""
    ch = obj.carried_by
    if ch is None:
        bug("Obj_from_char: null ch.", 0)
        return
    if obj.wear_loc != C.WEAR_NONE:
        raise NotPorted("handler.c obj_from_char: unequip_char")
    for i, o in enumerate(ch.carrying):
        if o is obj:
            del ch.carrying[i]
            break
    else:
        bug("Obj_from_char: obj not in list.", 0)
    obj.carried_by = None
    ch.carry_number = sh_int(ch.carry_number - get_obj_number(obj))
    ch.carry_weight = sh_int(ch.carry_weight - get_obj_weight(obj))


# C: handler.c obj_to_obj
def obj_to_obj(obj: Obj, obj_to: Obj) -> None:
    obj_to.contains.insert(0, obj)
    obj.in_obj = obj_to
    obj.in_room = None
    obj.carried_by = None
    if obj_to.index.vnum == C.OBJ_VNUM_PIT:
        obj.cost = 0
    o = obj_to
    while o is not None:
        if o.carried_by is not None:
            c = o.carried_by
            c.carry_number = sh_int(c.carry_number + get_obj_number(obj))
            c.carry_weight = sh_int(c.carry_weight + c_div(get_obj_weight(obj) * weight_mult(o), 100))
        o = o.in_obj


# C: handler.c obj_to_room
def obj_to_room(obj: Obj, room: Room) -> None:
    room.contents.insert(0, obj)
    obj.in_room = room
    obj.carried_by = None
    obj.in_obj = None


_AC_MULT = {C.WEAR_BODY: 3, C.WEAR_HEAD: 2, C.WEAR_LEGS: 2, C.WEAR_FEET: 1, C.WEAR_HANDS: 1, C.WEAR_ARMS: 1,
            C.WEAR_SHIELD: 1, C.WEAR_NECK_1: 1, C.WEAR_NECK_2: 1, C.WEAR_ABOUT: 2, C.WEAR_WAIST: 1,
            C.WEAR_WRIST_L: 1, C.WEAR_WRIST_R: 1, C.WEAR_HOLD: 1}


# C: handler.c apply_ac
def apply_ac(obj: Obj, wear: int, kind: int) -> int:
    if obj.item_type != C.ITEM_ARMOR:
        return 0
    return int32(_AC_MULT.get(wear, 0) * obj.value[kind])


def is_good(ch: Char) -> bool:
    return ch.alignment >= 350


def is_evil(ch: Char) -> bool:
    return ch.alignment <= -350


# C: handler.c equip_char [partial]
def equip_char(ch: Char, obj: Obj, wear: int) -> None:
    """[partial]: the anti-alignment zap needs act(), which isn't ported."""
    if get_eq_char(ch, wear) is not None:
        bug("Equip_char: already equipped (%d).", wear)
        return
    if ((is_obj_stat(obj, C.ITEM_ANTI_EVIL) and is_evil(ch))
            or (is_obj_stat(obj, C.ITEM_ANTI_GOOD) and is_good(ch))
            or (is_obj_stat(obj, C.ITEM_ANTI_NEUTRAL) and not is_good(ch) and not is_evil(ch))):
        # "Thanks to Morgenes for the bug fix here!"
        act("You are zapped by $p and drop it.", ch, obj, None, C.TO_CHAR)
        act("$n is zapped by $p and drops it.", ch, obj, None, C.TO_ROOM)
        obj_from_char(obj)
        obj_to_room(obj, ch.in_room)
        return
    for i in range(4):
        ch.armor[i] = sh_int(ch.armor[i] - apply_ac(obj, wear, i))
    obj.wear_loc = wear
    if not obj.enchanted:
        for paf in obj.index.affected:
            if paf.location != C.APPLY_SPELL_AFFECT:
                affect_modify(ch, paf, True)
    for paf in list(obj.affected):
        if paf.location == C.APPLY_SPELL_AFFECT:
            affect_to_char(ch, paf)
        else:
            affect_modify(ch, paf, True)
    if obj.item_type == C.ITEM_LIGHT and obj.value[2] != 0 and ch.in_room is not None:
        ch.in_room.light = sh_int(ch.in_room.light + 1)


# C: handler.c count_obj_list
def count_obj_list(index: ObjIndex, objs: list[Obj]) -> int:
    return sum(1 for o in objs if o.index is index)


# C: handler.c get_obj_type
def get_obj_type(game: Game, index: ObjIndex) -> Obj | None:
    for obj in game.object_list:
        if obj.index is index:
            return obj
    return None


# C: handler.c room_is_dark
def room_is_dark(room: Room, weather: WeatherInfo) -> bool:
    if room.light > 0:
        return False
    if room.room_flags & C.ROOM_DARK:
        return True
    if room.sector_type in (C.SECT_INSIDE, C.SECT_CITY):
        return False
    return weather.sunlight in (C.SUN_SET, C.SUN_DARK)
