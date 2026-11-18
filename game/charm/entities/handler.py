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
from charm.entities.game import weather as game_weather
from charm.entities.things import Char, Obj
from charm.world.index import Affect, ObjIndex, Room
from charm.data.attributes import STR_APP
from charm.data.classes import CLASS_TABLE
from charm.data.races import PC_RACE_TABLE
from charm.world.lookup import race_lookup, skill_lookup


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


_wield_depth = [0]  # affect_modify's static depth: guards against recursion (weapons with affects)


# C: handler.c affect_modify
def affect_modify(ch: Char, paf: Affect, add: bool) -> None:
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
    # LATER: sh_int(...) wraps are written out at every assignment; fields that wrap themselves (a descriptor
    # carrying the C width) would make a missed one impossible
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
    # Check for weapon wielding.
    wield = get_eq_char(ch, C.WEAR_WIELD) if not ch.is_npc else None
    if wield is not None and get_obj_weight(wield) > STR_APP[get_curr_stat(ch, C.STAT_STR)].wield * 10:
        if _wield_depth[0] == 0:
            _wield_depth[0] += 1
            act("You drop $p.", ch, wield, None, C.TO_CHAR)
            act("$n drops $p.", ch, wield, None, C.TO_ROOM)
            obj_from_char(wield)
            obj_to_room(wield, ch.in_room)
            _wield_depth[0] -= 1


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
    # LATER: lists with insert(0) keep the C's head-first order but are O(n); a deque, or a linked list like the
    # C's, once things leave the world (char_list, object_list, people, contents, carrying, contains)
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


# C: handler.c obj_from_char
def obj_from_char(obj: Obj) -> None:
    ch = obj.carried_by
    if ch is None:
        bug("Obj_from_char: null ch.", 0)
        return
    if obj.wear_loc != C.WEAR_NONE:
        unequip_char(ch, obj)
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
    # LATER: this scans every object, as the C does; an index of instances by prototype would make it O(1)
    for obj in game.object_list:
        if obj.index is index:
            return obj
    return None


# C: handler.c room_is_dark
def room_is_dark(room: Room, weather: WeatherInfo | None = None) -> bool:
    """weather is weather_info; without it, the current game's."""
    if weather is None:
        weather = game_weather()
    if room.light > 0:
        return False
    if room.room_flags & C.ROOM_DARK:
        return True
    if room.sector_type in (C.SECT_INSIDE, C.SECT_CITY):
        return False
    return weather.sunlight in (C.SUN_SET, C.SUN_DARK)


# C: handler.c get_trust
def get_trust(ch: Char) -> int:
    if ch.desc is not None and getattr(ch.desc, "original", None) is not None:
        ch = ch.desc.original
    if ch.trust:
        return ch.trust
    if ch.is_npc and ch.level >= C.LEVEL_HERO:
        return C.LEVEL_HERO - 1
    return ch.level


def is_immortal(ch: Char) -> bool:
    """IS_IMMORTAL."""
    return get_trust(ch) >= C.LEVEL_IMMORTAL


# C: handler.c can_see [partial]
def can_see(ch: Char, victim: Char) -> bool:
    """[partial]: seeing a sneaking character is a skill roll (get_skill, get_curr_stat), not ported yet."""
    if ch is victim:
        return True
    if get_trust(ch) < victim.invis_level:
        return False
    if get_trust(ch) < victim.incog_level and ch.in_room is not victim.in_room:
        return False
    if (not ch.is_npc and ch.act & C.PLR_HOLYLIGHT) or (ch.is_npc and is_immortal(ch)):
        return True
    if is_affected(ch, C.AFF_BLIND):
        return False
    if room_is_dark(ch.in_room) and not is_affected(ch, C.AFF_INFRARED):
        return False
    if is_affected(victim, C.AFF_INVISIBLE) and not is_affected(ch, C.AFF_DETECT_INVIS):
        return False
    if is_affected(victim, C.AFF_SNEAK) and not is_affected(ch, C.AFF_DETECT_HIDDEN) and victim.fighting is None:
        raise NotPorted("handler.c can_see: the roll to notice a sneaking character")
    if is_affected(victim, C.AFF_HIDE) and not is_affected(ch, C.AFF_DETECT_HIDDEN) and victim.fighting is None:
        return False
    return True


# C: handler.c can_see_obj
def can_see_obj(ch: Char, obj: Obj) -> bool:
    if not ch.is_npc and ch.act & C.PLR_HOLYLIGHT:
        return True
    if obj.extra_flags & C.ITEM_VIS_DEATH:
        return False
    if is_affected(ch, C.AFF_BLIND) and obj.item_type != C.ITEM_POTION:
        return False
    if obj.item_type == C.ITEM_LIGHT and obj.value[2] != 0:
        return True
    if obj.extra_flags & C.ITEM_INVIS and not is_affected(ch, C.AFF_DETECT_INVIS):
        return False
    if is_obj_stat(obj, C.ITEM_GLOW):
        return True
    if room_is_dark(ch.in_room) and not is_affected(ch, C.AFF_DARK_VISION):
        return False
    return True


# C: handler.c can_see_room
def can_see_room(ch: Char, room: Room) -> bool:
    if room.room_flags & C.ROOM_IMP_ONLY and get_trust(ch) < C.MAX_LEVEL:
        return False
    if room.room_flags & C.ROOM_GODS_ONLY and not is_immortal(ch):
        return False
    if room.room_flags & C.ROOM_HEROES_ONLY and not is_immortal(ch):
        return False
    if room.room_flags & C.ROOM_NEWBIES_ONLY and ch.level > 5 and not is_immortal(ch):
        return False
    if not is_immortal(ch) and room.clan and ch.clan != room.clan:
        return False
    return True


def pers(ch: Char, looker: Char) -> str:
    """PERS: what looker calls ch."""
    if can_see(looker, ch):
        return ch.short_descr if ch.is_npc else ch.name
    return "someone"


# C: handler.c get_curr_stat
def get_curr_stat(ch: Char, stat: int) -> int:
    if ch.is_npc or ch.level > C.LEVEL_IMMORTAL:
        top = 25
    else:
        top = PC_RACE_TABLE[ch.race].max_stats[stat] + 4
        if CLASS_TABLE[ch.class_].attr_prime == stat:
            top += 2
        if ch.race == race_lookup("human"):
            top += 1
        top = min(top, 25)
    value = ch.perm_stat[stat] + ch.mod_stat[stat]
    return 3 if value < 3 else (top if value > top else value)  # URANGE(3, value, max)


# C: handler.c unequip_char
def unequip_char(ch: Char, obj: Obj) -> None:
    if obj.wear_loc == C.WEAR_NONE:
        bug("Unequip_char: already unequipped.", 0)
        return
    for i in range(4):
        ch.armor[i] = sh_int(ch.armor[i] + apply_ac(obj, obj.wear_loc, i))
    obj.wear_loc = -1

    def remove_spell(paf: Affect, noisy: bool) -> None:
        for lpaf in list(ch.affected):
            if lpaf.type == paf.type and lpaf.level == paf.level and lpaf.location == C.APPLY_SPELL_AFFECT:
                if noisy:
                    bug("location = %d", lpaf.location)
                    bug("type = %d", lpaf.type)
                affect_remove(ch, lpaf)
                return  # "lpaf_next = NULL": only the first match goes

    if not obj.enchanted:
        for paf in obj.index.affected:
            if paf.location == C.APPLY_SPELL_AFFECT:
                remove_spell(paf, False)
            else:
                affect_modify(ch, paf, False)
                affect_check(ch, paf.where, paf.bitvector)
    for paf in list(obj.affected):
        if paf.location == C.APPLY_SPELL_AFFECT:
            bug("Norm-Apply: %d", 0)
            remove_spell(paf, True)
        else:
            affect_modify(ch, paf, False)
            affect_check(ch, paf.where, paf.bitvector)
    if obj.item_type == C.ITEM_LIGHT and obj.value[2] != 0 and ch.in_room is not None and ch.in_room.light > 0:
        ch.in_room.light = sh_int(ch.in_room.light - 1)


def _set_vector(ch: Char, where: int, vector: int) -> None:
    name = _SET_FIELD.get(where)
    if name:
        setattr(ch, name, getattr(ch, name) | vector)


# C: handler.c affect_check
def affect_check(ch: Char, where: int, vector: int) -> None:
    if where in (C.TO_OBJECT, C.TO_WEAPON) or vector == 0:
        return
    for paf in ch.affected:
        if paf.where == where and paf.bitvector == vector:
            _set_vector(ch, where, vector)
            return
    for obj in ch.carrying:
        if obj.wear_loc == -1:
            continue
        for paf in obj.affected:
            if paf.where == where and paf.bitvector == vector:
                _set_vector(ch, where, vector)
                return
        if obj.enchanted:
            continue
        for paf in obj.index.affected:
            if paf.where == where and paf.bitvector == vector:
                _set_vector(ch, where, vector)
                return


# C: handler.c affect_remove
def affect_remove(ch: Char, paf: Affect) -> None:
    if not ch.affected:
        bug("Affect_remove: no affect.", 0)
        return
    affect_modify(ch, paf, False)
    where, vector = paf.where, paf.bitvector
    for i, a in enumerate(ch.affected):
        if a is paf:
            del ch.affected[i]
            break
    else:
        bug("Affect_remove: cannot find paf.", 0)
        return
    affect_check(ch, where, vector)


# C: handler.c obj_from_room
def obj_from_room(obj: Obj) -> None:
    room = obj.in_room
    if room is None:
        bug("obj_from_room: NULL.", 0)
        return
    for ch in room.people:
        if ch.on is obj:
            ch.on = None
    for i, o in enumerate(room.contents):
        if o is obj:
            del room.contents[i]
            break
    else:
        bug("Obj_from_room: obj not found.", 0)
        return
    obj.in_room = None


# C: handler.c obj_from_obj
def obj_from_obj(obj: Obj) -> None:
    obj_from = obj.in_obj
    if obj_from is None:
        bug("Obj_from_obj: null obj_from.", 0)
        return
    for i, o in enumerate(obj_from.contains):
        if o is obj:
            del obj_from.contains[i]
            break
    else:
        bug("Obj_from_obj: obj not found.", 0)
        return
    obj.in_obj = None
    o = obj_from
    while o is not None:
        if o.carried_by is not None:
            c = o.carried_by
            c.carry_number = sh_int(c.carry_number - get_obj_number(obj))
            c.carry_weight = sh_int(c.carry_weight - c_div(get_obj_weight(obj) * weight_mult(o), 100))
        o = o.in_obj


# C: handler.c extract_obj
def extract_obj(game: Game, obj: Obj) -> None:
    if obj.in_room is not None:
        obj_from_room(obj)
    elif obj.carried_by is not None:
        obj_from_char(obj)
    elif obj.in_obj is not None:
        obj_from_obj(obj)
    for content in list(obj.contains):
        extract_obj(game, content)
    for i, o in enumerate(game.object_list):
        if o is obj:
            del game.object_list[i]
            break
    else:
        bug("Extract_obj: obj %d not found.", obj.index.vnum)
        return
    obj.index.count = sh_int(obj.index.count - 1)


def _str_prefix(astr: str, bstr: str) -> bool:
    """``!str_prefix(astr, bstr)``: astr is a case-insensitive prefix of bstr."""
    return bstr.lower().startswith(astr.lower())


# C: handler.c is_name
def is_name(string: str, namelist: str | None) -> bool:
    from charm.commands.interp import one_argument

    if not namelist:
        return False
    if string == "":
        return False
    whole, rest = string, string
    while True:
        rest, part = one_argument(rest)
        if part == "":
            return True
        names = namelist
        while True:
            names, name = one_argument(names)
            if name == "":
                return False
            if _str_prefix(whole, name):
                return True  # full pattern match
            if _str_prefix(part, name):
                break


# C: handler.c is_exact_name
def is_exact_name(string: str, namelist: str | None) -> bool:
    from charm.commands.interp import one_argument

    if namelist is None:
        return False
    while True:
        namelist, name = one_argument(namelist)
        if name == "":
            return False
        if string.lower() == name.lower():
            return True


def _apply(ch: Char, location: int, mod: int) -> None:
    """reset_char's "start adding back the effects" switch (the same three times)."""
    if location in _STAT:
        ch.mod_stat[_STAT[location]] = sh_int(ch.mod_stat[_STAT[location]] + mod)
    elif location == C.APPLY_SEX:
        ch.sex = sh_int(ch.sex + mod)
    elif location == C.APPLY_MANA:
        ch.max_mana = sh_int(ch.max_mana + mod)
    elif location == C.APPLY_HIT:
        ch.max_hit = sh_int(ch.max_hit + mod)
    elif location == C.APPLY_MOVE:
        ch.max_move = sh_int(ch.max_move + mod)
    elif location == C.APPLY_AC:
        for i in range(4):
            ch.armor[i] = sh_int(ch.armor[i] + mod)
    elif location == C.APPLY_HITROLL:
        ch.hitroll = sh_int(ch.hitroll + mod)
    elif location == C.APPLY_DAMROLL:
        ch.damroll = sh_int(ch.damroll + mod)
    elif location in _SAVES:
        ch.saving_throw = sh_int(ch.saving_throw + mod)


def _unapply(ch: Char, location: int, mod: int, fix_sex: bool) -> None:
    """The full reset's subtraction: sex, mana, hit and move only. Only the prototype's affects fix a bad sex."""
    if location == C.APPLY_SEX:
        ch.sex = sh_int(ch.sex - mod)
        if fix_sex and (ch.sex < 0 or ch.sex > 2):
            ch.sex = 0 if ch.is_npc else ch.pcdata.true_sex
    elif location == C.APPLY_MANA:
        ch.max_mana = sh_int(ch.max_mana - mod)
    elif location == C.APPLY_HIT:
        ch.max_hit = sh_int(ch.max_hit - mod)
    elif location == C.APPLY_MOVE:
        ch.max_move = sh_int(ch.max_move - mod)


# C: handler.c reset_char
def reset_char(ch: Char) -> None:
    if ch.is_npc:
        return
    pc = ch.pcdata
    if pc.perm_hit == 0 or pc.perm_mana == 0 or pc.perm_move == 0 or pc.last_level == 0:
        # "do a FULL reset"
        for loc in range(C.MAX_WEAR):
            obj = get_eq_char(ch, loc)
            if obj is None:
                continue
            if not obj.enchanted:
                for af in obj.index.affected:
                    _unapply(ch, af.location, af.modifier, True)
            for af in obj.affected:
                _unapply(ch, af.location, af.modifier, False)
        pc.perm_hit, pc.perm_mana, pc.perm_move = ch.max_hit, ch.max_mana, ch.max_move
        pc.last_level = c_div(ch.played, 3600)
        if pc.true_sex < 0 or pc.true_sex > 2:
            pc.true_sex = ch.sex if 0 < ch.sex < 3 else 0
    # "now restore the character to his/her true condition"
    ch.mod_stat = [0] * C.MAX_STATS
    if pc.true_sex < 0 or pc.true_sex > 2:
        pc.true_sex = 0
    ch.sex = pc.true_sex
    ch.max_hit, ch.max_mana, ch.max_move = pc.perm_hit, pc.perm_mana, pc.perm_move
    ch.armor = [100] * 4
    ch.hitroll = ch.damroll = ch.saving_throw = 0
    for loc in range(C.MAX_WEAR):  # "now start adding back the effects"
        obj = get_eq_char(ch, loc)
        if obj is None:
            continue
        for i in range(4):
            ch.armor[i] = sh_int(ch.armor[i] - apply_ac(obj, loc, i))
        if not obj.enchanted:
            for af in obj.index.affected:
                _apply(ch, af.location, af.modifier)
        for af in obj.affected:
            _apply(ch, af.location, af.modifier)
    for af in ch.affected:  # "now add back spell effects"
        _apply(ch, af.location, af.modifier)
    if ch.sex < 0 or ch.sex > 2:  # "make sure sex is RIGHT!!!!"
        ch.sex = pc.true_sex

