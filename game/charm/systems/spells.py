"""magic.c's spells (#74: acid blast to fly in PR 3, the rest in PR 4), and magic2.c's farsight, portal and nexus.

Each spell takes the C's arguments: the skill number, the caster's level for it, the caster, the target (a
character, an object, or None) and what the target is (TARGET_CHAR, TARGET_OBJ or TARGET_NONE). magic.cast_spell
finds them here by the C function's name; one that isn't here raises NotPorted.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/magic.c, src/magic2.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, sh_int
from charm.core.rng import dice, number_fuzzy, number_percent, number_range
from charm.core.strings import upper
from charm.data import constants as C
from charm.entities.handler import (affect_find, affect_join, affect_remove_obj, affect_strip, affect_to_char,
                                    affect_to_obj, is_affected, is_affected_by, is_evil, is_good)
from charm.net.act import act
from charm.net.output import send_to_char
from charm.world.index import Affect
from charm.world.lookup import GSN, skill_lookup


def _game():
    from charm.entities import game as game_module

    return game_module.current


def _damage(ch, victim, dam: int, sn: int, dam_type: int, show: bool) -> bool:
    from charm.systems.fight import damage

    return damage(ch, victim, dam, sn, dam_type, show)


def _saves(level: int, victim, dam_type: int) -> bool:
    from charm.systems.magic import saves_spell

    return saves_spell(level, victim, dam_type)


def _is_neutral(ch) -> bool:
    return not is_good(ch) and not is_evil(ch)


def _af(where: int, sn: int, level: int, duration: int, location: int, modifier: int, bitvector: int) -> Affect:
    return Affect(where=where, type=sn, level=level, duration=duration, location=location, modifier=modifier,
                  bitvector=bitvector)


def _table_damage(table: tuple, level: int) -> tuple[int, int]:
    """The damage-table spells: level capped to the table, and number_range(half, double) of its entry."""
    level = min(level, len(table) - 1)
    level = max(0, level)
    return level, number_range(c_div(table[level], 2), table[level] * 2)


def _already(ch, victim, mine: str, theirs: str) -> None:
    if victim is ch:
        send_to_char(mine, ch)
    else:
        act(theirs, ch, None, victim, C.TO_CHAR)


def _char_list_from_start(game):
    from charm.systems.fight import _char_list_from

    return _char_list_from(game.char_list, 0)


# C: magic.c spell_acid_blast
def spell_acid_blast(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    dam = dice(level, 12)
    if _saves(level, victim, C.DAM_ACID):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_ACID, True)


# C: magic.c spell_armor
def spell_armor(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(victim, sn):
        _already(ch, victim, "You are already armored.\n\r", "$N is already armored.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 24, C.APPLY_AC, -20, 0))
    send_to_char("You feel someone protecting you.\n\r", victim)
    if ch is not victim:
        act("$N is protected by your magic.", ch, None, victim, C.TO_CHAR)


# C: magic.c spell_bless
def spell_bless(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.magic import saves_dispel

    if target == C.TARGET_OBJ:  # "deal with the object case first"
        obj = vo
        if obj.extra_flags & C.ITEM_BLESS:
            act("$p is already blessed.", ch, obj, None, C.TO_CHAR)
            return
        if obj.extra_flags & C.ITEM_EVIL:
            paf = affect_find(obj.affected, GSN["gsn_curse"])
            if not saves_dispel(level, paf.level if paf is not None else obj.level, 0):
                if paf is not None:
                    affect_remove_obj(obj, paf)
                act("$p glows a pale blue.", ch, obj, None, C.TO_ALL)
                obj.extra_flags &= ~C.ITEM_EVIL
                return
            act("The evil of $p is too powerful for you to overcome.", ch, obj, None, C.TO_CHAR)
            return
        affect_to_obj(obj, _af(C.TO_OBJECT, sn, level, 6 + level, C.APPLY_SAVES, -1, C.ITEM_BLESS))
        act("$p glows with a holy aura.", ch, obj, None, C.TO_ALL)
        if obj.wear_loc != C.WEAR_NONE:
            ch.saving_throw = sh_int(ch.saving_throw - 1)  # the caster's: do_cast only finds what the caster carries
        return
    victim = vo  # "character target"
    if victim.position == C.POS_FIGHTING or is_affected_by(victim, sn):
        _already(ch, victim, "You are already blessed.\n\r", "$N already has divine favor.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 6 + level, C.APPLY_HITROLL, c_div(level, 8), 0))
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 6 + level, C.APPLY_SAVING_SPELL, 0 - c_div(level, 8), 0))
    send_to_char("You feel righteous.\n\r", victim)
    if ch is not victim:
        act("You grant $N the favor of your god.", ch, None, victim, C.TO_CHAR)


# C: magic.c spell_blindness
def spell_blindness(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_BLIND) or _saves(level, victim, C.DAM_OTHER):
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 1 + level, C.APPLY_HITROLL, -4, C.AFF_BLIND))
    send_to_char("You are blinded!\n\r", victim)
    act("$n appears to be blinded.", victim, None, None, C.TO_ROOM)


_BURNING_HANDS = (0, 0, 0, 0, 0, 14, 17, 20, 23, 26, 29, 29, 29, 30, 30, 31, 31, 32, 32, 33, 33, 34, 34, 35, 35, 36,
                  36, 37, 37, 38, 38, 39, 39, 40, 40, 41, 41, 42, 42, 43, 43, 44, 44, 45, 45, 46, 46, 47, 47, 48, 48)


# C: magic.c spell_burning_hands
def spell_burning_hands(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_BURNING_HANDS, level)
    if _saves(level, victim, C.DAM_FIRE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_FIRE, True)


def _is_outside(ch) -> bool:
    """IS_OUTSIDE."""
    return not ch.in_room.room_flags & C.ROOM_INDOORS


# C: magic.c spell_call_lightning
def spell_call_lightning(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import is_awake

    game = _game()
    if not _is_outside(ch):
        send_to_char("You must be out of doors.\n\r", ch)
        return
    if game.weather_info.sky < C.SKY_RAINING:
        send_to_char("You need bad weather.\n\r", ch)
        return
    dam = dice(c_div(level, 2), 8)
    send_to_char("Mota's lightning strikes your foes!\n\r", ch)
    act("$n calls Mota's lightning to strike $s foes!", ch, None, None, C.TO_ROOM)
    for vch in _char_list_from_start(game):
        if vch.in_room is None:
            continue
        if vch.in_room is ch.in_room:
            if vch is not ch and ((not vch.is_npc) if ch.is_npc else vch.is_npc):
                _damage(ch, vch, c_div(dam, 2) if _saves(level, vch, C.DAM_LIGHTNING) else dam, sn,
                        C.DAM_LIGHTNING, True)
            continue
        if vch.in_room.area is ch.in_room.area and _is_outside(vch) and is_awake(vch):
            send_to_char("Lightning flashes in the sky.\n\r", vch)


# C: magic.c spell_calm
def spell_calm(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT calm spell stops all fighting in the room"."""
    from charm.entities.handler import is_immortal
    from charm.systems.fight import stop_fighting

    mlevel = 0
    count = 0
    high_level = 0
    # "get sum of all mobile levels in the room"
    for vch in ch.in_room.people:
        if vch.position == C.POS_FIGHTING:
            count += 1
            mlevel += vch.level if vch.is_npc else c_div(vch.level, 2)
            high_level = max(high_level, vch.level)
    # "compute chance of stopping combat"
    chance = 4 * level - high_level + 2 * count
    if is_immortal(ch):  # "always works"
        mlevel = 0
    if number_range(0, chance) >= mlevel:  # "hard to stop large fights"
        for vch in list(ch.in_room.people):
            if vch.is_npc and (vch.imm_flags & C.IMM_MAGIC or vch.act & C.ACT_UNDEAD):
                return
            if (is_affected(vch, C.AFF_CALM) or is_affected(vch, C.AFF_BERSERK)
                    or is_affected_by(vch, skill_lookup("frenzy"))):
                return
            send_to_char("A wave of calm passes over you.\n\r", vch)
            if vch.fighting is not None or vch.position == C.POS_FIGHTING:
                stop_fighting(_game(), vch, False)
            modifier = -5 if not vch.is_npc else -2
            for location in (C.APPLY_HITROLL, C.APPLY_DAMROLL):
                affect_to_char(vch, _af(C.TO_AFFECTS, sn, level, c_div(level, 4), location, modifier, C.AFF_CALM))


# (spell, the message to the room when it's dispelled, or None) for check_dispel's run through, in the C's order;
# sic: "existance" (#79)
_DISPELLABLE = (
    ("armor", None), ("bless", None), ("blindness", "$n is no longer blinded."),
    ("calm", "$n no longer looks so peaceful..."), ("change sex", "$n looks more like $mself again."),
    ("charm person", "$n regains $s free will."), ("chill touch", "$n looks warmer."), ("curse", None),
    ("detect evil", None), ("detect good", None), ("detect hidden", None), ("detect invis", None),
    ("detect magic", None), ("faerie fire", "$n's outline fades."), ("fly", "$n falls to the ground!"),
    ("frenzy", "$n no longer looks so wild."), ("giant strength", "$n no longer looks so mighty."),
    ("haste", "$n is no longer moving so quickly."), ("infravision", None),
    ("invis", "$n fades into existance."), ("mass invis", "$n fades into existance."), ("pass door", None),
    ("protection evil", None), ("protection good", None),
    ("sanctuary", "The white aura around $n's body vanishes."), ("shield", "The shield protecting $n vanishes."),
    ("sleep", None), ("slow", "$n is no longer moving so slowly."),
    ("stone skin", "$n's skin regains its normal texture."), ("weaken", "$n looks stronger."),
)


def _dispel_all(level: int, ch, victim, sanctuary_bit: bool) -> None:
    """The run through the spells that cancellation and dispel magic share. Dispel magic (sanctuary_bit) also
    tries a sanctuary that's a bit, not a spell, as a mob's is, right after the spell."""
    from charm.systems.magic import check_dispel, saves_dispel

    found = False
    for name, msg in _DISPELLABLE:
        if check_dispel(level, victim, skill_lookup(name)):
            found = True
            if msg is not None:
                act(msg, victim, None, None, C.TO_ROOM)
        if sanctuary_bit and name == "sanctuary":
            if (is_affected(victim, C.AFF_SANCTUARY) and not saves_dispel(level, victim.level, -1)
                    and not is_affected_by(victim, skill_lookup("sanctuary"))):
                victim.affected_by &= ~C.AFF_SANCTUARY
                act("The white aura around $n's body vanishes.", victim, None, None, C.TO_ROOM)
                found = True
    send_to_char("Ok.\n\r" if found else "Spell failed.\n\r", ch)


# C: magic.c spell_cancellation
def spell_cancellation(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level += 2
    if ((not ch.is_npc and victim.is_npc and not (is_affected(ch, C.AFF_CHARM) and ch.master is victim))
            or (ch.is_npc and not victim.is_npc)):
        send_to_char("You failed, try dispel magic.\n\r", ch)
        return
    # "unlike dispel magic, the victim gets NO save"
    _dispel_all(level, ch, victim, False)


# C: magic.c spell_cause_light
def spell_cause_light(sn: int, level: int, ch, vo, target: int) -> None:
    _damage(ch, vo, dice(1, 8) + c_div(level, 3), sn, C.DAM_HARM, True)


# C: magic.c spell_cause_critical
def spell_cause_critical(sn: int, level: int, ch, vo, target: int) -> None:
    _damage(ch, vo, dice(3, 8) + level - 6, sn, C.DAM_HARM, True)


# C: magic.c spell_cause_serious
def spell_cause_serious(sn: int, level: int, ch, vo, target: int) -> None:
    _damage(ch, vo, dice(2, 8) + c_div(level, 2), sn, C.DAM_HARM, True)


# C: magic.c spell_chain_lightning
def spell_chain_lightning(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.core.errors import CWouldCrash
    from charm.entities.handler import next_in_room
    from charm.systems.fight import is_safe_spell

    victim = vo
    # "first strike"
    act("A lightning bolt leaps from $n's hand and arcs to $N.", ch, None, victim, C.TO_ROOM)
    act("A lightning bolt leaps from your hand and arcs to $N.", ch, None, victim, C.TO_CHAR)
    act("A lightning bolt leaps from $n's hand and hits you!", ch, None, victim, C.TO_VICT)
    dam = dice(level, 6)
    if _saves(level, victim, C.DAM_LIGHTNING):
        dam = c_div(dam, 3)
    _damage(ch, victim, dam, sn, C.DAM_LIGHTNING, True)
    last_vict = victim
    level -= 4  # "decrement damage"
    # "new targets"
    while level > 0:
        found = False
        if ch.in_room is None:
            raise CWouldCrash("magic.c spell_chain_lightning: the caster was killed, and the C reads its room")
        people = ch.in_room.people
        tmp_vict = people[0] if people else None
        while tmp_vict is not None:
            next_vict = next_in_room(tmp_vict)
            if not is_safe_spell(ch, tmp_vict, True) and tmp_vict is not last_vict:
                found = True
                last_vict = tmp_vict
                act("The bolt arcs to $n!", tmp_vict, None, None, C.TO_ROOM)
                act("The bolt hits you!", tmp_vict, None, None, C.TO_CHAR)
                dam = dice(level, 6)
                if _saves(level, tmp_vict, C.DAM_LIGHTNING):
                    dam = c_div(dam, 3)
                _damage(ch, tmp_vict, dam, sn, C.DAM_LIGHTNING, True)
                level -= 4  # "decrement damage"
            tmp_vict = next_vict
        if not found:  # "no target found, hit the caster"
            if last_vict is ch:  # "no double hits"
                act("The bolt seems to have fizzled out.", ch, None, None, C.TO_ROOM)
                act("The bolt grounds out through your body.", ch, None, None, C.TO_CHAR)
                return
            last_vict = ch
            act("The bolt arcs to $n...whoops!", ch, None, None, C.TO_ROOM)
            send_to_char("You are struck by your own lightning!\n\r", ch)
            dam = dice(level, 6)
            if _saves(level, ch, C.DAM_LIGHTNING):
                dam = c_div(dam, 3)
            _damage(ch, ch, dam, sn, C.DAM_LIGHTNING, True)
            level -= 4  # "decrement damage"
        # "now go back and find more targets"


# C: magic.c spell_change_sex
def spell_change_sex(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(victim, sn):
        _already(ch, victim, "You've already been changed.\n\r", "$N has already had $s(?) sex changed.")
        return
    if _saves(level, victim, C.DAM_OTHER):
        return
    while True:
        modifier = number_range(0, 2) - victim.sex
        if modifier != 0:
            break
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 2 * level, C.APPLY_SEX, modifier, 0))
    send_to_char("You feel different.\n\r", victim)
    act("$n doesn't look like $mself anymore...", victim, None, None, C.TO_ROOM)


# C: magic.c spell_charm_person
def spell_charm_person(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.comm import add_follower, stop_follower
    from charm.systems.fight import is_safe

    victim = vo
    if is_safe(ch, victim):
        return
    if victim is ch:
        send_to_char("You like yourself even better!\n\r", ch)
        return
    if (is_affected(victim, C.AFF_CHARM) or is_affected(ch, C.AFF_CHARM) or level < victim.level
            or victim.imm_flags & C.IMM_CHARM or _saves(level, victim, C.DAM_CHARM)):
        return
    if victim.in_room.room_flags & C.ROOM_LAW:
        send_to_char("The mayor does not allow charming in the city limits.\n\r", ch)
        return
    game = _game()
    if victim.master is not None:
        stop_follower(game, victim)
    add_follower(game, victim, ch)
    victim.leader = ch
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, number_fuzzy(c_div(level, 4)), 0, 0, C.AFF_CHARM))
    act("Isn't $n just so nice?", ch, None, victim, C.TO_VICT)
    if ch is not victim:
        act("$N looks at you with adoring eyes.", ch, None, victim, C.TO_CHAR)


_CHILL_TOUCH = (0, 0, 0, 6, 7, 8, 9, 12, 13, 13, 13, 14, 14, 14, 15, 15, 15, 16, 16, 16, 17, 17, 17, 18, 18, 18, 19,
                19, 19, 20, 20, 20, 21, 21, 21, 22, 22, 22, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27)


# C: magic.c spell_chill_touch
def spell_chill_touch(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_CHILL_TOUCH, level)
    if not _saves(level, victim, C.DAM_COLD):
        act("$n turns blue and shivers.", victim, None, None, C.TO_ROOM)
        affect_join(victim, _af(C.TO_AFFECTS, sn, level, 6, C.APPLY_STR, -1, 0))
    else:
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_COLD, True)


_COLOUR_SPRAY = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 30, 35, 40, 45, 50, 55, 55, 55, 56, 57, 58, 58, 59, 60, 61, 61, 62,
                 63, 64, 64, 65, 66, 67, 67, 68, 69, 70, 70, 71, 72, 73, 73, 74, 75, 76, 76, 77, 78, 79, 79)


# C: magic.c spell_colour_spray
def spell_colour_spray(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_COLOUR_SPRAY, level)
    if _saves(level, victim, C.DAM_LIGHT):
        dam = c_div(dam, 2)
    else:
        spell_blindness(skill_lookup("blindness"), c_div(level, 2), ch, victim, C.TARGET_CHAR)
    _damage(ch, victim, dam, sn, C.DAM_LIGHT, True)


# C: magic.c spell_continual_light
def spell_continual_light(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.create import create_object
    from charm.entities.handler import get_obj_carry, obj_to_room

    game = _game()
    if game.target_name != "":  # "do a glow on some object"
        light = get_obj_carry(ch, game.target_name, ch)
        if light is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
        if light.extra_flags & C.ITEM_GLOW:
            act("$p is already glowing.", ch, light, None, C.TO_CHAR)
            return
        light.extra_flags |= C.ITEM_GLOW
        act("$p glows with a white light.", ch, light, None, C.TO_ALL)
        return
    light = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_LIGHT_BALL), 0)
    obj_to_room(light, ch.in_room)
    act("$n twiddles $s thumbs and $p appears.", ch, light, None, C.TO_ROOM)
    act("You twiddle your thumbs and $p appears.", ch, light, None, C.TO_CHAR)


# C: magic.c spell_control_weather
def spell_control_weather(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.core.strings import str_cmp

    game = _game()
    if str_cmp(game.target_name, "better"):
        game.weather_info.change += dice(c_div(level, 3), 4)
    elif str_cmp(game.target_name, "worse"):
        game.weather_info.change -= dice(c_div(level, 3), 4)
    else:
        send_to_char("Do you want it to get better or worse?\n\r", ch)
    send_to_char("Ok.\n\r", ch)


# C: magic.c spell_create_food
def spell_create_food(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.create import create_object
    from charm.entities.handler import obj_to_room

    game = _game()
    mushroom = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_MUSHROOM), 0)
    mushroom.value[0] = c_div(level, 2)
    mushroom.value[1] = level
    obj_to_room(mushroom, ch.in_room)
    act("$p suddenly appears.", ch, mushroom, None, C.TO_ROOM)
    act("$p suddenly appears.", ch, mushroom, None, C.TO_CHAR)


# C: magic.c spell_create_rose
def spell_create_rose(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.create import create_object
    from charm.entities.handler import obj_to_char

    game = _game()
    rose = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_ROSE), 0)
    act("$n has created a beautiful red rose.", ch, rose, None, C.TO_ROOM)
    send_to_char("You create a beautiful red rose.\n\r", ch)
    obj_to_char(rose, ch)


# C: magic.c spell_create_spring
def spell_create_spring(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.create import create_object
    from charm.entities.handler import obj_to_room

    game = _game()
    spring = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_SPRING), 0)
    spring.timer = level
    obj_to_room(spring, ch.in_room)
    act("$p flows from the ground.", ch, spring, None, C.TO_ROOM)
    act("$p flows from the ground.", ch, spring, None, C.TO_CHAR)


# C: magic.c spell_create_water
def spell_create_water(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import is_name

    obj = vo
    if obj.item_type != C.ITEM_DRINK_CON:
        send_to_char("It is unable to hold water.\n\r", ch)
        return
    if obj.value[2] != C.LIQ_WATER and obj.value[1] != 0:
        send_to_char("It contains some other liquid.\n\r", ch)
        return
    water = min(level * (4 if _game().weather_info.sky >= C.SKY_RAINING else 2), obj.value[0] - obj.value[1])
    if water > 0:
        obj.value[2] = C.LIQ_WATER
        obj.value[1] += water
        if not is_name("water", obj.name):
            obj.name = "%s water" % obj.name
        act("$p is filled.", ch, obj, None, C.TO_CHAR)


def _cure(sn_name: str, level: int, ch, victim, not_yet: tuple[str, str], cured: tuple[str, str]) -> None:
    """cure blindness, disease and poison: not affected, the dispel, and what each says."""
    from charm.systems.magic import check_dispel

    sn = GSN[sn_name]
    if not is_affected_by(victim, sn):
        _already(ch, victim, not_yet[0], not_yet[1])
        return
    if check_dispel(level, victim, sn):
        send_to_char(cured[0], victim)
        act(cured[1], victim, None, None, C.TO_ROOM)
    else:
        send_to_char("Spell failed.\n\r", ch)


# C: magic.c spell_cure_blindness
def spell_cure_blindness(sn: int, level: int, ch, vo, target: int) -> None:
    _cure("gsn_blindness", level, ch, vo, ("You aren't blind.\n\r", "$N doesn't appear to be blinded."),
          ("Your vision returns!\n\r", "$n is no longer blinded."))


def _heal(ch, victim, heal: int) -> None:
    from charm.systems.fight import update_pos

    victim.hit = sh_int(min(victim.hit + heal, victim.max_hit))
    update_pos(victim)
    send_to_char("You feel better!\n\r", victim)
    if ch is not victim:
        send_to_char("Ok.\n\r", ch)


# C: magic.c spell_cure_critical
def spell_cure_critical(sn: int, level: int, ch, vo, target: int) -> None:
    _heal(ch, vo, dice(3, 8) + level - 6)


# C: magic.c spell_cure_disease
def spell_cure_disease(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT added to cure plague"."""
    _cure("gsn_plague", level, ch, vo, ("You aren't ill.\n\r", "$N doesn't appear to be diseased."),
          ("Your sores vanish.\n\r", "$n looks relieved as $s sores vanish."))


# C: magic.c spell_cure_light
def spell_cure_light(sn: int, level: int, ch, vo, target: int) -> None:
    _heal(ch, vo, dice(1, 8) + c_div(level, 3))


# C: magic.c spell_cure_poison
def spell_cure_poison(sn: int, level: int, ch, vo, target: int) -> None:
    _cure("gsn_poison", level, ch, vo, ("You aren't poisoned.\n\r", "$N doesn't appear to be poisoned."),
          ("A warm feeling runs through your body.\n\r", "$n looks much better."))


# C: magic.c spell_cure_serious
def spell_cure_serious(sn: int, level: int, ch, vo, target: int) -> None:
    _heal(ch, vo, dice(2, 8) + c_div(level, 2))


# C: magic.c spell_curse
def spell_curse(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.magic import saves_dispel

    if target == C.TARGET_OBJ:  # "deal with the object case first"
        obj = vo
        if obj.extra_flags & C.ITEM_EVIL:
            act("$p is already filled with evil.", ch, obj, None, C.TO_CHAR)
            return
        if obj.extra_flags & C.ITEM_BLESS:
            paf = affect_find(obj.affected, skill_lookup("bless"))
            if not saves_dispel(level, paf.level if paf is not None else obj.level, 0):
                if paf is not None:
                    affect_remove_obj(obj, paf)
                act("$p glows with a red aura.", ch, obj, None, C.TO_ALL)
                obj.extra_flags &= ~C.ITEM_BLESS
                return
            act("The holy aura of $p is too powerful for you to overcome.", ch, obj, None, C.TO_CHAR)
            return
        affect_to_obj(obj, _af(C.TO_OBJECT, sn, level, 2 * level, C.APPLY_SAVES, +1, C.ITEM_EVIL))
        act("$p glows with a malevolent aura.", ch, obj, None, C.TO_ALL)
        if obj.wear_loc != C.WEAR_NONE:
            ch.saving_throw = sh_int(ch.saving_throw + 1)  # the caster's: do_cast only finds what the caster carries
        return
    victim = vo  # "character curses"
    if is_affected(victim, C.AFF_CURSE) or _saves(level, victim, C.DAM_NEGATIVE):
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 2 * level, C.APPLY_HITROLL, -1 * c_div(level, 8),
                               C.AFF_CURSE))
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 2 * level, C.APPLY_SAVING_SPELL, c_div(level, 8),
                               C.AFF_CURSE))
    send_to_char("You feel unclean.\n\r", victim)
    if ch is not victim:
        act("$N looks very uncomfortable.", ch, None, victim, C.TO_CHAR)


# C: magic.c spell_demonfire
def spell_demonfire(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT replacement demonfire spell"."""
    victim = vo
    if not ch.is_npc and not is_evil(ch):
        victim = ch
        send_to_char("The demons turn upon you!\n\r", ch)
    ch.alignment = sh_int(max(-1000, ch.alignment - 50))
    if victim is not ch:
        act("$n calls forth the demons of Hell upon $N!", ch, None, victim, C.TO_ROOM)
        act("$n has assailed you with the demons of Hell!", ch, None, victim, C.TO_VICT)
        send_to_char("You conjure forth the demons of hell!\n\r", ch)
    dam = dice(level, 10)
    if _saves(level, victim, C.DAM_NEGATIVE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_NEGATIVE, True)
    spell_curse(GSN["gsn_curse"], c_div(3 * level, 4), ch, victim, C.TARGET_CHAR)


def _detect(sn: int, level: int, ch, victim, bit: int, already: tuple[str, str], feel: str) -> None:
    """The detect spells: one bit for level hours."""
    if is_affected(victim, bit):
        _already(ch, victim, already[0], already[1])
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level, C.APPLY_NONE, 0, bit))
    send_to_char(feel, victim)
    if ch is not victim:
        send_to_char("Ok.\n\r", ch)


# C: magic.c spell_detect_evil
def spell_detect_evil(sn: int, level: int, ch, vo, target: int) -> None:
    _detect(sn, level, ch, vo, C.AFF_DETECT_EVIL, ("You can already sense evil.\n\r", "$N can already detect evil."),
            "Your eyes tingle.\n\r")


# C: magic.c spell_detect_good
def spell_detect_good(sn: int, level: int, ch, vo, target: int) -> None:
    _detect(sn, level, ch, vo, C.AFF_DETECT_GOOD, ("You can already sense good.\n\r", "$N can already detect good."),
            "Your eyes tingle.\n\r")


# C: magic.c spell_detect_hidden
def spell_detect_hidden(sn: int, level: int, ch, vo, target: int) -> None:
    _detect(sn, level, ch, vo, C.AFF_DETECT_HIDDEN,
            ("You are already as alert as you can be. \n\r", "$N can already sense hidden lifeforms."),
            "Your awareness improves.\n\r")


# C: magic.c spell_detect_invis
def spell_detect_invis(sn: int, level: int, ch, vo, target: int) -> None:
    _detect(sn, level, ch, vo, C.AFF_DETECT_INVIS,
            ("You can already see invisible.\n\r", "$N can already see invisible things."), "Your eyes tingle.\n\r")


# C: magic.c spell_detect_magic
def spell_detect_magic(sn: int, level: int, ch, vo, target: int) -> None:
    _detect(sn, level, ch, vo, C.AFF_DETECT_MAGIC,
            ("You can already sense magical auras.\n\r", "$N can already detect magic."), "Your eyes tingle.\n\r")


# C: magic.c spell_detect_poison
def spell_detect_poison(sn: int, level: int, ch, vo, target: int) -> None:
    obj = vo
    if obj.item_type in (C.ITEM_DRINK_CON, C.ITEM_FOOD):
        send_to_char("You smell poisonous fumes.\n\r" if obj.value[3] != 0 else "It looks delicious.\n\r", ch)
    else:
        send_to_char("It doesn't look poisoned.\n\r", ch)


def _dispel_alignment(sn: int, level: int, ch, victim, protected: str, dam_type: int) -> None:
    if is_good(victim) if dam_type == C.DAM_HOLY else is_evil(victim):
        act(protected, ch, None, victim, C.TO_ROOM)
        return
    if _is_neutral(victim):
        act("$N does not seem to be affected.", ch, None, victim, C.TO_CHAR)
        return
    if victim.hit > ch.level * 4:
        dam = dice(level, 4)
    else:
        # UMAX (victim->hit, dice (level, 4)) is a macro: the dice are rolled to compare, and again for the result
        # if they win (sic, #79)
        dam = victim.hit if victim.hit > dice(level, 4) else dice(level, 4)
    if _saves(level, victim, dam_type):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, dam_type, True)


# C: magic.c spell_dispel_evil
def spell_dispel_evil(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if not ch.is_npc and is_evil(ch):
        victim = ch
    _dispel_alignment(sn, level, ch, victim, "Mota protects $N.", C.DAM_HOLY)


# C: magic.c spell_dispel_good
def spell_dispel_good(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if not ch.is_npc and is_good(ch):
        victim = ch
    _dispel_alignment(sn, level, ch, victim, "$N is protected by $S evil.", C.DAM_NEGATIVE)


# C: magic.c spell_dispel_magic
def spell_dispel_magic(sn: int, level: int, ch, vo, target: int) -> None:
    """"modified for enhanced use"."""
    victim = vo
    if _saves(level, victim, C.DAM_OTHER):
        send_to_char("You feel a brief tingling sensation.\n\r", victim)
        send_to_char("You failed.\n\r", ch)
        return
    _dispel_all(level, ch, victim, True)  # "begin running through the spells"


# C: magic.c spell_earthquake
def spell_earthquake(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.fight import is_safe_spell

    send_to_char("The earth trembles beneath your feet!\n\r", ch)
    act("$n makes the earth tremble and shiver.", ch, None, None, C.TO_ROOM)
    for vch in _char_list_from_start(_game()):
        if vch.in_room is None:
            continue
        if vch.in_room is ch.in_room:
            if vch is not ch and not is_safe_spell(ch, vch, True):
                if is_affected(vch, C.AFF_FLYING):
                    _damage(ch, vch, 0, sn, C.DAM_BASH, True)
                else:
                    _damage(ch, vch, level + dice(2, 8), sn, C.DAM_BASH, True)
            continue
        if vch.in_room.area is ch.in_room.area:
            send_to_char("The earth trembles and shivers.\n\r", vch)


def _enchant_fail(obj, locations: tuple[int, ...], squared: int, other: int) -> tuple[int, dict]:
    """The enchant spells' failure chance from the bonuses the object has: the prototype's, unless it's been
    enchanted, then its own. Each bonus at one of locations adds squared times its square, any other other. Also
    which of locations were found."""
    fail = 25  # "base 25% chance of failure"
    found: dict[int, bool] = {loc: False for loc in locations}
    lists = ([] if obj.enchanted else [obj.index.affected]) + [obj.affected]
    for affects in lists:
        for paf in affects:
            if paf.location in found:
                found[paf.location] = True
                fail += squared * (paf.modifier * paf.modifier)
            else:  # "things get a little harder"
                fail += other
    return fail, found


def _disenchant(ch, obj) -> None:
    act("$p glows brightly, then fades...oops.", ch, obj, None, C.TO_CHAR)
    act("$p glows brightly, then fades.", ch, obj, None, C.TO_ROOM)
    obj.enchanted = True
    obj.affected.clear()  # "remove all affects"
    obj.extra_flags = 0  # "clear all flags"


def _enchant_bonus(obj, sn: int, level: int, location: int, found: bool, added: int, where: int,
                   hum: bool) -> None:
    """Add added to the object's bonus at location, or a new affect for it."""
    if found:
        for paf in obj.affected:
            if paf.location == location:
                paf.type = sn
                paf.modifier = sh_int(paf.modifier + added)
                paf.level = max(paf.level, level)
                if hum and paf.modifier > 4:
                    obj.extra_flags |= C.ITEM_HUM
    else:  # "add a new affect"
        obj.affected.insert(0, _af(where, sn, level, -1, location, added, 0))


# C: magic.c spell_enchant_armor
def spell_enchant_armor(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import affect_enchant, extract_obj

    obj = vo
    if obj.item_type != C.ITEM_ARMOR:
        send_to_char("That isn't an armor.\n\r", ch)
        return
    if obj.wear_loc != -1:
        send_to_char("The item must be carried to be enchanted.\n\r", ch)
        return
    fail, found = _enchant_fail(obj, (C.APPLY_AC,), 5, 20)
    # "apply other modifiers"
    fail -= level
    if obj.extra_flags & C.ITEM_BLESS:
        fail -= 15
    if obj.extra_flags & C.ITEM_GLOW:
        fail -= 5
    fail = max(5, min(fail, 85))
    result = number_percent()
    # "the moment of truth"
    if result < c_div(fail, 5):  # "item destroyed"
        act("$p flares blindingly... and evaporates!", ch, obj, None, C.TO_CHAR)
        act("$p flares blindingly... and evaporates!", ch, obj, None, C.TO_ROOM)
        extract_obj(_game(), obj)
        return
    if result < c_div(fail, 3):  # "item disenchanted"
        _disenchant(ch, obj)
        return
    if result <= fail:  # "failed, no bad result"
        send_to_char("Nothing seemed to happen.\n\r", ch)
        return
    affect_enchant(obj)  # "okay, move all the old flags into new vectors if we have to"
    if result <= 90 - c_div(level, 5):  # "success!"
        act("$p shimmers with a gold aura.", ch, obj, None, C.TO_CHAR)
        act("$p shimmers with a gold aura.", ch, obj, None, C.TO_ROOM)
        obj.extra_flags |= C.ITEM_MAGIC
        added = -1
    else:  # "exceptional enchant"
        act("$p glows a brillant gold!", ch, obj, None, C.TO_CHAR)
        act("$p glows a brillant gold!", ch, obj, None, C.TO_ROOM)
        obj.extra_flags |= C.ITEM_MAGIC | C.ITEM_GLOW
        added = -2
    # "now add the enchantments"
    if obj.level < C.LEVEL_HERO:
        obj.level = min(C.LEVEL_HERO - 1, obj.level + 1)
    _enchant_bonus(obj, sn, level, C.APPLY_AC, found[C.APPLY_AC], added, C.TO_OBJECT, False)


# C: magic.c spell_enchant_weapon
def spell_enchant_weapon(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import affect_enchant, extract_obj

    obj = vo
    if obj.item_type != C.ITEM_WEAPON:
        send_to_char("That isn't a weapon.\n\r", ch)
        return
    if obj.wear_loc != -1:
        send_to_char("The item must be carried to be enchanted.\n\r", ch)
        return
    fail, found = _enchant_fail(obj, (C.APPLY_HITROLL, C.APPLY_DAMROLL), 2, 25)
    # "apply other modifiers"
    fail -= c_div(3 * level, 2)
    if obj.extra_flags & C.ITEM_BLESS:
        fail -= 15
    if obj.extra_flags & C.ITEM_GLOW:
        fail -= 5
    fail = max(5, min(fail, 95))
    result = number_percent()
    # "the moment of truth"
    if result < c_div(fail, 5):  # "item destroyed"
        act("$p shivers violently and explodes!", ch, obj, None, C.TO_CHAR)
        act("$p shivers violently and explodeds!", ch, obj, None, C.TO_ROOM)  # sic (#79)
        extract_obj(_game(), obj)
        return
    if result < c_div(fail, 2):  # "item disenchanted"
        _disenchant(ch, obj)
        return
    if result <= fail:  # "failed, no bad result"
        send_to_char("Nothing seemed to happen.\n\r", ch)
        return
    affect_enchant(obj)  # "okay, move all the old flags into new vectors if we have to"
    if result <= 100 - c_div(level, 5):  # "success!"
        act("$p glows blue.", ch, obj, None, C.TO_CHAR)
        act("$p glows blue.", ch, obj, None, C.TO_ROOM)
        obj.extra_flags |= C.ITEM_MAGIC
        added = 1
    else:  # "exceptional enchant"
        act("$p glows a brillant blue!", ch, obj, None, C.TO_CHAR)
        act("$p glows a brillant blue!", ch, obj, None, C.TO_ROOM)
        obj.extra_flags |= C.ITEM_MAGIC | C.ITEM_GLOW
        added = 2
    # "now add the enchantments"
    if obj.level < C.LEVEL_HERO - 1:
        obj.level = min(C.LEVEL_HERO - 1, obj.level + 1)
    _enchant_bonus(obj, sn, level, C.APPLY_DAMROLL, found[C.APPLY_DAMROLL], added, C.TO_OBJECT, True)
    # sic: the new hitroll affect's where is new_affect's zero, TO_AFFECTS, not TO_OBJECT (#79)
    _enchant_bonus(obj, sn, level, C.APPLY_HITROLL, found[C.APPLY_HITROLL], added, C.TO_AFFECTS, True)


# C: magic.c spell_energy_drain
def spell_energy_drain(sn: int, level: int, ch, vo, target: int) -> None:
    """"Drain XP, MANA, HP. Caster gains HP."."""
    from charm.systems.update import gain_exp

    victim = vo
    if victim is not ch:
        ch.alignment = sh_int(max(-1000, ch.alignment - 50))
    if _saves(level, victim, C.DAM_NEGATIVE):
        send_to_char("You feel a momentary chill.\n\r", victim)
        return
    if victim.level <= 2:
        dam = ch.hit + 1
    else:
        gain_exp(victim, 0 - number_range(c_div(level, 2), c_div(3 * level, 2)))
        victim.mana = sh_int(c_div(victim.mana, 2))
        victim.move = sh_int(c_div(victim.move, 2))
        dam = dice(1, level)
        ch.hit = sh_int(ch.hit + dam)
    send_to_char("You feel your life slipping away!\n\r", victim)
    send_to_char("Wow....what a rush!\n\r", ch)
    _damage(ch, victim, dam, sn, C.DAM_NEGATIVE, True)


_FIREBALL = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 82, 84, 86, 88,
             90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124, 126, 128, 130)


# C: magic.c spell_fireball
def spell_fireball(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_FIREBALL, level)
    if _saves(level, victim, C.DAM_FIRE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_FIRE, True)


# C: magic.c spell_fireproof
def spell_fireproof(sn: int, level: int, ch, vo, target: int) -> None:
    obj = vo
    if obj.extra_flags & C.ITEM_BURN_PROOF:
        act("$p is already protected from burning.", ch, obj, None, C.TO_CHAR)
        return
    affect_to_obj(obj, _af(C.TO_OBJECT, sn, level, number_fuzzy(c_div(level, 4)), C.APPLY_NONE, 0,
                           C.ITEM_BURN_PROOF))
    act("You protect $p from fire.", ch, obj, None, C.TO_CHAR)
    act("$p is surrounded by a protective aura.", ch, obj, None, C.TO_ROOM)


# C: magic.c spell_flamestrike
def spell_flamestrike(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    dam = dice(6 + c_div(level, 2), 8)
    if _saves(level, victim, C.DAM_FIRE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_FIRE, True)


# C: magic.c spell_faerie_fire
def spell_faerie_fire(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_FAERIE_FIRE):
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level, C.APPLY_AC, 2 * level, C.AFF_FAERIE_FIRE))
    send_to_char("You are surrounded by a pink outline.\n\r", victim)
    act("$n is surrounded by a pink outline.", victim, None, None, C.TO_ROOM)


# C: magic.c spell_faerie_fog
def spell_faerie_fog(sn: int, level: int, ch, vo, target: int) -> None:
    act("$n conjures a cloud of purple smoke.", ch, None, None, C.TO_ROOM)
    send_to_char("You conjure a cloud of purple smoke.\n\r", ch)
    for ich in list(ch.in_room.people):
        if ich.invis_level > 0:
            continue
        if ich is ch or _saves(level, ich, C.DAM_OTHER):
            continue
        affect_strip(ich, GSN["gsn_invis"])
        affect_strip(ich, GSN["gsn_mass_invis"])
        affect_strip(ich, GSN["gsn_sneak"])
        ich.affected_by &= ~(C.AFF_HIDE | C.AFF_INVISIBLE | C.AFF_SNEAK)
        act("$n is revealed!", ich, None, None, C.TO_ROOM)
        send_to_char("You are revealed!\n\r", ich)


# C: magic.c spell_floating_disc
def spell_floating_disc(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.obj import wear_obj
    from charm.entities.create import create_object
    from charm.entities.handler import get_eq_char, obj_to_char

    floating = get_eq_char(ch, C.WEAR_FLOAT)
    if floating is not None and floating.extra_flags & C.ITEM_NOREMOVE:
        act("You can't remove $p.", ch, floating, None, C.TO_CHAR)
        return
    game = _game()
    disc = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_DISC), 0)
    disc.value[0] = ch.level * 10  # "10 pounds per level capacity"
    disc.value[3] = ch.level * 5  # "5 pounds per level max per item"
    disc.timer = ch.level * 2 - number_range(0, c_div(level, 2))
    act("$n has created a floating black disc.", ch, None, None, C.TO_ROOM)
    send_to_char("You create a floating disc.\n\r", ch)
    obj_to_char(disc, ch)
    wear_obj(ch, disc, True)


# C: magic.c spell_fly
def spell_fly(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_FLYING):
        _already(ch, victim, "You are already airborne.\n\r", "$N doesn't need your help to fly.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level + 3, 0, 0, C.AFF_FLYING))
    send_to_char("Your feet rise off the ground.\n\r", victim)
    act("$n's feet rise off the ground.", victim, None, None, C.TO_ROOM)


# -- the second half (#74, PR 4): frenzy to the breaths, and magic2.c ---------------------------------------------

def _plus_by_level(level: int) -> int:
    """1 + (level >= 18) + (level >= 25) + (level >= 32): giant strength's and haste's bonus."""
    return 1 + (level >= 18) + (level >= 25) + (level >= 32)


def _same_alignment(ch, victim) -> bool:
    return ((is_good(ch) and is_good(victim)) or (is_evil(ch) and is_evil(victim))
            or (_is_neutral(ch) and _is_neutral(victim)))


def _look_auto(ch) -> None:
    from charm.commands.info import do_look

    do_look(ch, "auto")


# C: magic.c spell_frenzy
def spell_frenzy(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT clerical berserking spell"."""
    victim = vo
    if is_affected_by(victim, sn) or is_affected(victim, C.AFF_BERSERK):
        _already(ch, victim, "You are already in a frenzy.\n\r", "$N is already in a frenzy.")
        return
    if is_affected_by(victim, skill_lookup("calm")):
        _already(ch, victim, "Why don't you just relax for a while?\n\r",
                 "$N doesn't look like $e wants to fight anymore.")
        return
    if ((is_good(ch) and not is_good(victim)) or (_is_neutral(ch) and not _is_neutral(victim))
            or (is_evil(ch) and not is_evil(victim))):
        act("Your god doesn't seem to like $N", ch, None, victim, C.TO_CHAR)
        return
    for location in (C.APPLY_HITROLL, C.APPLY_DAMROLL):
        affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, c_div(level, 3), location, c_div(level, 6), 0))
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, c_div(level, 3), C.APPLY_AC, 10 * c_div(level, 12), 0))
    send_to_char("You are filled with holy wrath!\n\r", victim)
    act("$n gets a wild look in $s eyes!", victim, None, None, C.TO_ROOM)


def _travel_refused(ch, victim, level: int, safe_from: bool, dam_type: int, saves_first: bool) -> bool:
    """gate's, portal's and nexus's shared refusals (nexus adds its own about the caster's room)."""
    from charm.entities.handler import can_see_room, is_clan, is_same_clan

    if (victim is None or victim is ch or victim.in_room is None or not can_see_room(ch, victim.in_room)
            or victim.in_room.room_flags & (C.ROOM_SAFE | C.ROOM_PRIVATE | C.ROOM_SOLITARY | C.ROOM_NO_RECALL)
            or ch.in_room.room_flags & C.ROOM_NO_RECALL):
        return True
    if safe_from and ch.in_room.room_flags & C.ROOM_SAFE:
        return True
    if victim.level >= level + 3:
        return True
    if saves_first:  # gate: the clan rule before the level and the save
        if is_clan(victim) and not is_same_clan(ch, victim):
            return True
    if not victim.is_npc and victim.level >= C.LEVEL_HERO:  # "NOT trust"
        return True
    if victim.is_npc and victim.imm_flags & C.IMM_SUMMON:
        return True
    if victim.is_npc and _saves(level, victim, dam_type):
        return True
    if not saves_first and is_clan(victim) and not is_same_clan(ch, victim):
        return True
    return False


# C: magic.c spell_gate
def spell_gate(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT ROM-style gate"."""
    from charm.entities.handler import char_from_room, char_to_room, get_char_world

    victim = get_char_world(_game(), ch, _game().target_name)
    if _travel_refused(ch, victim, level, False, C.DAM_OTHER, True):
        send_to_char("You failed.\n\r", ch)
        return
    gate_pet = ch.pet is not None and ch.in_room is ch.pet.in_room
    act("$n steps through a gate and vanishes.", ch, None, None, C.TO_ROOM)
    send_to_char("You step through a gate and vanish.\n\r", ch)
    char_from_room(ch)
    char_to_room(ch, victim.in_room)
    act("$n has arrived through a gate.", ch, None, None, C.TO_ROOM)
    _look_auto(ch)
    if gate_pet:
        pet = ch.pet
        act("$n steps through a gate and vanishes.", pet, None, None, C.TO_ROOM)
        send_to_char("You step through a gate and vanish.\n\r", pet)
        char_from_room(pet)
        char_to_room(pet, victim.in_room)
        act("$n has arrived through a gate.", pet, None, None, C.TO_ROOM)
        _look_auto(pet)


# C: magic.c spell_giant_strength
def spell_giant_strength(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(victim, sn):
        _already(ch, victim, "You are already as strong as you can get!\n\r", "$N can't get any stronger.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level, C.APPLY_STR, _plus_by_level(level), 0))
    send_to_char("Your muscles surge with heightened power!\n\r", victim)
    act("$n's muscles surge with heightened power.", victim, None, None, C.TO_ROOM)


# C: magic.c spell_harm
def spell_harm(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    # UMAX (20, victim->hit - dice (1, 4)) is a macro: the die is rolled to compare, and again for the result if
    # it wins (sic, #81)
    dam = 20 if 20 > victim.hit - dice(1, 4) else victim.hit - dice(1, 4)
    if _saves(level, victim, C.DAM_HARM):
        dam = min(50, c_div(dam, 2))
    dam = min(100, dam)
    _damage(ch, victim, dam, sn, C.DAM_HARM, True)


# C: magic.c spell_haste
def spell_haste(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT haste spell"."""
    from charm.systems.magic import check_dispel

    victim = vo
    if is_affected_by(victim, sn) or is_affected(victim, C.AFF_HASTE) or victim.off_flags & C.OFF_FAST:
        _already(ch, victim, "You can't move any faster!\n\r", "$N is already moving as fast as $E can.")
        return
    if is_affected(victim, C.AFF_SLOW):
        if not check_dispel(level, victim, skill_lookup("slow")):
            if victim is not ch:
                send_to_char("Spell failed.\n\r", ch)
            send_to_char("You feel momentarily faster.\n\r", victim)
            return
        act("$n is moving less slowly.", victim, None, None, C.TO_ROOM)
        return
    duration = c_div(level, 2) if victim is ch else c_div(level, 4)
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, duration, C.APPLY_DEX, _plus_by_level(level), C.AFF_HASTE))
    send_to_char("You feel yourself moving more quickly.\n\r", victim)
    act("$n is moving more quickly.", victim, None, None, C.TO_ROOM)
    if ch is not victim:
        send_to_char("Ok.\n\r", ch)


# C: magic.c spell_heal
def spell_heal(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.fight import update_pos

    victim = vo
    victim.hit = sh_int(min(victim.hit + 100, victim.max_hit))
    update_pos(victim)
    send_to_char("A warm feeling fills your body.\n\r", victim)
    if ch is not victim:
        send_to_char("Ok.\n\r", ch)


# C: magic.c spell_heat_metal
def spell_heat_metal(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.obj import remove_obj
    from charm.entities.handler import can_drop_obj, get_curr_stat, obj_from_char, obj_to_room

    victim = vo
    dam = 0
    fail = True
    if not _saves(level + 2, victim, C.DAM_FIRE) and not victim.imm_flags & C.IMM_FIRE:
        for obj_lose in list(victim.carrying):
            if (number_range(1, 2 * level) > obj_lose.level and not _saves(level, victim, C.DAM_FIRE)
                    and not obj_lose.extra_flags & (C.ITEM_NONMETAL | C.ITEM_BURN_PROOF)):
                if obj_lose.item_type == C.ITEM_ARMOR:
                    if obj_lose.wear_loc != -1:  # "remove the item"
                        if (can_drop_obj(victim, obj_lose)
                                and c_div(obj_lose.weight, 10) < number_range(1, 2 * get_curr_stat(victim,
                                                                                                   C.STAT_DEX))
                                and remove_obj(victim, obj_lose.wear_loc, True)):
                            act("$n yelps and throws $p to the ground!", victim, obj_lose, None, C.TO_ROOM)
                            act("You remove and drop $p before it burns you.", victim, obj_lose, None, C.TO_CHAR)
                            dam += c_div(number_range(1, obj_lose.level), 3)
                            obj_from_char(obj_lose)
                            obj_to_room(obj_lose, victim.in_room)
                        else:  # "stuck on the body! ouch!"
                            act("Your skin is seared by $p!", victim, obj_lose, None, C.TO_CHAR)
                            dam += number_range(1, obj_lose.level)
                    else:  # "drop it if we can"
                        dam += _heat_drop(victim, obj_lose, "$n yelps and throws $p to the ground!")
                    fail = False
                elif obj_lose.item_type == C.ITEM_WEAPON:
                    if obj_lose.wear_loc != -1:  # "try to drop it"
                        if obj_lose.value[4] & C.WEAPON_FLAMING:
                            continue
                        if can_drop_obj(victim, obj_lose) and remove_obj(victim, obj_lose.wear_loc, True):
                            act("$n is burned by $p, and throws it to the ground.", victim, obj_lose, None,
                                C.TO_ROOM)
                            send_to_char("You throw your red-hot weapon to the ground!\n\r", victim)
                            dam += 1
                            obj_from_char(obj_lose)
                            obj_to_room(obj_lose, victim.in_room)
                        else:  # "YOWCH!"
                            send_to_char("Your weapon sears your flesh!\n\r", victim)
                            dam += number_range(1, obj_lose.level)
                    else:  # "drop it if we can"
                        dam += _heat_drop(victim, obj_lose, "$n throws a burning hot $p to the ground!")
                    fail = False
    if fail:
        send_to_char("Your spell had no effect.\n\r", ch)
        send_to_char("You feel momentarily warmer.\n\r", victim)
    else:  # "damage!"
        if _saves(level, victim, C.DAM_FIRE):
            dam = c_div(2 * dam, 3)
        _damage(ch, victim, dam, sn, C.DAM_FIRE, True)


def _heat_drop(victim, obj, room_msg: str) -> int:
    """heat metal on something carried, not worn: dropped if it can be, or it sears. The damage it adds."""
    from charm.entities.handler import can_drop_obj, obj_from_char, obj_to_room

    if can_drop_obj(victim, obj):
        act(room_msg, victim, obj, None, C.TO_ROOM)
        act("You and drop $p before it burns you.", victim, obj, None, C.TO_CHAR)  # sic (#81)
        dam = c_div(number_range(1, obj.level), 6)
        obj_from_char(obj)
        obj_to_room(obj, victim.in_room)
        return dam
    act("Your skin is seared by $p!", victim, obj, None, C.TO_CHAR)  # "cannot drop"
    return c_div(number_range(1, obj.level), 2)


# C: magic.c spell_holy_word
def spell_holy_word(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT really nasty high-level attack spell"."""
    from charm.entities.handler import next_in_room
    from charm.systems.fight import is_safe_spell

    bless_num = skill_lookup("bless")
    curse_num = skill_lookup("curse")
    frenzy_num = skill_lookup("frenzy")
    act("$n utters a word of divine power!", ch, None, None, C.TO_ROOM)
    send_to_char("You utter a word of divine power.\n\r", ch)
    people = ch.in_room.people
    vch = people[0] if people else None
    while vch is not None:
        vch_next = next_in_room(vch)
        if _same_alignment(ch, vch):
            send_to_char("You feel full more powerful.\n\r", vch)
            spell_frenzy(frenzy_num, level, ch, vch, C.TARGET_CHAR)
            spell_bless(bless_num, level, ch, vch, C.TARGET_CHAR)
        elif (is_good(ch) and is_evil(vch)) or (is_evil(ch) and is_good(vch)):
            if not is_safe_spell(ch, vch, True):
                spell_curse(curse_num, level, ch, vch, C.TARGET_CHAR)
                send_to_char("You are struck down!\n\r", vch)
                _damage(ch, vch, dice(level, 6), sn, C.DAM_ENERGY, True)
        elif _is_neutral(ch):
            if not is_safe_spell(ch, vch, True):
                spell_curse(curse_num, c_div(level, 2), ch, vch, C.TARGET_CHAR)
                send_to_char("You are struck down!\n\r", vch)
                _damage(ch, vch, dice(level, 4), sn, C.DAM_ENERGY, True)
        vch = vch_next
    send_to_char("You feel drained.\n\r", ch)
    ch.move = 0
    ch.hit = sh_int(c_div(ch.hit, 2))


def _skill_name(n: int) -> str:
    from charm.core.errors import CWouldCrash
    from charm.data.skills import SKILL_TABLE

    if n >= len(SKILL_TABLE):
        raise CWouldCrash(f"magic.c spell_identify: skill {n} is a zeroed row of skill_table, and its NULL name is "
                          "sent")
    return SKILL_TABLE[n].name


def _identify_bit(paf, weapon_too: bool) -> str:
    """The line for an affect's bit. Sic: the affect, object and weapon lines end in "\\n" alone (#81)."""
    from charm.entities.handler import affect_bit_name, extra_bit_name, imm_bit_name, weapon_bit_name

    where = paf.where
    if where == C.TO_AFFECTS:
        return "Adds %s affect.\n" % affect_bit_name(paf.bitvector)
    if where == C.TO_OBJECT:
        return "Adds %s object flag.\n" % extra_bit_name(paf.bitvector)
    if where == C.TO_WEAPON and weapon_too:
        return "Adds %s weapon flags.\n" % weapon_bit_name(paf.bitvector)
    if where == C.TO_IMMUNE:
        return "Adds immunity to %s.\n" % imm_bit_name(paf.bitvector)
    if where == C.TO_RESIST:
        return "Adds resistance to %s.\n\r" % imm_bit_name(paf.bitvector)
    if where == C.TO_VULN:
        return "Adds vulnerability to %s.\n\r" % imm_bit_name(paf.bitvector)
    return "Unknown bit %d: %d\n\r" % (where, paf.bitvector)


_WEAPON_KIND = {C.WEAPON_EXOTIC: "exotic", C.WEAPON_SWORD: "sword", C.WEAPON_DAGGER: "dagger",
                C.WEAPON_SPEAR: "spear/staff", C.WEAPON_MACE: "mace/club", C.WEAPON_AXE: "axe",
                C.WEAPON_FLAIL: "flail", C.WEAPON_WHIP: "whip", C.WEAPON_POLEARM: "polearm"}


# C: magic.c spell_identify
def spell_identify(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.obj import _liquid
    from charm.entities.handler import affect_loc_name, cont_bit_name, extra_bit_name, item_name, weapon_bit_name

    obj = vo
    v = obj.value
    send_to_char("Object '%s' is type %s, extra flags %s.\n\rWeight is %d, value is %d, level is %d.\n\r"
                 % (obj.name, item_name(obj.item_type), extra_bit_name(obj.extra_flags), c_div(obj.weight, 10),
                    obj.cost, obj.level), ch)
    kind = obj.item_type
    if kind in (C.ITEM_SCROLL, C.ITEM_POTION, C.ITEM_PILL):
        send_to_char("Level %d spells of:" % v[0], ch)
        for n in v[1:5]:
            if 0 <= n < C.MAX_SKILL:
                send_to_char(" '", ch)
                send_to_char(_skill_name(n), ch)
                send_to_char("'", ch)
        send_to_char(".\n\r", ch)
    elif kind in (C.ITEM_WAND, C.ITEM_STAFF):
        send_to_char("Has %d charges of level %d" % (v[2], v[0]), ch)
        if 0 <= v[3] < C.MAX_SKILL:
            send_to_char(" '", ch)
            send_to_char(_skill_name(v[3]), ch)
            send_to_char("'", ch)
        send_to_char(".\n\r", ch)
    elif kind == C.ITEM_DRINK_CON:
        liq = _liquid(v[2], "spell_identify")
        send_to_char("It holds %s-colored %s.\n\r" % (liq.liq_color, liq.liq_name), ch)
    elif kind == C.ITEM_CONTAINER:
        send_to_char("Capacity: %d#  Maximum weight: %d#  flags: %s\n\r" % (v[0], v[3], cont_bit_name(v[1])), ch)
        if v[4] != 100:
            send_to_char("Weight multiplier: %d%%\n\r" % v[4], ch)
    elif kind == C.ITEM_WEAPON:
        send_to_char("Weapon type is ", ch)
        send_to_char("%s.\n\r" % _WEAPON_KIND.get(v[0], "unknown"), ch)
        if obj.index.new_format:
            send_to_char("Damage is %dd%d (average %d).\n\r" % (v[1], v[2], c_div((1 + v[2]) * v[1], 2)), ch)
        else:
            send_to_char("Damage is %d to %d (average %d).\n\r" % (v[1], v[2], c_div(v[1] + v[2], 2)), ch)
        if v[4]:  # "weapon flags"
            send_to_char("Weapons flags: %s\n\r" % weapon_bit_name(v[4]), ch)
    elif kind == C.ITEM_ARMOR:
        send_to_char("Armor class is %d pierce, %d bash, %d slash, and %d vs. magic.\n\r" % (v[0], v[1], v[2], v[3]),
                     ch)
    if not obj.enchanted:
        for paf in obj.index.affected:
            if paf.location != C.APPLY_NONE and paf.modifier != 0:
                send_to_char("Affects %s by %d.\n\r" % (affect_loc_name(paf.location), paf.modifier), ch)
                if paf.bitvector:
                    send_to_char(_identify_bit(paf, False), ch)
    for paf in obj.affected:
        if paf.location != C.APPLY_NONE and paf.modifier != 0:
            send_to_char("Affects %s by %d" % (affect_loc_name(paf.location), paf.modifier), ch)
            send_to_char(", %d hours.\n\r" % paf.duration if paf.duration > -1 else ".\n\r", ch)
            if paf.bitvector:
                send_to_char(_identify_bit(paf, True), ch)


# C: magic.c spell_infravision
def spell_infravision(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_INFRARED):
        _already(ch, victim, "You can already see in the dark.\n\r", "$N already has infravision.\n\r")
        return
    act("$n's eyes glow red.\n\r", ch, None, None, C.TO_ROOM)  # sic: act adds a line end of its own too (#81)
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 2 * level, C.APPLY_NONE, 0, C.AFF_INFRARED))
    send_to_char("Your eyes glow red.\n\r", victim)


# C: magic.c spell_invis
def spell_invis(sn: int, level: int, ch, vo, target: int) -> None:
    if target == C.TARGET_OBJ:  # "object invisibility"
        obj = vo
        if obj.extra_flags & C.ITEM_INVIS:
            act("$p is already invisible.", ch, obj, None, C.TO_CHAR)
            return
        affect_to_obj(obj, _af(C.TO_OBJECT, sn, level, level + 12, C.APPLY_NONE, 0, C.ITEM_INVIS))
        act("$p fades out of sight.", ch, obj, None, C.TO_ALL)
        return
    victim = vo  # "character invisibility"
    if is_affected(victim, C.AFF_INVISIBLE):
        return
    act("$n fades out of existence.", victim, None, None, C.TO_ROOM)
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level + 12, C.APPLY_NONE, 0, C.AFF_INVISIBLE))
    send_to_char("You fade out of existence.\n\r", victim)


# C: magic.c spell_know_alignment
def spell_know_alignment(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    ap = victim.alignment
    if ap > 700:
        msg = "$N has a pure and good aura."
    elif ap > 350:
        msg = "$N is of excellent moral character."
    elif ap > 100:
        msg = "$N is often kind and thoughtful."
    elif ap > -100:
        msg = "$N doesn't have a firm moral commitment."
    elif ap > -350:
        msg = "$N lies to $S friends."
    elif ap > -700:
        msg = "$N is a black-hearted murderer."
    else:
        msg = "$N is the embodiment of pure evil!."
    act(msg, ch, None, victim, C.TO_CHAR)


_LIGHTNING_BOLT = (0, 0, 0, 0, 0, 0, 0, 0, 0, 25, 28, 31, 34, 37, 40, 40, 41, 42, 42, 43, 44, 44, 45, 46, 46, 47, 48,
                   48, 49, 50, 50, 51, 52, 52, 53, 54, 54, 55, 56, 56, 57, 58, 58, 59, 60, 60, 61, 62, 62, 63, 64)


# C: magic.c spell_lightning_bolt
def spell_lightning_bolt(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_LIGHTNING_BOLT, level)
    if _saves(level, victim, C.DAM_LIGHTNING):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_LIGHTNING, True)


# C: magic.c spell_locate_object
def spell_locate_object(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import can_see, can_see_obj, is_immortal, is_name, pers
    from charm.net.output import page_to_char

    game = _game()
    found = False
    number = 0
    max_found = 200 if is_immortal(ch) else 2 * level
    lines = []
    for obj in list(game.object_list):
        if (not can_see_obj(ch, obj) or not is_name(game.target_name, obj.name)
                or obj.extra_flags & C.ITEM_NOLOCATE or number_percent() > 2 * level or ch.level < obj.level):
            continue
        found = True
        number += 1
        in_obj = obj
        while in_obj.in_obj is not None:
            in_obj = in_obj.in_obj
        if in_obj.carried_by is not None and can_see(ch, in_obj.carried_by):
            buf = "one is carried by %s\n\r" % pers(in_obj.carried_by, ch)
        elif is_immortal(ch) and in_obj.in_room is not None:
            buf = "one is in %s [Room %d]\n\r" % (in_obj.in_room.name, in_obj.in_room.vnum)
        else:
            buf = "one is in %s\n\r" % ("somewhere" if in_obj.in_room is None else in_obj.in_room.name)
        if len(buf) >= C.MAX_INPUT_LENGTH:
            from charm.core.errors import CWouldCrash

            raise CWouldCrash("magic.c spell_locate_object: a line overflows buf[MAX_INPUT_LENGTH]")
        lines.append(upper(buf[0]) + buf[1:])  # buf[0] = UPPER (buf[0])
        if number >= max_found:
            break
    if not found:
        send_to_char("Nothing like that in heaven or earth.\n\r", ch)
    else:
        page_to_char("".join(lines), ch)


_MAGIC_MISSILE = (0, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 11,
                  11, 11, 11, 11, 12, 12, 12, 12, 12, 13, 13, 13, 13, 13, 14, 14, 14, 14, 14)


# C: magic.c spell_magic_missile
def spell_magic_missile(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_MAGIC_MISSILE, level)
    if _saves(level, victim, C.DAM_ENERGY):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_ENERGY, True)


# C: magic.c spell_mass_healing
def spell_mass_healing(sn: int, level: int, ch, vo, target: int) -> None:
    heal_num = skill_lookup("heal")
    refresh_num = skill_lookup("refresh")
    for gch in list(ch.in_room.people):
        if gch.is_npc == ch.is_npc:
            spell_heal(heal_num, level, ch, gch, C.TARGET_CHAR)
            spell_refresh(refresh_num, level, ch, gch, C.TARGET_CHAR)


# C: magic.c spell_mass_invis
def spell_mass_invis(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.comm import is_same_group

    for gch in list(ch.in_room.people):
        if not is_same_group(gch, ch) or is_affected(gch, C.AFF_INVISIBLE):
            continue
        act("$n slowly fades out of existence.", gch, None, None, C.TO_ROOM)
        send_to_char("You slowly fade out of existence.\n\r", gch)
        affect_to_char(gch, _af(C.TO_AFFECTS, sn, c_div(level, 2), 24, C.APPLY_NONE, 0, C.AFF_INVISIBLE))
    send_to_char("Ok.\n\r", ch)


# C: magic.c spell_pass_door
def spell_pass_door(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_PASS_DOOR):
        _already(ch, victim, "You are already out of phase.\n\r", "$N is already shifted out of phase.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, number_fuzzy(c_div(level, 4)), C.APPLY_NONE, 0,
                               C.AFF_PASS_DOOR))
    act("$n turns translucent.", victim, None, None, C.TO_ROOM)
    send_to_char("You turn translucent.\n\r", victim)


# C: magic.c spell_plague
def spell_plague(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT plague spell, very nasty"."""
    victim = vo
    if _saves(level, victim, C.DAM_DISEASE) or (victim.is_npc and victim.act & C.ACT_UNDEAD):
        if ch is victim:
            send_to_char("You feel momentarily ill, but it passes.\n\r", ch)
        else:
            act("$N seems to be unaffected.", ch, None, victim, C.TO_CHAR)
        return
    affect_join(victim, _af(C.TO_AFFECTS, sn, c_div(level * 3, 4), level, C.APPLY_STR, -5, C.AFF_PLAGUE))
    send_to_char("You scream in agony as plague sores erupt from your skin.\n\r", victim)
    act("$n screams in agony as plague sores erupt from $s skin.", victim, None, None, C.TO_ROOM)


# C: magic.c spell_poison
def spell_poison(sn: int, level: int, ch, vo, target: int) -> None:
    if target == C.TARGET_OBJ:
        obj = vo
        if obj.item_type in (C.ITEM_FOOD, C.ITEM_DRINK_CON):
            if obj.extra_flags & (C.ITEM_BLESS | C.ITEM_BURN_PROOF):
                act("Your spell fails to corrupt $p.", ch, obj, None, C.TO_CHAR)
                return
            obj.value[3] = 1
            act("$p is infused with poisonous vapors.", ch, obj, None, C.TO_ALL)
            return
        if obj.item_type == C.ITEM_WEAPON:
            if (obj.value[4] & (C.WEAPON_FLAMING | C.WEAPON_FROST | C.WEAPON_VAMPIRIC | C.WEAPON_SHARP
                                | C.WEAPON_VORPAL | C.WEAPON_SHOCKING)
                    or obj.extra_flags & (C.ITEM_BLESS | C.ITEM_BURN_PROOF)):
                act("You can't seem to envenom $p.", ch, obj, None, C.TO_CHAR)
                return
            if obj.value[4] & C.WEAPON_POISON:
                act("$p is already envenomed.", ch, obj, None, C.TO_CHAR)
                return
            affect_to_obj(obj, _af(C.TO_WEAPON, sn, c_div(level, 2), c_div(level, 8), 0, 0, C.WEAPON_POISON))
            act("$p is coated with deadly venom.", ch, obj, None, C.TO_ALL)
            return
        act("You can't poison $p.", ch, obj, None, C.TO_CHAR)
        return
    victim = vo
    if _saves(level, victim, C.DAM_POISON):
        act("$n turns slightly green, but it passes.", victim, None, None, C.TO_ROOM)
        send_to_char("You feel momentarily ill, but it passes.\n\r", victim)
        return
    affect_join(victim, _af(C.TO_AFFECTS, sn, level, level, C.APPLY_STR, -2, C.AFF_POISON))
    send_to_char("You feel very sick.\n\r", victim)
    act("$n looks very ill.", victim, None, None, C.TO_ROOM)


def _protection(sn: int, level: int, ch, victim, bit: int, feel: str, theirs: str) -> None:
    if is_affected(victim, C.AFF_PROTECT_EVIL) or is_affected(victim, C.AFF_PROTECT_GOOD):
        _already(ch, victim, "You are already protected.\n\r", "$N is already protected.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 24, C.APPLY_SAVING_SPELL, -1, bit))
    send_to_char(feel, victim)
    if ch is not victim:
        act(theirs, ch, None, victim, C.TO_CHAR)


# C: magic.c spell_protection_evil
def spell_protection_evil(sn: int, level: int, ch, vo, target: int) -> None:
    _protection(sn, level, ch, vo, C.AFF_PROTECT_EVIL, "You feel holy and pure.\n\r", "$N is protected from evil.")


# C: magic.c spell_protection_good
def spell_protection_good(sn: int, level: int, ch, vo, target: int) -> None:
    _protection(sn, level, ch, vo, C.AFF_PROTECT_GOOD, "You feel aligned with darkness.\n\r",
                "$N is protected from good.")


# C: magic.c spell_ray_of_truth
def spell_ray_of_truth(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.core.cint import int32

    victim = vo
    if is_evil(ch):
        victim = ch
        send_to_char("The energy explodes inside you!\n\r", ch)
    if victim is not ch:
        act("$n raises $s hand, and a blinding ray of light shoots forth!", ch, None, None, C.TO_ROOM)
        send_to_char("You raise your hand and a blinding ray of light shoots forth!\n\r", ch)
    if is_good(victim):
        act("$n seems unharmed by the light.", victim, None, victim, C.TO_ROOM)
        send_to_char("The light seems powerless to affect you.\n\r", victim)
        return
    dam = dice(level, 10)
    if _saves(level, victim, C.DAM_HOLY):
        dam = c_div(dam, 2)
    align = victim.alignment
    align -= 350
    if align < -1000:
        align = -1000 + c_div(align + 1000, 3)
    dam = c_div(int32(int32(dam * align) * align), 1000000)
    _damage(ch, victim, dam, sn, C.DAM_HOLY, True)
    spell_blindness(GSN["gsn_blindness"], c_div(3 * level, 4), ch, victim, C.TARGET_CHAR)


# C: magic.c spell_recharge
def spell_recharge(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import extract_obj

    obj = vo
    v = obj.value
    if obj.item_type not in (C.ITEM_WAND, C.ITEM_STAFF):
        send_to_char("That item does not carry charges.\n\r", ch)
        return
    if v[3] >= c_div(3 * level, 2):
        send_to_char("Your skills are not great enough for that.\n\r", ch)
        return
    if v[1] == 0:
        send_to_char("That item has already been recharged once.\n\r", ch)
        return
    chance = 40 + 2 * level
    chance -= v[3]  # "harder to do high-level spells"
    chance -= (v[1] - v[2]) * (v[1] - v[2])
    chance = max(c_div(level, 2), chance)
    percent = number_percent()
    if percent < c_div(chance, 2):
        act("$p glows softly.", ch, obj, None, C.TO_CHAR)
        act("$p glows softly.", ch, obj, None, C.TO_ROOM)
        v[2] = max(v[1], v[2])
        v[1] = 0
    elif percent <= chance:
        act("$p glows softly.", ch, obj, None, C.TO_CHAR)
        act("$p glows softly.", ch, obj, None, C.TO_CHAR)  # sic: twice to the caster, not to the room (#81)
        chargemax = v[1] - v[2]
        chargeback = max(1, c_div(chargemax * percent, 100)) if chargemax > 0 else 0
        v[2] += chargeback
        v[1] = 0
    elif percent <= min(95, c_div(3 * chance, 2)):
        send_to_char("Nothing seems to happen.\n\r", ch)
        if v[1] > 1:
            v[1] -= 1
    else:  # "whoops!"
        act("$p glows brightly and explodes!", ch, obj, None, C.TO_CHAR)
        act("$p glows brightly and explodes!", ch, obj, None, C.TO_ROOM)
        extract_obj(_game(), obj)


# C: magic.c spell_refresh
def spell_refresh(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    victim.move = sh_int(min(victim.move + level, victim.max_move))
    send_to_char("You feel fully refreshed!\n\r" if victim.max_move == victim.move else "You feel less tired.\n\r",
                 victim)
    if ch is not victim:
        send_to_char("Ok.\n\r", ch)


# C: magic.c spell_remove_curse
def spell_remove_curse(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.magic import check_dispel, saves_dispel

    if target == C.TARGET_OBJ:  # "do object cases first"
        obj = vo
        if obj.extra_flags & (C.ITEM_NODROP | C.ITEM_NOREMOVE):
            if not obj.extra_flags & C.ITEM_NOUNCURSE and not saves_dispel(level + 2, obj.level, 0):
                obj.extra_flags &= ~(C.ITEM_NODROP | C.ITEM_NOREMOVE)
                act("$p glows blue.", ch, obj, None, C.TO_ALL)
                return
            act("The curse on $p is beyond your power.", ch, obj, None, C.TO_CHAR)
            return
        act("There doesn't seem to be a curse on $p.", ch, obj, None, C.TO_CHAR)
        return
    victim = vo  # "characters"
    if check_dispel(level, victim, GSN["gsn_curse"]):
        send_to_char("You feel better.\n\r", victim)
        act("$n looks more relaxed.", victim, None, None, C.TO_ROOM)
    for obj in list(victim.carrying):
        if (obj.extra_flags & (C.ITEM_NODROP | C.ITEM_NOREMOVE)
                and not obj.extra_flags & C.ITEM_NOUNCURSE):  # "attempt to remove curse"
            if not saves_dispel(level, obj.level, 0):
                obj.extra_flags &= ~(C.ITEM_NODROP | C.ITEM_NOREMOVE)
                act("Your $p glows blue.", victim, obj, None, C.TO_CHAR)
                act("$n's $p glows blue.", victim, obj, None, C.TO_ROOM)
                break


# C: magic.c spell_sanctuary
def spell_sanctuary(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected(victim, C.AFF_SANCTUARY):
        _already(ch, victim, "You are already in sanctuary.\n\r", "$N is already in sanctuary.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, c_div(level, 6), C.APPLY_NONE, 0, C.AFF_SANCTUARY))
    act("$n is surrounded by a white aura.", victim, None, None, C.TO_ROOM)
    send_to_char("You are surrounded by a white aura.\n\r", victim)


# C: magic.c spell_shield
def spell_shield(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(victim, sn):
        _already(ch, victim, "You are already shielded from harm.\n\r", "$N is already protected by a shield.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, 8 + level, C.APPLY_AC, -20, 0))
    act("$n is surrounded by a force shield.", victim, None, None, C.TO_ROOM)
    send_to_char("You are surrounded by a force shield.\n\r", victim)


_SHOCKING_GRASP = (0, 0, 0, 0, 0, 0, 0, 20, 25, 29, 33, 36, 39, 39, 39, 40, 40, 41, 41, 42, 42, 43, 43, 44, 44, 45,
                   45, 46, 46, 47, 47, 48, 48, 49, 49, 50, 50, 51, 51, 52, 52, 53, 53, 54, 54, 55, 55, 56, 56, 57, 57)


# C: magic.c spell_shocking_grasp
def spell_shocking_grasp(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    level, dam = _table_damage(_SHOCKING_GRASP, level)
    if _saves(level, victim, C.DAM_LIGHTNING):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_LIGHTNING, True)


# C: magic.c spell_sleep
def spell_sleep(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import is_awake

    victim = vo
    if (is_affected(victim, C.AFF_SLEEP) or (victim.is_npc and victim.act & C.ACT_UNDEAD)
            or (level + 2) < victim.level or _saves(level - 4, victim, C.DAM_CHARM)):
        return
    affect_join(victim, _af(C.TO_AFFECTS, sn, level, 4 + level, C.APPLY_NONE, 0, C.AFF_SLEEP))
    if is_awake(victim):
        send_to_char("You feel very sleepy ..... zzzzzz.\n\r", victim)
        act("$n goes to sleep.", victim, None, None, C.TO_ROOM)
        victim.position = C.POS_SLEEPING


# C: magic.c spell_slow
def spell_slow(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.magic import check_dispel

    victim = vo
    if is_affected_by(victim, sn) or is_affected(victim, C.AFF_SLOW):
        _already(ch, victim, "You can't move any slower!\n\r", "$N can't get any slower than that.")
        return
    if _saves(level, victim, C.DAM_OTHER) or victim.imm_flags & C.IMM_MAGIC:
        if victim is not ch:
            send_to_char("Nothing seemed to happen.\n\r", ch)
        send_to_char("You feel momentarily lethargic.\n\r", victim)
        return
    if is_affected(victim, C.AFF_HASTE):
        if not check_dispel(level, victim, skill_lookup("haste")):
            if victim is not ch:
                send_to_char("Spell failed.\n\r", ch)
            send_to_char("You feel momentarily slower.\n\r", victim)
            return
        act("$n is moving less quickly.", victim, None, None, C.TO_ROOM)
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, c_div(level, 2), C.APPLY_DEX, -_plus_by_level(level),
                               C.AFF_SLOW))
    send_to_char("You feel yourself slowing d o w n...\n\r", victim)
    act("$n starts to move in slow motion.", victim, None, None, C.TO_ROOM)


# C: magic.c spell_stone_skin
def spell_stone_skin(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(ch, sn):  # the caster's: the spell is for yourself only, so the victim is the caster
        _already(ch, victim, "Your skin is already as hard as a rock.\n\r", "$N is already as hard as can be.")
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, level, C.APPLY_AC, -40, 0))
    act("$n's skin turns to stone.", victim, None, None, C.TO_ROOM)
    send_to_char("Your skin turns to stone.\n\r", victim)


# C: magic.c spell_summon
def spell_summon(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import char_from_room, char_to_room, get_char_world

    victim = get_char_world(_game(), ch, _game().target_name)
    if (victim is None or victim is ch or victim.in_room is None or ch.in_room.room_flags & C.ROOM_SAFE
            or victim.in_room.room_flags & (C.ROOM_SAFE | C.ROOM_PRIVATE | C.ROOM_SOLITARY | C.ROOM_NO_RECALL)
            or (victim.is_npc and victim.act & C.ACT_AGGRESSIVE) or victim.level >= level + 3
            or (not victim.is_npc and victim.level >= C.LEVEL_IMMORTAL) or victim.fighting is not None
            or (victim.is_npc and victim.imm_flags & C.IMM_SUMMON)
            or (victim.is_npc and victim.index.shop is not None)
            or (not victim.is_npc and victim.act & C.PLR_NOSUMMON)
            or (victim.is_npc and _saves(level, victim, C.DAM_OTHER))):
        send_to_char("You failed.\n\r", ch)
        return
    act("$n disappears suddenly.", victim, None, None, C.TO_ROOM)
    char_from_room(victim)
    char_to_room(victim, ch.in_room)
    act("$n arrives suddenly.", victim, None, None, C.TO_ROOM)
    act("$n has summoned you!", ch, None, victim, C.TO_VICT)
    _look_auto(victim)


# C: magic.c spell_teleport
def spell_teleport(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.move import get_random_room
    from charm.entities.handler import char_from_room, char_to_room

    victim = vo
    if (victim.in_room is None or victim.in_room.room_flags & C.ROOM_NO_RECALL
            or (victim is not ch and victim.imm_flags & C.IMM_SUMMON)
            or (not ch.is_npc and victim.fighting is not None)
            or (victim is not ch and _saves(level - 5, victim, C.DAM_OTHER))):
        send_to_char("You failed.\n\r", ch)
        return
    room = get_random_room(victim)
    if victim is not ch:
        send_to_char("You have been teleported!\n\r", victim)
    act("$n vanishes!", victim, None, None, C.TO_ROOM)
    char_from_room(victim)
    char_to_room(victim, room)
    act("$n slowly fades into existence.", victim, None, None, C.TO_ROOM)
    _look_auto(victim)


# C: magic.c spell_ventriloquate
def spell_ventriloquate(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.commands.interp import one_argument
    from charm.entities.handler import is_awake, is_exact_name

    game = _game()
    game.target_name, speaker = one_argument(game.target_name)
    buf1 = "%s says '%s'.\n\r" % (speaker, game.target_name)
    buf2 = "Someone makes %s say '%s'.\n\r" % (speaker, game.target_name)
    buf1 = upper(buf1[0]) + buf1[1:]  # buf1[0] = UPPER (buf1[0])
    for vch in list(ch.in_room.people):
        if not is_exact_name(speaker, vch.name) and is_awake(vch):
            send_to_char(buf2 if _saves(level, vch, C.DAM_OTHER) else buf1, vch)


# C: magic.c spell_weaken
def spell_weaken(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    if is_affected_by(victim, sn) or _saves(level, victim, C.DAM_OTHER):
        return
    affect_to_char(victim, _af(C.TO_AFFECTS, sn, level, c_div(level, 2), C.APPLY_STR, -1 * c_div(level, 5),
                               C.AFF_WEAKEN))
    send_to_char("You feel your strength slip away.\n\r", victim)
    act("$n looks tired and weak.", victim, None, None, C.TO_ROOM)


# C: magic.c spell_word_of_recall
def spell_word_of_recall(sn: int, level: int, ch, vo, target: int) -> None:
    """"RT recall spell is back"."""
    from charm.entities.handler import char_from_room, char_to_room
    from charm.systems.fight import stop_fighting

    victim = vo
    if victim.is_npc:
        return
    location = _game().index.get_room_index(C.ROOM_VNUM_TEMPLE)
    if location is None:
        send_to_char("You are completely lost.\n\r", victim)
        return
    if victim.in_room.room_flags & C.ROOM_NO_RECALL or is_affected(victim, C.AFF_CURSE):
        send_to_char("Spell failed.\n\r", victim)
        return
    if victim.fighting is not None:
        stop_fighting(_game(), victim, True)
    ch.move = sh_int(c_div(ch.move, 2))  # the caster's: the spell is for yourself only
    act("$n disappears.", victim, None, None, C.TO_ROOM)
    char_from_room(victim)
    char_to_room(victim, location)
    act("$n appears in the room.", victim, None, None, C.TO_ROOM)
    _look_auto(victim)


def _breath_damage(ch, hp_floor: int, hp_low: int, hp_high_div: int, dice_size: int, level: int,
                   fixed_high: int | None = None) -> int:
    """The breaths' damage: from the breather's hit points and dice, the larger of the two blends."""
    hpch = max(hp_floor, ch.hit)
    high = fixed_high if fixed_high is not None else c_div(hpch, hp_high_div)
    hp_dam = number_range(c_div(hpch, hp_low) + 1, high)
    dice_dam = dice(level, dice_size)
    return max(hp_dam + c_div(dice_dam, 10), dice_dam + c_div(hp_dam, 10))


# C: magic.c spell_acid_breath
def spell_acid_breath(sn: int, level: int, ch, vo, target: int) -> None:
    """"NPC spells."."""
    from charm.systems.effects import acid_effect

    victim = vo
    act("$n spits acid at $N.", ch, None, victim, C.TO_NOTVICT)
    act("$n spits a stream of corrosive acid at you.", ch, None, victim, C.TO_VICT)
    act("You spit acid at $N.", ch, None, victim, C.TO_CHAR)
    dam = _breath_damage(ch, 12, 11, 6, 16, level)
    if _saves(level, victim, C.DAM_ACID):
        acid_effect(victim, c_div(level, 2), c_div(dam, 4), C.TARGET_CHAR)
        _damage(ch, victim, c_div(dam, 2), sn, C.DAM_ACID, True)
    else:
        acid_effect(victim, level, dam, C.TARGET_CHAR)
        _damage(ch, victim, dam, sn, C.DAM_ACID, True)


def _cone(sn: int, level: int, ch, victim, dam: int, dam_type: int, effect) -> None:
    """fire breath's and frost breath's cone: the victim takes it all, the rest of the room in part."""
    from charm.entities.handler import next_in_room
    from charm.systems.fight import is_safe_spell

    people = victim.in_room.people
    vch = people[0] if people else None
    while vch is not None:
        vch_next = next_in_room(vch)
        if not (is_safe_spell(ch, vch, True)
                or (vch.is_npc and ch.is_npc and (ch.fighting is not vch or vch.fighting is not ch))):
            if vch is victim:  # "full damage"
                if _saves(level, vch, dam_type):
                    effect(vch, c_div(level, 2), c_div(dam, 4), C.TARGET_CHAR)
                    _damage(ch, vch, c_div(dam, 2), sn, dam_type, True)
                else:
                    effect(vch, level, dam, C.TARGET_CHAR)
                    _damage(ch, vch, dam, sn, dam_type, True)
            else:  # "partial damage"
                if _saves(level - 2, vch, dam_type):
                    effect(vch, c_div(level, 4), c_div(dam, 8), C.TARGET_CHAR)
                    _damage(ch, vch, c_div(dam, 4), sn, dam_type, True)
                else:
                    effect(vch, c_div(level, 2), c_div(dam, 4), C.TARGET_CHAR)
                    _damage(ch, vch, c_div(dam, 2), sn, dam_type, True)
        vch = vch_next


# C: magic.c spell_fire_breath
def spell_fire_breath(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.effects import fire_effect

    victim = vo
    act("$n breathes forth a cone of fire.", ch, None, victim, C.TO_NOTVICT)
    act("$n breathes a cone of hot fire over you!", ch, None, victim, C.TO_VICT)
    act("You breath forth a cone of fire.", ch, None, None, C.TO_CHAR)
    dam = _breath_damage(ch, 10, 9, 5, 20, level)
    fire_effect(victim.in_room, level, c_div(dam, 2), C.TARGET_ROOM)
    _cone(sn, level, ch, victim, dam, C.DAM_FIRE, fire_effect)


# C: magic.c spell_frost_breath
def spell_frost_breath(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.effects import cold_effect

    victim = vo
    act("$n breathes out a freezing cone of frost!", ch, None, victim, C.TO_NOTVICT)
    act("$n breathes a freezing cone of frost over you!", ch, None, victim, C.TO_VICT)
    act("You breath out a cone of frost.", ch, None, None, C.TO_CHAR)
    dam = _breath_damage(ch, 12, 11, 6, 16, level)
    cold_effect(victim.in_room, level, c_div(dam, 2), C.TARGET_ROOM)
    _cone(sn, level, ch, victim, dam, C.DAM_COLD, cold_effect)


# C: magic.c spell_gas_breath
def spell_gas_breath(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import next_in_room
    from charm.systems.effects import poison_effect
    from charm.systems.fight import is_safe_spell

    act("$n breathes out a cloud of poisonous gas!", ch, None, None, C.TO_ROOM)
    act("You breath out a cloud of poisonous gas.", ch, None, None, C.TO_CHAR)
    dam = _breath_damage(ch, 16, 15, 1, 12, level, fixed_high=8)
    poison_effect(ch.in_room, level, dam, C.TARGET_ROOM)
    people = ch.in_room.people
    vch = people[0] if people else None
    while vch is not None:
        vch_next = next_in_room(vch)
        # sic: a mob breathing spares the mobs it's fighting, where fire and frost spare those it isn't (#81)
        if not (is_safe_spell(ch, vch, True)
                or (ch.is_npc and vch.is_npc and (ch.fighting is vch or vch.fighting is ch))):
            if _saves(level, vch, C.DAM_POISON):
                poison_effect(vch, c_div(level, 2), c_div(dam, 4), C.TARGET_CHAR)
                _damage(ch, vch, c_div(dam, 2), sn, C.DAM_POISON, True)
            else:
                poison_effect(vch, level, dam, C.TARGET_CHAR)
                _damage(ch, vch, dam, sn, C.DAM_POISON, True)
        vch = vch_next


# C: magic.c spell_lightning_breath
def spell_lightning_breath(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.effects import shock_effect

    victim = vo
    act("$n breathes a bolt of lightning at $N.", ch, None, victim, C.TO_NOTVICT)
    act("$n breathes a bolt of lightning at you!", ch, None, victim, C.TO_VICT)
    act("You breathe a bolt of lightning at $N.", ch, None, victim, C.TO_CHAR)
    dam = _breath_damage(ch, 10, 9, 5, 20, level)
    if _saves(level, victim, C.DAM_LIGHTNING):
        shock_effect(victim, c_div(level, 2), c_div(dam, 4), C.TARGET_CHAR)
        _damage(ch, victim, c_div(dam, 2), sn, C.DAM_LIGHTNING, True)
    else:
        shock_effect(victim, level, dam, C.TARGET_CHAR)
        _damage(ch, victim, dam, sn, C.DAM_LIGHTNING, True)


# C: magic.c spell_general_purpose
def spell_general_purpose(sn: int, level: int, ch, vo, target: int) -> None:
    """"Spells for mega1.are from Glop/Erkenbrand."."""
    victim = vo
    dam = number_range(25, 100)
    if _saves(level, victim, C.DAM_PIERCE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_PIERCE, True)


# C: magic.c spell_high_explosive
def spell_high_explosive(sn: int, level: int, ch, vo, target: int) -> None:
    victim = vo
    dam = number_range(30, 120)
    if _saves(level, victim, C.DAM_PIERCE):
        dam = c_div(dam, 2)
    _damage(ch, victim, dam, sn, C.DAM_PIERCE, True)


# C: magic2.c spell_farsight
def spell_farsight(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.systems.fight import _do

    if is_affected(ch, C.AFF_BLIND):
        send_to_char("Maybe it would help if you could see?\n\r", ch)
        return
    _do("do_scan", ch, _game().target_name)


def _warp_stone(ch) -> bool:
    """portal's and nexus's component: a warp stone held, or an immortal; used up if held. False if lacking."""
    from charm.entities.handler import extract_obj, get_eq_char, is_immortal

    stone = get_eq_char(ch, C.WEAR_HOLD)
    if not is_immortal(ch) and (stone is None or stone.item_type != C.ITEM_WARP_STONE):
        send_to_char("You lack the proper component for this spell.\n\r", ch)
        return False
    if stone is not None and stone.item_type == C.ITEM_WARP_STONE:
        act("You draw upon the power of $p.", ch, stone, None, C.TO_CHAR)
        act("It flares brightly and vanishes!", ch, stone, None, C.TO_CHAR)
        extract_obj(_game(), stone)
    return True


def _portal(timer: int, to_vnum: int, room):
    from charm.entities.create import create_object
    from charm.entities.handler import obj_to_room

    game = _game()
    portal = create_object(game, game.index.get_obj_index(C.OBJ_VNUM_PORTAL), 0)
    portal.timer = timer
    portal.value[3] = to_vnum
    obj_to_room(portal, room)
    return portal


# C: magic2.c spell_portal
def spell_portal(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import get_char_world

    victim = get_char_world(_game(), ch, _game().target_name)
    if _travel_refused(ch, victim, level, False, C.DAM_NONE, False):
        send_to_char("You failed.\n\r", ch)
        return
    if not _warp_stone(ch):
        return
    portal = _portal(2 + c_div(level, 25), victim.in_room.vnum, ch.in_room)
    act("$p rises up from the ground.", ch, portal, None, C.TO_ROOM)
    act("$p rises up before you.", ch, portal, None, C.TO_CHAR)


# C: magic2.c spell_nexus
def spell_nexus(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.entities.handler import can_see_room, get_char_world

    from_room = ch.in_room
    victim = get_char_world(_game(), ch, _game().target_name)
    if (victim is not None and victim is not ch and victim.in_room is not None
            and not can_see_room(ch, from_room)):
        send_to_char("You failed.\n\r", ch)
        return
    if _travel_refused(ch, victim, level, True, C.DAM_NONE, False):
        send_to_char("You failed.\n\r", ch)
        return
    to_room = victim.in_room
    if not _warp_stone(ch):
        return
    portal = _portal(1 + c_div(level, 10), to_room.vnum, from_room)  # "portal one"
    act("$p rises up from the ground.", ch, portal, None, C.TO_ROOM)
    act("$p rises up before you.", ch, portal, None, C.TO_CHAR)
    if to_room is from_room:  # "no second portal if rooms are the same"
        return
    portal = _portal(1 + c_div(level, 10), from_room.vnum, to_room)  # "portal two"
    if to_room.people:
        act("$p rises up from the ground.", to_room.people[0], portal, None, C.TO_ROOM)
        act("$p rises up from the ground.", to_room.people[0], portal, None, C.TO_CHAR)


SPELLS = {name: fn for name, fn in globals().items() if name.startswith("spell_") and callable(fn)}
