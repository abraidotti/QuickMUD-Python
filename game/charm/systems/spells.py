"""magic.c's spells, the first half in the C's order (acid blast to fly; #74, PR 3). The rest come in PR 4.

Each spell takes the C's arguments: the skill number, the caster's level for it, the caster, the target (a
character, an object, or None) and what the target is (TARGET_CHAR, TARGET_OBJ or TARGET_NONE). magic.cast_spell
finds them here by the C function's name; one that isn't here raises NotPorted.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/magic.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, sh_int
from charm.core.rng import dice, number_fuzzy, number_percent, number_range
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


SPELLS = {name: fn for name, fn in globals().items() if name.startswith("spell_") and callable(fn)}
