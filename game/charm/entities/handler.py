"""handler.c's functions: moving characters and objects about, affects, finding things by name, and what a
character can see, carry and do (skills, trust, age). db.c's get_extra_descr is here too.

A few are [partial]; each unported branch raises NotPorted instead of doing something else: plague spreading in
char_to_room (it needs spells), a switched character in extract_char (do_return), and get_skill's daze with
sn -1, where the C reads before the start of skill_table.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/handler.c, src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, int32, sh_int
from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.core.strings import str_cmp, str_prefix
from charm.net.act import act
from charm.data import constants as C
from charm.entities.game import Game, WeatherInfo
from charm.entities.game import weather as game_weather
from charm.entities.things import Char, Obj
from charm.world.index import Affect, ObjIndex, Room
from charm.data.attributes import STR_APP
from charm.data.classes import CLASS_TABLE
from charm.data.races import PC_RACE_TABLE
from charm.world.lookup import GSN, race_lookup, skill_lookup
from charm.core.rng import number_percent
from charm.data.attributes import DEX_APP
from charm.data.skills import SKILL_TABLE
from charm.entities import game as game_module


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
    """[partial]: plague spreading to the room needs saves_spell and affect_join, which aren't ported."""
    if room is None:
        bug("Char_to_room: NULL.", 0)
        temple = game_module.current.index.get_room_index(C.ROOM_VNUM_TEMPLE)
        if temple is not None:
            char_to_room(ch, temple)
        return
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


# C: handler.c equip_char
def equip_char(ch: Char, obj: Obj, wear: int) -> None:
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


# C: handler.c can_see
def can_see(ch: Char, victim: Char) -> bool:
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
        chance = get_skill(victim, GSN["gsn_sneak"])
        chance += c_div(get_curr_stat(victim, C.STAT_DEX) * 3, 2)
        chance -= get_curr_stat(ch, C.STAT_INT) * 2
        chance -= ch.level - c_div(victim.level * 3, 2)
        if number_percent() < chance:
            return False
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
            if str_prefix(whole, name):
                return True  # full pattern match
            if str_prefix(part, name):
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
        if str_cmp(string, name):
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



# C: handler.c get_skill [partial]
def get_skill(ch: Char, sn: int) -> int:
    """[partial]: a dazed character with sn -1 reads skill_table[-1] in the C, before the array: raises NotPorted."""
    if sn == -1:  # "shorthand for level based skills"
        skill = c_div(ch.level * 5, 2)
    elif sn < -1 or sn > C.MAX_SKILL:
        bug("Bad sn %d in get_skill.", sn)
        skill = 0
    elif not ch.is_npc:
        skill = 0 if ch.level < SKILL_TABLE[sn].skill_level[ch.class_] else ch.pcdata.learned[sn]
    else:  # mobiles
        g, off, flags = GSN, ch.off_flags, ch.act
        if SKILL_TABLE[sn].spell_fun != "spell_null":
            skill = 40 + 2 * ch.level
        elif sn in (g["gsn_sneak"], g["gsn_hide"]):
            skill = ch.level * 2 + 20
        elif (sn == g["gsn_dodge"] and off & C.OFF_DODGE) or (sn == g["gsn_parry"] and off & C.OFF_PARRY):
            skill = ch.level * 2
        elif sn == g["gsn_shield_block"]:
            skill = 10 + 2 * ch.level
        elif sn == g["gsn_second_attack"] and flags & (C.ACT_WARRIOR | C.ACT_THIEF):
            skill = 10 + 3 * ch.level
        elif sn == g["gsn_third_attack"] and flags & C.ACT_WARRIOR:
            skill = 4 * ch.level - 40
        elif sn == g["gsn_hand_to_hand"]:
            skill = 40 + 2 * ch.level
        elif sn == g["gsn_trip"] and off & C.OFF_TRIP:
            skill = 10 + 3 * ch.level
        elif sn == g["gsn_bash"] and off & C.OFF_BASH:
            skill = 10 + 3 * ch.level
        elif sn == g["gsn_disarm"] and (off & C.OFF_DISARM or flags & (C.ACT_WARRIOR | C.ACT_THIEF)):
            skill = 20 + 3 * ch.level
        elif sn == g["gsn_berserk"] and off & C.OFF_BERSERK:
            skill = 3 * ch.level
        elif sn == g["gsn_kick"]:
            skill = 10 + 3 * ch.level
        elif sn == g["gsn_backstab"] and flags & C.ACT_THIEF:
            skill = 20 + 2 * ch.level
        elif sn in (g["gsn_rescue"], g["gsn_recall"]):
            skill = 40 + ch.level
        elif sn in (g["gsn_sword"], g["gsn_dagger"], g["gsn_spear"], g["gsn_mace"], g["gsn_axe"], g["gsn_flail"],
                    g["gsn_whip"], g["gsn_polearm"]):
            skill = 40 + c_div(5 * ch.level, 2)
        else:
            skill = 0
    if ch.daze > 0:
        if sn == -1:
            raise NotPorted("handler.c get_skill: daze with sn -1 (reads skill_table[-1])")
        skill = c_div(skill, 2) if SKILL_TABLE[sn].spell_fun != "spell_null" else c_div(2 * skill, 3)
    if not ch.is_npc and ch.pcdata.condition[C.COND_DRUNK] > 10:
        skill = c_div(9 * skill, 10)
    return 0 if skill < 0 else (100 if skill > 100 else skill)


_WEAPON_GSN = {C.WEAPON_SWORD: "gsn_sword", C.WEAPON_DAGGER: "gsn_dagger", C.WEAPON_SPEAR: "gsn_spear",
               C.WEAPON_MACE: "gsn_mace", C.WEAPON_AXE: "gsn_axe", C.WEAPON_FLAIL: "gsn_flail",
               C.WEAPON_WHIP: "gsn_whip", C.WEAPON_POLEARM: "gsn_polearm"}


# C: handler.c get_weapon_sn
def get_weapon_sn(ch: Char) -> int:
    wield = get_eq_char(ch, C.WEAR_WIELD)
    if wield is None or wield.item_type != C.ITEM_WEAPON:
        return GSN["gsn_hand_to_hand"]
    name = _WEAPON_GSN.get(wield.value[0])
    return GSN[name] if name else -1  # -1 is exotic


# C: handler.c get_weapon_skill
def get_weapon_skill(ch: Char, sn: int) -> int:
    if ch.is_npc:
        if sn == -1:  # "-1 is exotic"
            skill = 3 * ch.level
        elif sn == GSN["gsn_hand_to_hand"]:
            skill = 40 + 2 * ch.level
        else:
            skill = 40 + c_div(5 * ch.level, 2)
    elif sn == -1:
        skill = 3 * ch.level
    else:
        skill = ch.pcdata.learned[sn]
    return 0 if skill < 0 else (100 if skill > 100 else skill)  # URANGE(0, skill, 100)


# C: handler.c create_money
def create_money(game: Game, gold: int, silver: int) -> Obj:
    from charm.entities.create import create_object

    if gold < 0 or silver < 0 or (gold == 0 and silver == 0):
        bug("Create_money: zero or negative money.", min(gold, silver))
        gold = max(1, gold)
        silver = max(1, silver)
    ix = game.index
    if gold == 0 and silver == 1:
        obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_SILVER_ONE), 0)
    elif gold == 1 and silver == 0:
        obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_GOLD_ONE), 0)
    elif silver == 0:
        obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_GOLD_SOME), 0)
        obj.short_descr = obj.short_descr % gold  # format: sprintf (limbo.are's "%d gold coins")
        obj.value[1] = gold
        obj.cost = gold
        obj.weight = gold // 5  # non-negative: gold > 0 here
    elif gold == 0:
        obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_SILVER_SOME), 0)
        obj.short_descr = obj.short_descr % silver  # format: sprintf (limbo.are's "%d silver coins")
        obj.value[0] = silver
        obj.cost = silver
        obj.weight = silver // 20  # non-negative: silver > 0 here
    else:
        obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_COINS), 0)
        obj.short_descr = obj.short_descr % (silver, gold)  # format: sprintf ("%d silver coins and %d gold coins")
        obj.value[0] = silver
        obj.value[1] = gold
        obj.cost = int32(100 * gold + silver)
        obj.weight = gold // 5 + silver // 20  # non-negative: both > 0 here
    return obj


# C: handler.c get_true_weight
def get_true_weight(obj: Obj) -> int:
    weight = obj.weight
    for o in obj.contains:
        weight += get_obj_weight(o)
    return int32(weight)


# C: handler.c can_drop_obj
def can_drop_obj(ch: Char, obj: Obj) -> bool:
    if not obj.extra_flags & C.ITEM_NODROP:
        return True
    return not ch.is_npc and ch.level >= C.LEVEL_IMMORTAL


# C: handler.c get_age
def get_age(game: Game, ch: Char) -> int:
    return 17 + c_div(ch.played + int32(game.current_time - ch.logon), 72000)


# C: handler.c can_carry_n
def can_carry_n(ch: Char) -> int:
    if not ch.is_npc and ch.level >= C.LEVEL_IMMORTAL:
        return 1000
    if ch.is_npc and ch.act & C.ACT_PET:
        return 0
    return C.MAX_WEAR + 2 * get_curr_stat(ch, C.STAT_DEX) + ch.level


# C: handler.c can_carry_w
def can_carry_w(ch: Char) -> int:
    if not ch.is_npc and ch.level >= C.LEVEL_IMMORTAL:
        return 10000000
    if ch.is_npc and ch.act & C.ACT_PET:
        return 0
    return STR_APP[get_curr_stat(ch, C.STAT_STR)].carry * 10 + ch.level * 25


def get_carry_weight(ch: Char) -> int:
    """get_carry_weight: carried weight plus the coins' (silver / 10 and gold * 2 / 5)."""
    return ch.carry_weight + c_div(ch.silver, 10) + c_div(ch.gold * 2, 5)


def is_awake(ch: Char) -> bool:
    """IS_AWAKE."""
    return ch.position > C.POS_SLEEPING


def get_ac(ch: Char, kind: int) -> int:
    """GET_AC: armour, plus the dexterity bonus while awake."""
    return ch.armor[kind] + (DEX_APP[get_curr_stat(ch, C.STAT_DEX)].defensive if is_awake(ch) else 0)


def get_hitroll(ch: Char) -> int:
    """GET_HITROLL."""
    return ch.hitroll + STR_APP[get_curr_stat(ch, C.STAT_STR)].tohit


def get_damroll(ch: Char) -> int:
    """GET_DAMROLL."""
    return ch.damroll + STR_APP[get_curr_stat(ch, C.STAT_STR)].todam


def is_builder(ch: Char, area) -> bool:
    """IS_BUILDER: not switched, and security high enough or named (or "All") in the area's builders."""
    switched = ch.desc is not None and ch.desc.original is not None
    return (not ch.is_npc and not switched
            and (ch.pcdata.security >= area.security or ch.name in area.builders or "All" in area.builders))


# C: handler.c char_from_room
def char_from_room(ch: Char) -> None:
    room = ch.in_room
    if room is None:
        bug("Char_from_room: NULL.", 0)
        return
    if not ch.is_npc:
        room.area.nplayer = sh_int(room.area.nplayer - 1)
    obj = get_eq_char(ch, C.WEAR_LIGHT)
    if obj is not None and obj.item_type == C.ITEM_LIGHT and obj.value[2] != 0 and room.light > 0:
        room.light = sh_int(room.light - 1)
    if ch in room.people:
        room.people.remove(ch)
    else:
        bug("Char_from_room: ch not found.", 0)
    ch.in_room = None
    ch.on = None  # "sanity check!"


# C: handler.c extract_char [partial]
def extract_char(game: Game, ch: Char, f_pull: bool) -> None:
    """[partial]: a switched character (do_return) raises NotPorted."""
    from charm.commands.comm import die_follower, nuke_pets
    from charm.data.clans import CLAN_TABLE
    from charm.entities.create import free_char
    from charm.systems.fight import stop_fighting

    nuke_pets(game, ch)
    ch.pet = None  # "just in case"
    if f_pull:
        die_follower(game, ch)
    stop_fighting(game, ch, True)
    for obj in list(ch.carrying):
        extract_obj(game, obj)
    if ch.in_room is not None:
        char_from_room(ch)
    if not f_pull:  # "Death room is set in the clan tabe now"
        char_to_room(ch, game.index.get_room_index(CLAN_TABLE[ch.clan].hall))
        return
    if ch.is_npc:
        ch.index.count = sh_int(ch.index.count - 1)
    if ch.desc is not None and ch.desc.original is not None:
        raise NotPorted("handler.c extract_char: do_return (a switched character)")
    for wch in game.char_list:
        if wch.reply is ch:
            wch.reply = None
        if ch.mprog_target is wch:
            wch.mprog_target = None
    if ch in game.char_list:
        game.char_list.remove(ch)
    else:
        bug("Extract_char: char not found.", 0)
        return
    if ch.desc is not None:
        ch.desc.character = None
    free_char(game, ch)


# C: handler.c get_char_room
def get_char_room(ch: Char, argument: str) -> Char | None:
    from charm.commands.interp import number_argument
    from charm.core.strings import str_cmp

    number, arg = number_argument(argument)
    if str_cmp(arg, "self"):
        return ch
    count = 0
    for rch in ch.in_room.people:
        if not can_see(ch, rch) or not is_name(arg, rch.name):
            continue
        count += 1
        if count == number:
            return rch
    return None


# C: handler.c get_obj_list
def get_obj_list(ch: Char, argument: str, objs: list[Obj]) -> Obj | None:
    from charm.commands.interp import number_argument

    number, arg = number_argument(argument)
    count = 0
    for obj in objs:
        if can_see_obj(ch, obj) and is_name(arg, obj.name):
            count += 1
            if count == number:
                return obj
    return None


# C: handler.c get_obj_carry
def get_obj_carry(ch: Char, argument: str, viewer: Char) -> Obj | None:
    from charm.commands.interp import number_argument

    number, arg = number_argument(argument)
    count = 0
    for obj in ch.carrying:
        if obj.wear_loc == C.WEAR_NONE and can_see_obj(viewer, obj) and is_name(arg, obj.name):
            count += 1
            if count == number:
                return obj
    return None


# C: handler.c get_obj_wear
def get_obj_wear(ch: Char, argument: str) -> Obj | None:
    from charm.commands.interp import number_argument

    number, arg = number_argument(argument)
    count = 0
    for obj in ch.carrying:
        if obj.wear_loc != C.WEAR_NONE and can_see_obj(ch, obj) and is_name(arg, obj.name):
            count += 1
            if count == number:
                return obj
    return None


# C: handler.c get_obj_here
def get_obj_here(ch: Char, argument: str) -> Obj | None:
    obj = get_obj_list(ch, argument, ch.in_room.contents)
    if obj is not None:
        return obj
    obj = get_obj_carry(ch, argument, ch)
    if obj is not None:
        return obj
    return get_obj_wear(ch, argument)


# C: handler.c room_is_private
def room_is_private(room: Room) -> bool:
    if room.owner:
        return True
    count = len(room.people)
    if room.room_flags & C.ROOM_PRIVATE and count >= 2:
        return True
    if room.room_flags & C.ROOM_SOLITARY and count >= 1:
        return True
    if room.room_flags & C.ROOM_IMP_ONLY:
        return True
    return False


def next_in_room(ch: Char) -> Char | None:
    """``ch->next_in_room``: who comes after ch in its room's list now. A C loop that saves it before moving ch
    carries on through whatever room that one is in by then; walking a copy of the list wouldn't."""
    if ch.in_room is None:
        return None
    people = ch.in_room.people
    i = next(k for k, p in enumerate(people) if p is ch)
    return people[i + 1] if i + 1 < len(people) else None


# C: handler.c count_users
def count_users(obj: Obj) -> int:
    if obj.in_room is None:
        return 0
    return sum(1 for fch in obj.in_room.people if fch.on is obj)


# C: handler.c get_max_train
def get_max_train(ch: Char, stat: int) -> int:
    if ch.is_npc or ch.level > C.LEVEL_IMMORTAL:
        return 25
    max_ = PC_RACE_TABLE[ch.race].max_stats[stat]
    if CLASS_TABLE[ch.class_].attr_prime == stat:
        max_ += 3 if ch.race == race_lookup("human") else 2
    return min(max_, 25)


# C: handler.c is_room_owner
def is_room_owner(ch: Char, room: Room) -> bool:
    if not room.owner:
        return False
    return is_name(ch.name, room.owner)


# C: handler.c is_clan
def is_clan(ch: Char) -> bool:
    return bool(ch.clan)


# C: handler.c is_same_clan
def is_same_clan(ch: Char, victim: Char) -> bool:
    from charm.data.clans import CLAN_TABLE

    if CLAN_TABLE[ch.clan].independent:
        return False
    return ch.clan == victim.clan


# C: handler.c get_char_world
def get_char_world(game: Game, ch: Char, argument: str) -> Char | None:
    from charm.commands.interp import number_argument

    wch = get_char_room(ch, argument)
    if wch is not None:
        return wch
    number, arg = number_argument(argument)
    count = 0
    for wch in game.char_list:
        if wch.in_room is None or not can_see(ch, wch) or not is_name(arg, wch.name):
            continue
        count += 1
        if count == number:
            return wch
    return None


# handler.c default_colour's settings: (bright, colour, beep). Not save.c's defaults for a file with no colours.
_DEFAULT_COLOUR = {
    "text": (C.NORMAL, C.WHITE, 0), "auction": (C.BRIGHT, C.YELLOW, 0), "auction_text": (C.BRIGHT, C.WHITE, 0),
    "gossip": (C.NORMAL, C.MAGENTA, 0), "gossip_text": (C.BRIGHT, C.MAGENTA, 0), "music": (C.NORMAL, C.RED, 0),
    "music_text": (C.BRIGHT, C.RED, 0), "question": (C.BRIGHT, C.YELLOW, 0), "question_text": (C.BRIGHT, C.WHITE, 0),
    "answer": (C.BRIGHT, C.YELLOW, 0), "answer_text": (C.BRIGHT, C.WHITE, 0), "quote": (C.NORMAL, C.GREEN, 0),
    "quote_text": (C.BRIGHT, C.GREEN, 0), "immtalk_text": (C.NORMAL, C.CYAN, 0),
    "immtalk_type": (C.NORMAL, C.YELLOW, 0), "info": (C.NORMAL, C.YELLOW, 1), "tell": (C.NORMAL, C.GREEN, 0),
    "tell_text": (C.BRIGHT, C.GREEN, 0), "say": (C.NORMAL, C.GREEN, 0), "say_text": (C.BRIGHT, C.GREEN, 0),
    "reply": (C.NORMAL, C.GREEN, 0), "reply_text": (C.BRIGHT, C.GREEN, 0), "gtell_text": (C.NORMAL, C.GREEN, 0),
    "gtell_type": (C.NORMAL, C.RED, 0), "wiznet": (C.NORMAL, C.GREEN, 0), "room_title": (C.NORMAL, C.CYAN, 0),
    "room_text": (C.NORMAL, C.WHITE, 0), "room_exits": (C.NORMAL, C.GREEN, 0), "room_things": (C.NORMAL, C.CYAN, 0),
    "prompt": (C.NORMAL, C.CYAN, 0), "fight_death": (C.NORMAL, C.RED, 0), "fight_yhit": (C.NORMAL, C.GREEN, 0),
    "fight_ohit": (C.NORMAL, C.YELLOW, 0), "fight_thit": (C.NORMAL, C.RED, 0), "fight_skill": (C.NORMAL, C.WHITE, 0),
}


# C: handler.c default_colour
def default_colour(ch: Char) -> None:
    if ch.is_npc or ch.pcdata is None:
        return
    for name, triple in _DEFAULT_COLOUR.items():
        ch.pcdata.colours[name][:] = triple


# all_colour's choices, in the C's order: (word, colour, bright, the name it reports). sic: no "red". The C tests
# it with an if, not an else-if, so the chain after it says "Unrecognised" for red (#51). And grey
# reports "White".
_ALL_COLOURS = (
    ("hi-red", C.RED, C.BRIGHT, "Red"), ("green", C.GREEN, C.NORMAL, "Green"),
    ("hi-green", C.GREEN, C.BRIGHT, "Green"), ("yellow", C.YELLOW, C.NORMAL, "Yellow"),
    ("hi-yellow", C.YELLOW, C.BRIGHT, "Yellow"), ("blue", C.BLUE, C.NORMAL, "Blue"),
    ("hi-blue", C.BLUE, C.BRIGHT, "Blue"), ("magenta", C.MAGENTA, C.NORMAL, "Magenta"),
    ("hi-magenta", C.MAGENTA, C.BRIGHT, "Magenta"), ("cyan", C.CYAN, C.NORMAL, "Cyan"),
    ("hi-cyan", C.CYAN, C.BRIGHT, "Cyan"), ("white", C.WHITE, C.NORMAL, "White"),
    ("hi-white", C.WHITE, C.BRIGHT, "White"), ("grey", C.BLACK, C.BRIGHT, "White"),
)
# The settings all_colour changes: every one but the five channels' _text ones after auction_text.
_ALL_COLOUR_FIELDS = (
    "text", "auction", "gossip", "music", "question", "answer", "quote", "quote_text", "immtalk_text", "immtalk_type",
    "info", "say", "say_text", "tell", "tell_text", "reply", "reply_text", "gtell_text", "gtell_type", "wiznet",
    "room_title", "room_text", "room_exits", "room_things", "prompt", "fight_death", "fight_yhit", "fight_ohit",
    "fight_thit", "fight_skill")


# C: handler.c all_colour
def all_colour(ch: Char, argument: str) -> None:
    from charm.net.output import send_to_char_bw

    if ch.is_npc or ch.pcdata is None:
        return
    if argument == "":
        return
    for word, colour, bright, name in _ALL_COLOURS:
        if str_prefix(argument, word):
            break
    else:
        send_to_char_bw("Unrecognised colour, unchanged.\n\r", ch)
        return
    for field in _ALL_COLOUR_FIELDS:
        ch.pcdata.colours[field][1] = colour
    for field in _ALL_COLOUR_FIELDS:
        ch.pcdata.colours[field][0] = bright
    send_to_char_bw("All Colour settings set to %s.\n\r" % name, ch)


_LOC_NAMES = {
    C.APPLY_NONE: "none", C.APPLY_STR: "strength", C.APPLY_DEX: "dexterity", C.APPLY_INT: "intelligence",
    C.APPLY_WIS: "wisdom", C.APPLY_CON: "constitution", C.APPLY_SEX: "sex", C.APPLY_CLASS: "class",
    C.APPLY_LEVEL: "level", C.APPLY_AGE: "age", C.APPLY_MANA: "mana", C.APPLY_HIT: "hp", C.APPLY_MOVE: "moves",
    C.APPLY_GOLD: "gold", C.APPLY_EXP: "experience", C.APPLY_AC: "armor class", C.APPLY_HITROLL: "hit roll",
    C.APPLY_DAMROLL: "damage roll", C.APPLY_SAVES: "saves", C.APPLY_SAVING_ROD: "save vs rod",
    C.APPLY_SAVING_PETRI: "save vs petrification", C.APPLY_SAVING_BREATH: "save vs breath",
    C.APPLY_SAVING_SPELL: "save vs spell", C.APPLY_SPELL_AFFECT: "none",
}


# C: handler.c affect_loc_name
def affect_loc_name(location: int) -> str:
    if location in _LOC_NAMES:
        return _LOC_NAMES[location]
    bug("Affect_location_name: unknown location %d.", location)
    return "(unknown)"


# C: handler.c affect_strip
def affect_strip(ch: Char, sn: int) -> None:
    for paf in list(ch.affected):
        if paf.type == sn:
            affect_remove(ch, paf)


# C: db.c get_extra_descr
def get_extra_descr(name: str, eds) -> str | None:
    for ed in eds:
        if is_name(name, ed.keyword):
            return ed.description
    return None
