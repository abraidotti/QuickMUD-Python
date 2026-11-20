"""Making mobs and objects from their prototypes: create_mobile and create_object, and clone_mobile and
clone_object for do_clone.

Every random draw is in the C's order, because the draws during resets decide what the world looks like and
every later draw depends on them. Both are [partial]: the old-format branches (#MOBOLD and #OBJOLD prototypes,
which no area uses) raise NotPorted.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/recycle.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, int32, sh_int
from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.core.rng import dice, number_range
from charm.data import constants as C
from charm.entities.game import Game
from charm.entities.handler import affect_to_char, affect_to_obj, is_affected
from charm.entities.things import Char, Obj, new_char, new_obj
from charm.world.index import Affect, MobIndex, ObjIndex
from charm.world.lookup import skill_lookup


# C: recycle.c get_mob_id
def get_mob_id(game: Game) -> int:
    game.last_mob_id += 1
    return game.last_mob_id


def _random_dam_type() -> int:
    return {1: 3, 2: 7, 3: 11}[number_range(1, 3)]  # slash, pound, pierce


# C: db.c create_mobile [partial]
def create_mobile(game: Game, p: MobIndex) -> Char:
    """[partial]: an old-format prototype raises NotPorted."""
    game.mobile_count += 1
    if p is None:
        raise SystemExit("Create_mobile: NULL pMobIndex.")
    mob = new_char(game.current_time)
    mob.index = p
    mob.name = p.player_name
    mob.short_descr = p.short_descr
    mob.long_descr = p.long_descr
    mob.description = p.description
    mob.own_strings.clear()  # str_dup hands back a boot string's pointer: these are still the prototype's
    mob.id = get_mob_id(game)
    mob.spec_fun = p.spec_fun
    mob.prompt = None
    mob.mprog_target = None

    if p.wealth == 0:
        mob.silver = 0
        mob.gold = 0
    else:
        wealth = number_range(c_div(p.wealth, 2), c_div(3 * p.wealth, 2))
        mob.gold = number_range(c_div(wealth, 200), c_div(wealth, 100))
        mob.silver = wealth - mob.gold * 100

    if not p.new_format:
        raise NotPorted("db.c create_mobile: an old-format (#MOBOLD) prototype")

    mob.group = p.group
    mob.act = p.act
    mob.comm = C.COMM_NOCHANNELS | C.COMM_NOSHOUT | C.COMM_NOTELL
    mob.affected_by = p.affected_by
    mob.alignment = p.alignment
    mob.level = p.level
    mob.hitroll = p.hitroll
    mob.damroll = p.damage[C.DICE_BONUS]
    mob.max_hit = sh_int(dice(p.hit[C.DICE_NUMBER], p.hit[C.DICE_TYPE]) + p.hit[C.DICE_BONUS])
    mob.hit = mob.max_hit
    mob.max_mana = sh_int(dice(p.mana[C.DICE_NUMBER], p.mana[C.DICE_TYPE]) + p.mana[C.DICE_BONUS])
    mob.mana = mob.max_mana
    mob.damage[C.DICE_NUMBER] = p.damage[C.DICE_NUMBER]
    mob.damage[C.DICE_TYPE] = p.damage[C.DICE_TYPE]
    mob.dam_type = p.dam_type
    if mob.dam_type == 0:
        mob.dam_type = _random_dam_type()
    for i in range(4):
        mob.armor[i] = p.ac[i]
    mob.off_flags = p.off_flags
    mob.imm_flags = p.imm_flags
    mob.res_flags = p.res_flags
    mob.vuln_flags = p.vuln_flags
    mob.start_pos = p.start_pos
    mob.default_pos = p.default_pos
    mob.sex = p.sex
    if mob.sex == 3:  # random sex
        mob.sex = number_range(1, 2)
    mob.race = p.race
    mob.form = p.form
    mob.parts = p.parts
    mob.size = p.size
    mob.material = p.material

    for i in range(C.MAX_STATS):
        mob.perm_stat[i] = min(25, 11 + c_div(mob.level, 4))
    st = mob.perm_stat
    if mob.act & C.ACT_WARRIOR:
        st[C.STAT_STR] += 3
        st[C.STAT_INT] -= 1
        st[C.STAT_CON] += 2
    if mob.act & C.ACT_THIEF:
        st[C.STAT_DEX] += 3
        st[C.STAT_INT] += 1
        st[C.STAT_WIS] -= 1
    if mob.act & C.ACT_CLERIC:
        st[C.STAT_WIS] += 3
        st[C.STAT_DEX] -= 1
        st[C.STAT_STR] += 1
    if mob.act & C.ACT_MAGE:
        st[C.STAT_INT] += 3
        st[C.STAT_STR] -= 1
        st[C.STAT_DEX] += 1
    if mob.off_flags & C.OFF_FAST:
        st[C.STAT_DEX] += 2
    st[C.STAT_STR] += mob.size - C.SIZE_MEDIUM
    st[C.STAT_CON] += c_div(mob.size - C.SIZE_MEDIUM, 2)
    for i in range(C.MAX_STATS):
        st[i] = sh_int(st[i])

    # "let's get some spell action"
    if is_affected(mob, C.AFF_SANCTUARY):
        affect_to_char(mob, Affect(C.TO_AFFECTS, skill_lookup("sanctuary"), mob.level, -1, C.APPLY_NONE, 0,
                                   C.AFF_SANCTUARY))
    if is_affected(mob, C.AFF_HASTE):
        modifier = 1 + (mob.level >= 18) + (mob.level >= 25) + (mob.level >= 32)
        affect_to_char(mob, Affect(C.TO_AFFECTS, skill_lookup("haste"), mob.level, -1, C.APPLY_DEX, modifier,
                                   C.AFF_HASTE))
    if is_affected(mob, C.AFF_PROTECT_EVIL):
        affect_to_char(mob, Affect(C.TO_AFFECTS, skill_lookup("protection evil"), mob.level, -1, C.APPLY_SAVES, -1,
                                   C.AFF_PROTECT_EVIL))
    if is_affected(mob, C.AFF_PROTECT_GOOD):
        affect_to_char(mob, Affect(C.TO_AFFECTS, skill_lookup("protection good"), mob.level, -1, C.APPLY_SAVES, -1,
                                   C.AFF_PROTECT_GOOD))

    mob.position = mob.start_pos
    game.char_list.insert(0, mob)
    p.count = sh_int(p.count + 1)
    return mob


_COST_FIFTH = {C.ITEM_FURNITURE, C.ITEM_TRASH, C.ITEM_CONTAINER, C.ITEM_DRINK_CON, C.ITEM_KEY, C.ITEM_FOOD,
               C.ITEM_BOAT, C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC, C.ITEM_FOUNTAIN, C.ITEM_MAP, C.ITEM_CLOTHING,
               C.ITEM_PORTAL}
_AS_IS = {C.ITEM_TREASURE, C.ITEM_WARP_STONE, C.ITEM_ROOM_KEY, C.ITEM_GEM, C.ITEM_JEWELRY}
_OLD_FORMAT_ONLY = {C.ITEM_SCROLL, C.ITEM_WAND, C.ITEM_STAFF, C.ITEM_WEAPON, C.ITEM_ARMOR, C.ITEM_POTION,
                    C.ITEM_PILL, C.ITEM_MONEY}


# C: db.c create_object [partial]
def create_object(game: Game, p: ObjIndex, level: int) -> Obj:
    """[partial]: an old-format prototype raises NotPorted (its level, cost and values are made up from the
    level given, with more random draws)."""
    if p is None:
        raise SystemExit("Create_object: NULL pObjIndex.")
    if not p.new_format:
        raise NotPorted("db.c create_object: an old-format (#OBJOLD) prototype")
    obj = new_obj()
    obj.index = p
    obj.in_room = None
    obj.enchanted = False
    obj.level = p.level
    obj.wear_loc = -1
    obj.name = p.name
    obj.short_descr = p.short_descr
    obj.description = p.description
    obj.own_strings.clear()  # str_dup hands back a boot string's pointer: these are still the prototype's
    obj.material = p.material
    obj.item_type = p.item_type
    obj.extra_flags = p.extra_flags
    obj.wear_flags = p.wear_flags
    obj.value = list(p.value)
    obj.weight = p.weight
    obj.cost = p.cost  # level == -1 or new format

    # "Mess with object properties": for a new-format prototype only these branches do anything.
    t = obj.item_type
    if t == C.ITEM_LIGHT:
        if obj.value[2] == 999:
            obj.value[2] = -1
    elif t == C.ITEM_JUKEBOX:
        obj.value = [-1] * 5
    elif t in _COST_FIFTH or t in _AS_IS or t in _OLD_FORMAT_ONLY:
        pass
    else:
        bug("Read_object: vnum %d bad type.", p.vnum)

    for paf in p.affected:
        if paf.location == C.APPLY_SPELL_AFFECT:
            affect_to_obj(obj, paf)

    game.object_list.insert(0, obj)
    p.count = sh_int(p.count + 1)
    obj.cost = int32(obj.cost)
    return obj


# C: db.c clone_mobile
def clone_mobile(parent: Char | None, clone: Char | None) -> None:
    """Copy a mob onto a fresh one made from the same prototype (do_clone). The affects go through affect_to_char,
    which applies their modifiers again on top of the copied stats, as the C does."""
    if parent is None or clone is None or not parent.is_npc:
        return
    # "start fixing values"
    for f in ("name", "version", "short_descr", "long_descr", "description", "group", "sex", "class_", "race",
              "level", "timer", "wait", "hit", "max_hit", "mana", "max_mana", "move", "max_move", "gold", "silver",
              "exp", "act", "comm", "imm_flags", "res_flags", "vuln_flags", "invis_level", "affected_by", "position",
              "practice", "train", "saving_throw", "alignment", "hitroll", "damroll", "wimpy", "form", "parts",
              "size", "material", "off_flags", "dam_type", "start_pos", "default_pos", "spec_fun"):
        setattr(clone, f, getattr(parent, f))
    clone.trust = 0
    # str_dup keeps a boot string's pointer, so the clone's strings are the prototype's where the parent's are
    clone.own_strings = set(parent.own_strings)
    clone.armor = list(parent.armor)
    clone.perm_stat = list(parent.perm_stat)
    clone.mod_stat = list(parent.mod_stat)
    clone.damage = list(parent.damage)
    for paf in parent.affected:  # "now add the affects"
        affect_to_char(clone, paf)


# C: db.c clone_object
def clone_object(parent: Obj | None, clone: Obj | None) -> None:
    """Copy an object onto a fresh one made from the same prototype (do_clone). affect_to_obj and the extra
    descriptions each go on the head of the list, so both come out in the reverse order."""
    from charm.world.index import ExtraDescr

    if parent is None or clone is None:
        return
    # "start fixing the object"
    for f in ("name", "short_descr", "description", "item_type", "extra_flags", "wear_flags", "weight", "cost",
              "level", "condition", "material", "timer"):
        setattr(clone, f, getattr(parent, f))
    clone.own_strings = set(parent.own_strings)
    clone.value[:5] = parent.value[:5]
    clone.enchanted = parent.enchanted  # "affects"
    for paf in parent.affected:
        affect_to_obj(clone, paf)
    for ed in parent.extra_descr:  # "extended desc"
        clone.extra_descr.insert(0, ExtraDescr(ed.keyword, ed.description))


# C: recycle.c free_char
def free_char(game: Game, ch: Char) -> None:
    """Extract what it carries, remove its affects, and invalidate it (the memory is Python's to free)."""
    from charm.entities.handler import affect_remove, extract_obj

    if not ch.valid:
        return
    if ch.is_npc:
        game.mobile_count -= 1
    for obj in list(ch.carrying):
        extract_obj(game, obj)
    for paf in list(ch.affected):
        affect_remove(ch, paf)
    ch.valid = False

