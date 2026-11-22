"""effects.c: what acid, cold, fire, poison and lightning do to a character, an object or a room's floor.

A weapon that burns, freezes or shocks (fight.c's one_hit) calls these, as the breath and elemental spells will.
Each walks a list by the next pointer it took before the body ran, and the body can only take the current object
from the list (its contents go to the room's head), so walking a copy of the list visits the same objects.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/effects.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div, sh_int
from quickmud.core.rng import number_percent, number_range
from quickmud.data import constants as C


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


def _chance(level: int, dam: int) -> int:
    """The chance an object is toasted, before its own adjustments."""
    chance = c_div(level, 4) + c_div(dam, 10)
    if chance > 25:
        chance = c_div(chance - 25, 2) + 25
    if chance > 50:
        chance = c_div(chance - 50, 2) + 50
    return chance


def _show(msg: str, obj) -> None:
    from quickmud.net.act import act

    if obj.carried_by is not None:
        act(msg, obj.carried_by, obj, None, C.TO_ALL)
    elif obj.in_room is not None and obj.in_room.people:
        act(msg, obj.in_room.people[0], obj, None, C.TO_ALL)


def _dump_contents(obj, level: int, dam: int, effect) -> None:
    """Spill a destroyed container's contents to the room it's in or its carrier is in, and toast each at half."""
    from quickmud.entities.handler import extract_obj, obj_from_obj, obj_to_room

    for t_obj in list(obj.contains):
        obj_from_obj(t_obj)
        if obj.in_room is not None:
            obj_to_room(t_obj, obj.in_room)
        elif obj.carried_by is not None:
            obj_to_room(t_obj, obj.carried_by.in_room)
        else:
            extract_obj(_game(), t_obj)
            continue
        effect(t_obj, c_div(level, 2), c_div(dam, 2), C.TARGET_OBJ)


# C: effects.c acid_effect
def acid_effect(vo, level: int, dam: int, target: int) -> None:
    from quickmud.entities.handler import affect_enchant, extract_obj
    from quickmud.world.index import Affect

    if target == C.TARGET_ROOM:  # "nail objects on the floor"
        for obj in list(vo.contents):
            acid_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target == C.TARGET_CHAR:  # "do the effect on a victim": "let's toast some gear"
        for obj in list(vo.carrying):
            acid_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target != C.TARGET_OBJ:
        return
    obj = vo  # "toast an object"
    if obj.extra_flags & (C.ITEM_BURN_PROOF | C.ITEM_NOPURGE) or number_range(0, 4) == 0:
        return
    chance = _chance(level, dam)
    if obj.extra_flags & C.ITEM_BLESS:
        chance -= 5
    chance -= obj.level * 2
    kind = obj.item_type
    if kind in (C.ITEM_CONTAINER, C.ITEM_CORPSE_PC, C.ITEM_CORPSE_NPC):
        msg = "$p fumes and dissolves."
    elif kind == C.ITEM_ARMOR:
        msg = "$p is pitted and etched."
    elif kind == C.ITEM_CLOTHING:
        msg = "$p is corroded into scrap."
    elif kind in (C.ITEM_STAFF, C.ITEM_WAND):
        chance -= 10
        msg = "$p corrodes and breaks."
    elif kind == C.ITEM_SCROLL:
        chance += 10
        msg = "$p is burned into waste."
    else:
        return
    chance = max(5, min(chance, 95))
    if number_percent() > chance:
        return
    _show(msg, obj)
    if obj.item_type == C.ITEM_ARMOR:  # "etch it"
        affect_enchant(obj)
        for paf in obj.affected:
            if paf.location == C.APPLY_AC:
                paf.type = -1
                paf.modifier = sh_int(paf.modifier + 1)
                paf.level = max(paf.level, level)
                break
        else:  # "needs a new affect"
            obj.affected.insert(0, Affect(where=C.TO_AFFECTS, type=-1, level=level, duration=-1,
                                          location=C.APPLY_AC, modifier=1, bitvector=0))
        if obj.carried_by is not None and obj.wear_loc != C.WEAR_NONE:
            for i in range(4):
                obj.carried_by.armor[i] = sh_int(obj.carried_by.armor[i] + 1)
        return
    if obj.contains:  # "get rid of the object": "dump contents"
        _dump_contents(obj, level, dam, acid_effect)
    extract_obj(_game(), obj)


# C: effects.c cold_effect
def cold_effect(vo, level: int, dam: int, target: int) -> None:
    from quickmud.entities.handler import affect_join, extract_obj
    from quickmud.net.act import act
    from quickmud.systems.magic import saves_spell
    from quickmud.systems.update import gain_condition
    from quickmud.world.index import Affect
    from quickmud.world.lookup import skill_lookup

    if target == C.TARGET_ROOM:  # "nail objects on the floor"
        for obj in list(vo.contents):
            cold_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target == C.TARGET_CHAR:  # "whack a character"
        victim = vo
        # "chill touch effect"
        if not saves_spell(c_div(level, 4) + c_div(dam, 20), victim, C.DAM_COLD):
            act("$n turns blue and shivers.", victim, None, None, C.TO_ROOM)
            act("A chill sinks deep into your bones.", victim, None, None, C.TO_CHAR)
            affect_join(victim, Affect(where=C.TO_AFFECTS, type=skill_lookup("chill touch"), level=level,
                                       duration=6, location=C.APPLY_STR, modifier=-1, bitvector=0))
        # "hunger! (warmth sucked out"
        if not victim.is_npc:
            gain_condition(victim, C.COND_HUNGER, c_div(dam, 20))
        for obj in list(victim.carrying):  # "let's toast some gear"
            cold_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target != C.TARGET_OBJ:
        return
    obj = vo  # "toast an object"
    if obj.extra_flags & (C.ITEM_BURN_PROOF | C.ITEM_NOPURGE) or number_range(0, 4) == 0:
        return
    chance = _chance(level, dam)
    if obj.extra_flags & C.ITEM_BLESS:
        chance -= 5
    chance -= obj.level * 2
    if obj.item_type == C.ITEM_POTION:
        msg = "$p freezes and shatters!"
        chance += 25
    elif obj.item_type == C.ITEM_DRINK_CON:
        msg = "$p freezes and shatters!"
        chance += 5
    else:
        return
    chance = max(5, min(chance, 95))
    if number_percent() > chance:
        return
    _show(msg, obj)
    extract_obj(_game(), obj)


# C: effects.c fire_effect
def fire_effect(vo, level: int, dam: int, target: int) -> None:
    from quickmud.entities.handler import affect_to_char, extract_obj, is_affected
    from quickmud.net.act import act
    from quickmud.systems.magic import saves_spell
    from quickmud.systems.update import gain_condition
    from quickmud.world.index import Affect
    from quickmud.world.lookup import skill_lookup

    if target == C.TARGET_ROOM:  # "nail objects on the floor"
        for obj in list(vo.contents):
            fire_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target == C.TARGET_CHAR:  # "do the effect on a victim"
        victim = vo
        # "chance of blindness"
        if (not is_affected(victim, C.AFF_BLIND)
                and not saves_spell(c_div(level, 4) + c_div(dam, 20), victim, C.DAM_FIRE)):
            act("$n is blinded by smoke!", victim, None, None, C.TO_ROOM)
            act("Your eyes tear up from smoke...you can't see a thing!", victim, None, None, C.TO_CHAR)
            affect_to_char(victim, Affect(where=C.TO_AFFECTS, type=skill_lookup("fire breath"), level=level,
                                          duration=number_range(0, c_div(level, 10)), location=C.APPLY_HITROLL,
                                          modifier=-4, bitvector=C.AFF_BLIND))
        if not victim.is_npc:  # "getting thirsty"
            gain_condition(victim, C.COND_THIRST, c_div(dam, 20))
        for obj in list(victim.carrying):  # "let's toast some gear!"
            fire_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target != C.TARGET_OBJ:
        return
    obj = vo  # "toast an object"
    if obj.extra_flags & (C.ITEM_BURN_PROOF | C.ITEM_NOPURGE) or number_range(0, 4) == 0:
        return
    chance = _chance(level, dam)
    if obj.extra_flags & C.ITEM_BLESS:
        chance -= 5
    chance -= obj.level * 2
    kind = obj.item_type
    if kind == C.ITEM_CONTAINER:
        msg = "$p ignites and burns!"
    elif kind == C.ITEM_POTION:
        chance += 25
        msg = "$p bubbles and boils!"
    elif kind == C.ITEM_SCROLL:
        chance += 50
        msg = "$p crackles and burns!"
    elif kind == C.ITEM_STAFF:
        chance += 10
        msg = "$p smokes and chars!"
    elif kind == C.ITEM_WAND:
        msg = "$p sparks and sputters!"
    elif kind == C.ITEM_FOOD:
        msg = "$p blackens and crisps!"
    elif kind == C.ITEM_PILL:
        msg = "$p melts and drips!"
    else:
        return
    chance = max(5, min(chance, 95))
    if number_percent() > chance:
        return
    _show(msg, obj)
    if obj.contains:  # "dump the contents"
        _dump_contents(obj, level, dam, fire_effect)
    extract_obj(_game(), obj)


# C: effects.c poison_effect
def poison_effect(vo, level: int, dam: int, target: int) -> None:
    from quickmud.entities.handler import affect_join
    from quickmud.net.act import act
    from quickmud.net.output import send_to_char
    from quickmud.systems.magic import saves_spell
    from quickmud.world.index import Affect
    from quickmud.world.lookup import GSN

    if target == C.TARGET_ROOM:  # "nail objects on the floor"
        for obj in list(vo.contents):
            poison_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target == C.TARGET_CHAR:  # "do the effect on a victim"
        victim = vo
        # "chance of poisoning"
        if not saves_spell(c_div(level, 4) + c_div(dam, 20), victim, C.DAM_POISON):
            send_to_char("You feel poison coursing through your veins.\n\r", victim)
            act("$n looks very ill.", victim, None, None, C.TO_ROOM)
            affect_join(victim, Affect(where=C.TO_AFFECTS, type=GSN["gsn_poison"], level=level,
                                       duration=c_div(level, 2), location=C.APPLY_STR, modifier=-1,
                                       bitvector=C.AFF_POISON))
        for obj in list(victim.carrying):  # "equipment"
            poison_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target != C.TARGET_OBJ:
        return
    obj = vo  # "do some poisoning"
    if obj.extra_flags & (C.ITEM_BURN_PROOF | C.ITEM_BLESS) or number_range(0, 4) == 0:
        return
    chance = _chance(level, dam)
    chance -= obj.level * 2
    if obj.item_type == C.ITEM_FOOD:
        pass
    elif obj.item_type == C.ITEM_DRINK_CON:
        if obj.value[0] == obj.value[1]:
            return
    else:
        return
    chance = max(5, min(chance, 95))
    if number_percent() > chance:
        return
    obj.value[3] = 1


# C: effects.c shock_effect
def shock_effect(vo, level: int, dam: int, target: int) -> None:
    from quickmud.entities.handler import extract_obj
    from quickmud.net.output import send_to_char
    from quickmud.systems.magic import saves_spell

    if target == C.TARGET_ROOM:
        for obj in list(vo.contents):
            shock_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target == C.TARGET_CHAR:
        victim = vo
        # "daze and confused?"
        if not saves_spell(c_div(level, 4) + c_div(dam, 20), victim, C.DAM_LIGHTNING):
            send_to_char("Your muscles stop responding.\n\r", victim)
            victim.daze = sh_int(max(victim.daze, max(12, c_div(level, 4) + c_div(dam, 20))))  # DAZE_STATE
        for obj in list(victim.carrying):  # "toast some gear"
            shock_effect(obj, level, dam, C.TARGET_OBJ)
        return
    if target != C.TARGET_OBJ:
        return
    obj = vo
    if obj.extra_flags & (C.ITEM_BURN_PROOF | C.ITEM_NOPURGE) or number_range(0, 4) == 0:
        return
    chance = _chance(level, dam)
    if obj.extra_flags & C.ITEM_BLESS:
        chance -= 5
    chance -= obj.level * 2
    if obj.item_type in (C.ITEM_WAND, C.ITEM_STAFF):
        chance += 10
        msg = "$p overloads and explodes!"
    elif obj.item_type == C.ITEM_JEWELRY:
        chance -= 10
        msg = "$p is fused into a worthless lump."
    else:
        return
    chance = max(5, min(chance, 95))
    if number_percent() > chance:
        return
    _show(msg, obj)
    extract_obj(_game(), obj)
