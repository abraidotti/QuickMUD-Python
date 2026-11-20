"""fight.c, all of it: fights, round by round (violence_update), what a hit, a death and a kill do, and the
fighting skills (backstab, bash, berserk, dirt, trip, kick, disarm, rescue).

The C walks char_list and a room's people by the next pointer it took before each body ran. _char_list_from
copies that: see its docstring for what the C does when that next character is freed in the meantime.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/fight.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, sh_int
from charm.core.errors import CWouldCrash, NotPorted
from charm.core.rng import dice, number_bits, number_door, number_percent, number_range
from charm.data import constants as C


def _game():
    from charm.entities import game as game_module

    return game_module.current


def _gsn(name: str) -> int:
    from charm.world.lookup import GSN

    return GSN[name]


def _do(name: str, ch, argument: str) -> None:
    """do_function(ch, &do_NAME, argument): a command that isn't ported yet raises NotPorted."""
    from charm.commands.interp import command_function

    fn = command_function(name)
    if fn is None:
        raise NotPorted(f"fight.c: {name}")
    fn(ch, argument)


def _char_list_from(chars: list, i: int):
    """The characters from chars[i] on, by ch->next, read before each one's turn as the C reads it.

    A character that leaves char_list before its turn is skipped, as unlinking it does in the C. One freed during
    the turn before (extract_char: a mob killed, a player's pet) isn't: the C's next pointer still points at it, and
    a freed character's next is recycle.c's free list. Every character on that list has no fight and no room
    (extract_char stops its fights and takes it from its room; one freed without being extracted never fought), so
    each loop that walks this way does nothing more with them, and it ends: the characters after the freed one get
    nothing this time round (sic, #75).
    """
    snap = list(chars)
    while i < len(snap):
        j = i + 1
        while j < len(snap) and not snap[j].valid:
            j += 1
        yield snap[i]
        if j < len(snap) and not snap[j].valid:
            return
        i = j


def _attack(n: int):
    from charm.data.attacks import ATTACK_TABLE

    if not 0 <= n < len(ATTACK_TABLE):
        raise CWouldCrash(f"fight.c: attack {n} is past attack_table")
    return ATTACK_TABLE[n]


def _name_into(fmt: str, name: str) -> str:
    """sprintf(buf, fmt, name) for an object's template, such as "the corpse of %s"."""
    out, i = [], 0
    used = False
    while i < len(fmt):
        c = fmt[i]
        if c == "%" and i + 1 < len(fmt):
            nxt = fmt[i + 1]
            if nxt == "%":
                out.append("%")
            elif nxt == "s" and not used:
                out.append(name)
                used = True
            else:
                raise NotPorted(f"fight.c: an object template with %{nxt} in it ({fmt!r})")
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _is_neutral(ch) -> bool:
    from charm.entities.handler import is_evil, is_good

    return not is_good(ch) and not is_evil(ch)


# C: fight.c violence_update
def violence_update(game) -> None:
    from charm.entities.handler import is_awake
    from charm.systems.mobprog import has_trigger, mp_hprct_trigger, mp_percent_trigger

    for ch in _char_list_from(game.char_list, 0):
        victim = ch.fighting
        if victim is None or ch.in_room is None:
            continue
        if is_awake(ch) and ch.in_room is victim.in_room:
            multi_hit(ch, victim, C.TYPE_UNDEFINED)
        else:
            stop_fighting(game, ch, False)
        victim = ch.fighting
        if victim is None:
            continue
        check_assist(ch, victim)  # "Fun for the whole family!"
        if ch.is_npc:
            if has_trigger(ch, C.TRIG_FIGHT):
                mp_percent_trigger(ch, victim, None, None, C.TRIG_FIGHT)
            if has_trigger(ch, C.TRIG_HPCNT):
                mp_hprct_trigger(ch, victim)


# C: fight.c check_assist
def check_assist(ch, victim) -> None:
    from charm.commands.comm import do_emote, is_same_group
    from charm.entities.handler import can_see, is_affected, is_awake, is_evil, is_good, next_in_room

    people = ch.in_room.people
    rch = people[0] if people else None
    while rch is not None:
        rch_next = next_in_room(rch)
        if is_awake(rch) and rch.fighting is None:
            # "quick check for ASSIST_PLAYER"
            if not ch.is_npc and rch.is_npc and rch.off_flags & C.ASSIST_PLAYERS and rch.level + 6 > victim.level:
                do_emote(rch, "screams and attacks!")
                multi_hit(rch, victim, C.TYPE_UNDEFINED)
                rch = rch_next
                continue
            # "PCs next"
            if not ch.is_npc or is_affected(ch, C.AFF_CHARM):
                if (((not rch.is_npc and rch.act & C.PLR_AUTOASSIST) or is_affected(rch, C.AFF_CHARM))
                        and is_same_group(ch, rch) and not is_safe(rch, victim)):
                    multi_hit(rch, victim, C.TYPE_UNDEFINED)
                rch = rch_next
                continue
            # "now check the NPC cases"
            if ch.is_npc and not is_affected(ch, C.AFF_CHARM):
                if ((rch.is_npc and rch.off_flags & C.ASSIST_ALL)
                        or (rch.is_npc and rch.group and rch.group == ch.group)
                        or (rch.is_npc and rch.race == ch.race and rch.off_flags & C.ASSIST_RACE)
                        or (rch.is_npc and rch.off_flags & C.ASSIST_ALIGN
                            and ((is_good(rch) and is_good(ch)) or (is_evil(rch) and is_evil(ch))
                                 or (_is_neutral(rch) and _is_neutral(ch))))
                        or (rch.index is ch.index and rch.off_flags & C.ASSIST_VNUM)):
                    if number_bits(1) == 0:
                        rch = rch_next
                        continue
                    target = None
                    number = 0
                    # sic: vch->next is char_list's next, not the room's, so this goes on from the room's first
                    # character through every character after it in char_list, in any room (#75)
                    chars = _game().char_list
                    start = next((k for k, p in enumerate(chars) if p is ch.in_room.people[0]), len(chars))
                    for vch in chars[start:]:
                        if can_see(rch, vch) and is_same_group(vch, victim) and number_range(0, number) == 0:
                            target = vch
                            number += 1
                    if target is not None:
                        do_emote(rch, "screams and attacks!")
                        multi_hit(rch, target, C.TYPE_UNDEFINED)
        rch = rch_next


# C: fight.c multi_hit
def multi_hit(ch, victim, dt: int) -> None:
    """Do one group of attacks."""
    from charm.entities.handler import get_skill, is_affected
    from charm.systems.skills import check_improve

    # "decrement the wait"
    if ch.desc is None:
        ch.wait = sh_int(max(0, ch.wait - C.PULSE_VIOLENCE))
    if ch.desc is None:
        ch.daze = sh_int(max(0, ch.daze - C.PULSE_VIOLENCE))
    # "no attacks for stunnies -- just a check"
    if ch.position < C.POS_RESTING:
        return
    if ch.is_npc:
        mob_hit(ch, victim, dt)
        return
    one_hit(ch, victim, dt)
    if ch.fighting is not victim:
        return
    if is_affected(ch, C.AFF_HASTE):
        one_hit(ch, victim, dt)
    if ch.fighting is not victim or dt == _gsn("gsn_backstab"):
        return
    chance = c_div(get_skill(ch, _gsn("gsn_second_attack")), 2)
    if is_affected(ch, C.AFF_SLOW):
        chance = c_div(chance, 2)
    if number_percent() < chance:
        one_hit(ch, victim, dt)
        check_improve(ch, _gsn("gsn_second_attack"), True, 5)
        if ch.fighting is not victim:
            return
    chance = c_div(get_skill(ch, _gsn("gsn_third_attack")), 4)
    if is_affected(ch, C.AFF_SLOW):
        chance = 0
    if number_percent() < chance:
        one_hit(ch, victim, dt)
        check_improve(ch, _gsn("gsn_third_attack"), True, 6)
        if ch.fighting is not victim:
            return


# C: fight.c mob_hit
def mob_hit(ch, victim, dt: int) -> None:
    """A mob's attacks."""
    from charm.entities.handler import get_skill, get_weapon_sn, is_affected

    one_hit(ch, victim, dt)
    if ch.fighting is not victim:
        return
    # "Area attack -- BALLS nasty!"
    if ch.off_flags & C.OFF_AREA_ATTACK:
        # sic: vch->next is char_list's next, as in check_assist (#75); one_hit skips those in other rooms
        chars = _game().char_list
        head = ch.in_room.people[0]
        start = next((k for k, p in enumerate(chars) if p is head), len(chars))
        for vch in _char_list_from(chars, start):
            if vch is not victim and vch.fighting is ch:
                one_hit(ch, vch, dt)
    if is_affected(ch, C.AFF_HASTE) or (ch.off_flags & C.OFF_FAST and not is_affected(ch, C.AFF_SLOW)):
        one_hit(ch, victim, dt)
    if ch.fighting is not victim or dt == _gsn("gsn_backstab"):
        return
    chance = c_div(get_skill(ch, _gsn("gsn_second_attack")), 2)
    if is_affected(ch, C.AFF_SLOW) and not ch.off_flags & C.OFF_FAST:
        chance = c_div(chance, 2)
    if number_percent() < chance:
        one_hit(ch, victim, dt)
        if ch.fighting is not victim:
            return
    chance = c_div(get_skill(ch, _gsn("gsn_third_attack")), 4)
    if is_affected(ch, C.AFF_SLOW) and not ch.off_flags & C.OFF_FAST:
        chance = 0
    if number_percent() < chance:
        one_hit(ch, victim, dt)
        if ch.fighting is not victim:
            return
    # "oh boy!  Fun stuff!"
    if ch.wait > 0:
        return
    number_range(0, 2)  # the C's mob_cast_mage and mob_cast_cleric are commented out: only the draw is left
    # "now for the skills"
    number = number_range(0, 8)
    off = ch.off_flags
    if number == 0:
        if off & C.OFF_BASH:
            _do("do_bash", ch, "")
    elif number == 1:
        if off & C.OFF_BERSERK and not is_affected(ch, C.AFF_BERSERK):
            _do("do_berserk", ch, "")
    elif number == 2:
        if off & C.OFF_DISARM or (get_weapon_sn(ch) != _gsn("gsn_hand_to_hand")
                                  and ch.act & (C.ACT_WARRIOR | C.ACT_THIEF)):
            _do("do_disarm", ch, "")
    elif number == 3:
        if off & C.OFF_KICK:
            _do("do_kick", ch, "")
    elif number == 4:
        if off & C.OFF_KICK_DIRT:
            _do("do_dirt", ch, "")
    elif number == 6:
        if off & C.OFF_TRIP:
            _do("do_trip", ch, "")
    elif number == 8:
        if off & C.OFF_BACKSTAB:
            _do("do_backstab", ch, "")
    # 5 (OFF_TAIL) and 7 (OFF_CRUSH): the C's do_tail and do_crush calls are commented out


# C: fight.c one_hit
def one_hit(ch, victim, dt: int) -> None:
    """Hit one guy once."""
    from charm.data.classes import CLASS_TABLE
    from charm.entities.handler import (affect_find, affect_join, can_see, get_ac, get_damroll, get_eq_char,
                                        get_hitroll, get_skill, get_weapon_skill, get_weapon_sn, interpolate,
                                        is_awake)
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.effects import cold_effect, fire_effect, shock_effect
    from charm.systems.magic import saves_spell
    from charm.systems.skills import check_improve
    from charm.world.index import Affect

    # "just in case"
    if victim is ch or ch is None or victim is None:
        return
    # "Can't beat a dead char! Guard against weird room-leavings."
    if victim.position == C.POS_DEAD or ch.in_room is not victim.in_room:
        return
    # "Figure out the type of damage message."
    wield = get_eq_char(ch, C.WEAR_WIELD)
    if dt == C.TYPE_UNDEFINED:
        dt = C.TYPE_HIT
        if wield is not None and wield.item_type == C.ITEM_WEAPON:
            dt += wield.value[3]
        else:
            dt += ch.dam_type
    if dt < C.TYPE_HIT:
        dam_type = _attack(wield.value[3] if wield is not None else ch.dam_type).damage
    else:
        dam_type = _attack(dt - C.TYPE_HIT).damage
    if dam_type == -1:
        dam_type = C.DAM_BASH

    # "get the weapon skill"
    sn = get_weapon_sn(ch)
    skill = 20 + get_weapon_skill(ch, sn)

    # "Calculate to-hit-armor-class-0 versus armor."
    if ch.is_npc:
        thac0_00 = 20
        thac0_32 = -4  # "as good as a thief"
        if ch.act & C.ACT_WARRIOR:
            thac0_32 = -10
        elif ch.act & C.ACT_THIEF:
            thac0_32 = -4
        elif ch.act & C.ACT_CLERIC:
            thac0_32 = 2
        elif ch.act & C.ACT_MAGE:
            thac0_32 = 6
    else:
        thac0_00 = CLASS_TABLE[ch.class_].thac0_00
        thac0_32 = CLASS_TABLE[ch.class_].thac0_32
    thac0 = interpolate(ch.level, thac0_00, thac0_32)
    if thac0 < 0:
        thac0 = c_div(thac0, 2)
    if thac0 < -5:
        thac0 = -5 + c_div(thac0 + 5, 2)
    thac0 -= c_div(get_hitroll(ch) * skill, 100)
    thac0 += c_div(5 * (100 - skill), 100)
    if dt == _gsn("gsn_backstab"):
        thac0 -= 10 * (100 - get_skill(ch, _gsn("gsn_backstab")))

    if dam_type == C.DAM_PIERCE:
        victim_ac = c_div(get_ac(victim, C.AC_PIERCE), 10)
    elif dam_type == C.DAM_BASH:
        victim_ac = c_div(get_ac(victim, C.AC_BASH), 10)
    elif dam_type == C.DAM_SLASH:
        victim_ac = c_div(get_ac(victim, C.AC_SLASH), 10)
    else:
        victim_ac = c_div(get_ac(victim, C.AC_EXOTIC), 10)
    if victim_ac < -15:
        victim_ac = c_div(victim_ac + 15, 5) - 15
    if not can_see(ch, victim):
        victim_ac -= 4
    if victim.position < C.POS_FIGHTING:
        victim_ac += 4
    if victim.position < C.POS_RESTING:
        victim_ac += 6

    # "The moment of excitement!"
    while True:
        diceroll = number_bits(5)
        if diceroll < 20:
            break
    if diceroll == 0 or (diceroll != 19 and diceroll < thac0 - victim_ac):
        damage(ch, victim, 0, dt, dam_type, True)  # "Miss."
        return

    # "Hit. Calc damage."
    if ch.is_npc and (not ch.index.new_format or wield is None):
        if not ch.index.new_format:
            dam = number_range(c_div(ch.level, 2), c_div(ch.level * 3, 2))
            if wield is not None:
                dam += c_div(dam, 2)
        else:
            dam = dice(ch.damage[C.DICE_NUMBER], ch.damage[C.DICE_TYPE])
    else:
        if sn != -1:
            check_improve(ch, sn, True, 5)
        if wield is not None:
            if wield.index.new_format:
                dam = c_div(dice(wield.value[1], wield.value[2]) * skill, 100)
            else:
                dam = number_range(c_div(wield.value[1] * skill, 100), c_div(wield.value[2] * skill, 100))
            if get_eq_char(ch, C.WEAR_SHIELD) is None:  # "no shield = more"
                dam = c_div(dam * 11, 10)
            if wield.value[4] & C.WEAPON_SHARP:  # "sharpness!"
                percent = number_percent()
                if percent <= c_div(skill, 8):
                    dam = 2 * dam + c_div(dam * 2 * percent, 100)
        else:
            dam = number_range(1 + c_div(4 * skill, 100), c_div(c_div(2 * ch.level, 3) * skill, 100))

    # "Bonuses."
    if get_skill(ch, _gsn("gsn_enhanced_damage")) > 0:
        diceroll = number_percent()
        if diceroll <= get_skill(ch, _gsn("gsn_enhanced_damage")):
            check_improve(ch, _gsn("gsn_enhanced_damage"), True, 6)
            dam += 2 * c_div(dam * diceroll, 300)
    if not is_awake(victim):
        dam *= 2
    elif victim.position < C.POS_FIGHTING:
        dam = c_div(dam * 3, 2)
    if dt == _gsn("gsn_backstab") and wield is not None:
        if wield.value[0] != 2:
            dam *= 2 + c_div(ch.level, 10)
        else:
            dam *= 2 + c_div(ch.level, 8)
    dam += c_div(get_damroll(ch) * min(100, skill), 100)
    if dam <= 0:
        dam = 1

    result = damage(ch, victim, dam, dt, dam_type, True)

    # "but do we have a funky weapon?"
    if result and wield is not None:
        if ch.fighting is victim and wield.value[4] & C.WEAPON_POISON:
            poison = affect_find(wield.affected, _gsn("gsn_poison"))
            level = wield.level if poison is None else poison.level
            if not saves_spell(c_div(level, 2), victim, C.DAM_POISON):
                send_to_char("You feel poison coursing through your veins.", victim)  # sic: no line end (#75)
                act("$n is poisoned by the venom on $p.", victim, wield, None, C.TO_ROOM)
                affect_join(victim, Affect(where=C.TO_AFFECTS, type=_gsn("gsn_poison"), level=c_div(level * 3, 4),
                                           duration=c_div(level, 2), location=C.APPLY_STR, modifier=-1,
                                           bitvector=C.AFF_POISON))
            # "weaken the poison if it's temporary"
            if poison is not None:
                poison.level = max(0, poison.level - 2)
                poison.duration = max(0, poison.duration - 1)
                if poison.level == 0 or poison.duration == 0:
                    act("The poison on $p has worn off.", ch, wield, None, C.TO_CHAR)
        if ch.fighting is victim and wield.value[4] & C.WEAPON_VAMPIRIC:
            dam = number_range(1, c_div(wield.level, 5) + 1)
            act("$p draws life from $n.", victim, wield, None, C.TO_ROOM)
            act("You feel $p drawing your life away.", victim, wield, None, C.TO_CHAR)
            damage(ch, victim, dam, 0, C.DAM_NEGATIVE, False)
            ch.alignment = sh_int(max(-1000, ch.alignment - 1))
            ch.hit = sh_int(ch.hit + c_div(dam, 2))
        if ch.fighting is victim and wield.value[4] & C.WEAPON_FLAMING:
            dam = number_range(1, c_div(wield.level, 4) + 1)
            act("$n is burned by $p.", victim, wield, None, C.TO_ROOM)
            act("$p sears your flesh.", victim, wield, None, C.TO_CHAR)
            fire_effect(victim, c_div(wield.level, 2), dam, C.TARGET_CHAR)
            damage(ch, victim, dam, 0, C.DAM_FIRE, False)
        if ch.fighting is victim and wield.value[4] & C.WEAPON_FROST:
            dam = number_range(1, c_div(wield.level, 6) + 2)
            act("$p freezes $n.", victim, wield, None, C.TO_ROOM)
            act("The cold touch of $p surrounds you with ice.", victim, wield, None, C.TO_CHAR)
            cold_effect(victim, c_div(wield.level, 2), dam, C.TARGET_CHAR)
            damage(ch, victim, dam, 0, C.DAM_COLD, False)
        if ch.fighting is victim and wield.value[4] & C.WEAPON_SHOCKING:
            dam = number_range(1, c_div(wield.level, 5) + 2)
            act("$n is struck by lightning from $p.", victim, wield, None, C.TO_ROOM)
            act("You are shocked by $p.", victim, wield, None, C.TO_CHAR)
            shock_effect(victim, c_div(wield.level, 2), dam, C.TARGET_CHAR)
            damage(ch, victim, dam, 0, C.DAM_LIGHTNING, False)


# C: fight.c damage
def damage(ch, victim, dam: int, dt: int, dam_type: int, show: bool) -> bool:
    """Inflict damage from a hit."""
    from charm.commands.comm import stop_follower
    from charm.core.log import bug, log_string
    from charm.entities.handler import (affect_strip, can_see_obj, check_immune, extract_obj, get_eq_char,
                                        get_obj_list, is_affected, is_awake, is_evil, is_good, is_immortal,
                                        is_same_clan)
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.net.wiznet import wiznet
    from charm.systems.mobprog import has_trigger, mp_percent_trigger
    from charm.systems.skills import exp_per_level
    from charm.systems.update import gain_exp

    game = _game()
    if victim.position == C.POS_DEAD:
        return False

    # "Stop up any residual loopholes."
    if dam > 1200 and dt >= C.TYPE_HIT:
        bug("Damage: %d: more than 1200 points!", dam)
        dam = 1200
        if not is_immortal(ch):
            obj = get_eq_char(ch, C.WEAR_WIELD)
            send_to_char("You really shouldn't cheat.\n\r", ch)
            if obj is not None:
                extract_obj(game, obj)

    # "damage reduction"
    if dam > 35:
        dam = c_div(dam - 35, 2) + 35
    if dam > 80:
        dam = c_div(dam - 80, 2) + 80

    if victim is not ch:
        # "Certain attacks are forbidden. Most other attacks are returned."
        if is_safe(ch, victim):
            return False
        check_killer(ch, victim)
        if victim.position > C.POS_STUNNED:
            if victim.fighting is None:
                set_fighting(victim, ch)
                if victim.is_npc and has_trigger(victim, C.TRIG_KILL):
                    mp_percent_trigger(victim, ch, None, None, C.TRIG_KILL)
            if victim.timer <= 4:
                victim.position = C.POS_FIGHTING
        if victim.position > C.POS_STUNNED:
            if ch.fighting is None:
                set_fighting(ch, victim)
        # "More charm stuff."
        if victim.master is ch:
            stop_follower(game, victim)

    # "Inviso attacks ... not."
    if is_affected(ch, C.AFF_INVISIBLE):
        affect_strip(ch, _gsn("gsn_invis"))
        affect_strip(ch, _gsn("gsn_mass_invis"))
        ch.affected_by &= ~C.AFF_INVISIBLE
        act("$n fades into existence.", ch, None, None, C.TO_ROOM)

    # "Damage modifiers."
    if dam > 1 and not victim.is_npc and victim.pcdata.condition[C.COND_DRUNK] > 10:
        dam = c_div(9 * dam, 10)
    if dam > 1 and is_affected(victim, C.AFF_SANCTUARY):
        dam = c_div(dam, 2)
    if dam > 1 and ((is_affected(victim, C.AFF_PROTECT_EVIL) and is_evil(ch))
                    or (is_affected(victim, C.AFF_PROTECT_GOOD) and is_good(ch))):
        dam -= c_div(dam, 4)
    immune = False

    # "Check for parry, and dodge."
    if dt >= C.TYPE_HIT and ch is not victim:
        if check_parry(ch, victim):
            return False
        if check_dodge(ch, victim):
            return False
        if check_shield_block(ch, victim):
            return False

    kind = check_immune(victim, dam_type)
    if kind == C.IS_IMMUNE:
        immune = True
        dam = 0
    elif kind == C.IS_RESISTANT:
        dam -= c_div(dam, 3)
    elif kind == C.IS_VULNERABLE:
        dam += c_div(dam, 2)

    if show:
        dam_message(ch, victim, dam, dt, immune)
    if dam == 0:
        return False

    # "Hurt the victim. Inform the victim of his new state."
    victim.hit = sh_int(victim.hit - dam)
    if not victim.is_npc and victim.level >= C.LEVEL_IMMORTAL and victim.hit < 1:
        victim.hit = 1
    update_pos(victim)

    pos = victim.position
    if pos == C.POS_MORTAL:
        act("$n is mortally wounded, and will die soon, if not aided.", victim, None, None, C.TO_ROOM)
        send_to_char("You are mortally wounded, and will die soon, if not aided.\n\r", victim)
    elif pos == C.POS_INCAP:
        act("$n is incapacitated and will slowly die, if not aided.", victim, None, None, C.TO_ROOM)
        send_to_char("You are incapacitated and will slowly die, if not aided.\n\r", victim)
    elif pos == C.POS_STUNNED:
        act("$n is stunned, but will probably recover.", victim, None, None, C.TO_ROOM)
        send_to_char("You are stunned, but will probably recover.\n\r", victim)
    elif pos == C.POS_DEAD:
        act("{R$n is DEAD!!{x", victim, None, None, C.TO_ROOM)
        send_to_char("{RYou have been KILLED!!{x\n\r\n\r", victim)
    else:
        if dam > c_div(victim.max_hit, 4):
            send_to_char("{RThat really did HURT!{x\n\r", victim)
        if victim.hit < c_div(victim.max_hit, 4):
            send_to_char("{RYou sure are BLEEDING!{x\n\r", victim)

    # "Sleep spells and extremely wounded folks."
    if not is_awake(victim):
        stop_fighting(game, victim, False)

    # "Payoff for killing things."
    if victim.position == C.POS_DEAD:
        group_gain(ch, victim)
        if not victim.is_npc:
            log_string("%s killed by %s at %d" % (victim.name, ch.short_descr if ch.is_npc else ch.name,
                                                  ch.in_room.vnum))
            # "Dying penalty: 2/3 way back to previous level."
            per = exp_per_level(victim, victim.pcdata.points)
            if victim.exp > per * victim.level:
                gain_exp(victim, c_div(2 * (per * victim.level - victim.exp), 3) + 50)
        buf = "%s got toasted by %s at %s [room %d]" % (victim.short_descr if victim.is_npc else victim.name,
                                                       ch.short_descr if ch.is_npc else ch.name,
                                                       ch.in_room.name, ch.in_room.vnum)
        wiznet(game, buf, None, None, C.WIZ_MOBDEATHS if victim.is_npc else C.WIZ_DEATHS, 0, 0)
        # "Death trigger"
        if victim.is_npc and has_trigger(victim, C.TRIG_DEATH):
            victim.position = C.POS_STANDING
            mp_percent_trigger(victim, ch, None, None, C.TRIG_DEATH)
        raw_kill(victim)
        # "dump the flags"
        if ch is not victim and not ch.is_npc and not is_same_clan(ch, victim):
            if victim.act & C.PLR_KILLER:
                victim.act &= ~C.PLR_KILLER
            else:
                victim.act &= ~C.PLR_THIEF
        # "RT new auto commands"
        if not ch.is_npc:
            corpse = get_obj_list(ch, "corpse", ch.in_room.contents)
            if corpse is not None and corpse.item_type == C.ITEM_CORPSE_NPC and can_see_obj(ch, corpse):
                from charm.commands.obj import do_get, do_sacrifice

                corpse = get_obj_list(ch, "corpse", ch.in_room.contents)
                if ch.act & C.PLR_AUTOLOOT and corpse is not None and corpse.contains:  # "exists and not empty"
                    do_get(ch, "all corpse")
                if (ch.act & C.PLR_AUTOGOLD and corpse is not None and corpse.contains
                        and not ch.act & C.PLR_AUTOLOOT):
                    if get_obj_list(ch, "gcash", corpse.contains) is not None:
                        do_get(ch, "all.gcash corpse")
                if ch.act & C.PLR_AUTOSAC:
                    if ch.act & C.PLR_AUTOLOOT and corpse is not None and corpse.contains:
                        return True  # "leave if corpse has treasure"
                    do_sacrifice(ch, "corpse")
        return True

    if victim is ch:
        return True

    # "Take care of link dead people."
    if not victim.is_npc and victim.desc is None:
        if number_range(0, victim.wait) == 0:
            from charm.commands.move import do_recall

            do_recall(victim, "")
            return True

    # "Wimp out?"
    if victim.is_npc and dam > 0 and victim.wait < c_div(C.PULSE_VIOLENCE, 2):
        if ((victim.act & C.ACT_WIMPY and number_bits(2) == 0 and victim.hit < c_div(victim.max_hit, 5))
                or (is_affected(victim, C.AFF_CHARM) and victim.master is not None
                    and victim.master.in_room is not victim.in_room)):
            do_flee(victim, "")
    if (not victim.is_npc and victim.hit > 0 and victim.hit <= victim.wimpy
            and victim.wait < c_div(C.PULSE_VIOLENCE, 2)):
        do_flee(victim, "")
    return True


# C: fight.c is_safe_spell
def is_safe_spell(ch, victim, area: bool) -> bool:
    from charm.commands.comm import is_same_group
    from charm.entities.handler import is_affected, is_clan, is_immortal

    if victim.in_room is None or ch.in_room is None:
        return True
    if victim is ch and area:
        return True
    if victim.fighting is ch or victim is ch:
        return False
    if is_immortal(ch) and ch.level > C.LEVEL_IMMORTAL and not area:
        return False
    if victim.is_npc:
        # "killing mobiles"
        if victim.in_room.room_flags & C.ROOM_SAFE:
            return True
        if victim.index.shop is not None:
            return True
        # "no killing healers, trainers, etc"
        if victim.act & (C.ACT_TRAIN | C.ACT_PRACTICE | C.ACT_IS_HEALER | C.ACT_IS_CHANGER):
            return True
        if not ch.is_npc:
            if victim.act & C.ACT_PET:  # "no pets"
                return True
            # "no charmed creatures unless owner"
            if is_affected(victim, C.AFF_CHARM) and (area or ch is not victim.master):
                return True
            # "legal kill? -- cannot hit mob fighting non-group member"
            if victim.fighting is not None and not is_same_group(ch, victim.fighting):
                return True
        else:
            # "area effect spells do not hit other mobs"
            if area and not is_same_group(victim, ch.fighting):
                return True
    else:
        # "killing players"
        if area and is_immortal(victim) and victim.level > C.LEVEL_IMMORTAL:
            return True
        if ch.is_npc:
            # "NPC doing the killing": "charmed mobs and pets cannot attack players while owned"
            if is_affected(ch, C.AFF_CHARM) and ch.master is not None and ch.master.fighting is not victim:
                return True
            if victim.in_room.room_flags & C.ROOM_SAFE:
                return True
            # "legal kill? -- mobs only hit players grouped with opponent"
            if ch.fighting is not None and not is_same_group(ch.fighting, victim):
                return True
        else:
            # "player doing the killing"
            if not is_clan(ch):
                return True
            if victim.act & (C.PLR_KILLER | C.PLR_THIEF):
                return False
            if not is_clan(victim):
                return True
            if ch.level > victim.level + 8:
                return True
    return False


# C: fight.c check_killer
def check_killer(ch, victim) -> None:
    """See if an attack justifies a KILLER flag."""
    from charm.commands.comm import stop_follower
    from charm.core.log import bug
    from charm.entities.handler import affect_strip, is_affected, is_clan
    from charm.net.output import send_to_char
    from charm.net.wiznet import wiznet
    from charm.persist.player import save_char_obj

    game = _game()
    # "Follow charm thread to responsible character. Attacking someone's charmed char is hostile!"
    while is_affected(victim, C.AFF_CHARM) and victim.master is not None:
        victim = victim.master
    # "NPC's are fair game. So are killers and thieves."
    if victim.is_npc or victim.act & (C.PLR_KILLER | C.PLR_THIEF):
        return
    # "Charm-o-rama."
    if ch.affected_by & C.AFF_CHARM:
        if ch.master is None:
            bug("Check_killer: %s bad AFF_CHARM" % (ch.short_descr if ch.is_npc else ch.name), 0)
            affect_strip(ch, _gsn("gsn_charm_person"))
            ch.affected_by &= ~C.AFF_CHARM
            return
        stop_follower(game, ch)
        return
    # "NPC's are cool of course (as long as not charmed). Hitting yourself is cool too (bleeding). So is being
    # immortal (Alander's idea). And current killers stay as they are."
    if (ch.is_npc or ch is victim or ch.level >= C.LEVEL_IMMORTAL or not is_clan(ch) or ch.act & C.PLR_KILLER
            or ch.fighting is victim):
        return
    send_to_char("*** You are now a KILLER!! ***\n\r", ch)
    ch.act |= C.PLR_KILLER
    wiznet(game, "$N is attempting to murder %s" % victim.name, ch, None, C.WIZ_FLAGS, 0, 0)
    save_char_obj(game, ch)


# C: fight.c check_parry
def check_parry(ch, victim) -> bool:
    from charm.entities.handler import can_see, get_eq_char, get_skill, is_awake
    from charm.net.act import act
    from charm.systems.skills import check_improve

    if not is_awake(victim):
        return False
    chance = c_div(get_skill(victim, _gsn("gsn_parry")), 2)
    if get_eq_char(victim, C.WEAR_WIELD) is None:
        if victim.is_npc:
            chance = c_div(chance, 2)
        else:
            return False
    if not can_see(ch, victim):
        chance = c_div(chance, 2)
    if number_percent() >= chance + victim.level - ch.level:
        return False
    act("You parry $n's attack.", ch, None, victim, C.TO_VICT)
    act("$N parries your attack.", ch, None, victim, C.TO_CHAR)
    check_improve(victim, _gsn("gsn_parry"), True, 6)
    return True


# C: fight.c check_shield_block
def check_shield_block(ch, victim) -> bool:
    from charm.entities.handler import get_eq_char, get_skill, is_awake
    from charm.net.act import act
    from charm.systems.skills import check_improve

    if not is_awake(victim):
        return False
    chance = c_div(get_skill(victim, _gsn("gsn_shield_block")), 5) + 3
    if get_eq_char(victim, C.WEAR_SHIELD) is None:
        return False
    if number_percent() >= chance + victim.level - ch.level:
        return False
    act("You block $n's attack with your shield.", ch, None, victim, C.TO_VICT)
    act("$N blocks your attack with a shield.", ch, None, victim, C.TO_CHAR)
    check_improve(victim, _gsn("gsn_shield_block"), True, 6)
    return True


# C: fight.c check_dodge
def check_dodge(ch, victim) -> bool:
    from charm.entities.handler import can_see, get_skill, is_awake
    from charm.net.act import act
    from charm.systems.skills import check_improve

    if not is_awake(victim):
        return False
    chance = c_div(get_skill(victim, _gsn("gsn_dodge")), 2)
    if not can_see(victim, ch):
        chance = c_div(chance, 2)
    if number_percent() >= chance + victim.level - ch.level:
        return False
    act("You dodge $n's attack.", ch, None, victim, C.TO_VICT)
    act("$N dodges your attack.", ch, None, victim, C.TO_CHAR)
    check_improve(victim, _gsn("gsn_dodge"), True, 6)
    return True


# C: fight.c set_fighting
def set_fighting(ch, victim) -> None:
    """Start fights."""
    from charm.core.log import bug
    from charm.entities.handler import affect_strip, is_affected

    if ch.fighting is not None:
        bug("Set_fighting: already fighting", 0)
        return
    if is_affected(ch, C.AFF_SLEEP):
        affect_strip(ch, _gsn("gsn_sleep"))
    ch.fighting = victim
    ch.position = C.POS_FIGHTING


# C: fight.c make_corpse
def make_corpse(ch) -> None:
    """Make a corpse out of a character."""
    from charm.entities.create import create_object
    from charm.entities.handler import (create_money, extract_obj, is_clan, obj_from_char, obj_from_obj,
                                        obj_to_obj, obj_to_room)
    from charm.net.act import act

    game = _game()
    ix = game.index
    if ch.is_npc:
        name = ch.short_descr
        corpse = create_object(game, ix.get_obj_index(C.OBJ_VNUM_CORPSE_NPC), 0)
        corpse.timer = number_range(3, 6)
        if ch.gold > 0:
            obj_to_obj(create_money(game, ch.gold, ch.silver), corpse)
            ch.gold = 0
            ch.silver = 0
        corpse.cost = 0
    else:
        name = ch.name
        corpse = create_object(game, ix.get_obj_index(C.OBJ_VNUM_CORPSE_PC), 0)
        corpse.timer = number_range(25, 40)
        ch.act &= ~C.PLR_CANLOOT
        if not is_clan(ch):
            corpse.owner = ch.name
        else:
            corpse.owner = None
            if ch.gold > 1 or ch.silver > 1:
                obj_to_obj(create_money(game, c_div(ch.gold, 2), c_div(ch.silver, 2)), corpse)
                ch.gold -= c_div(ch.gold, 2)
                ch.silver -= c_div(ch.silver, 2)
        corpse.cost = 0
    corpse.level = ch.level
    corpse.short_descr = _name_into(corpse.short_descr, name)
    corpse.description = _name_into(corpse.description, name)

    for obj in list(ch.carrying):
        floating = obj.wear_loc == C.WEAR_FLOAT
        obj_from_char(obj)
        if obj.item_type == C.ITEM_POTION:
            obj.timer = number_range(500, 1000)
        if obj.item_type == C.ITEM_SCROLL:
            obj.timer = number_range(1000, 2500)
        if obj.extra_flags & C.ITEM_ROT_DEATH and not floating:
            obj.timer = number_range(5, 10)
            obj.extra_flags &= ~C.ITEM_ROT_DEATH
        obj.extra_flags &= ~C.ITEM_VIS_DEATH
        if obj.extra_flags & C.ITEM_INVENTORY:
            extract_obj(game, obj)
        elif floating:
            if obj.extra_flags & C.ITEM_ROT_DEATH:  # "get rid of it!"
                if obj.contains:
                    act("$p evaporates,scattering its contents.", ch, obj, None, C.TO_ROOM)  # sic (#75)
                    for inner in list(obj.contains):
                        obj_from_obj(inner)
                        obj_to_room(inner, ch.in_room)
                else:
                    act("$p evaporates.", ch, obj, None, C.TO_ROOM)
                extract_obj(game, obj)
            else:
                act("$p falls to the floor.", ch, obj, None, C.TO_ROOM)
                obj_to_room(obj, ch.in_room)
        else:
            obj_to_obj(obj, corpse)
    obj_to_room(corpse, ch.in_room)


_DEATH_PARTS = {  # number_bits(4) from 2: the part, the message, and the object it leaves
    2: (C.PART_GUTS, "$n spills $s guts all over the floor.", C.OBJ_VNUM_GUTS),
    3: (C.PART_HEAD, "$n's severed head plops on the ground.", C.OBJ_VNUM_SEVERED_HEAD),
    4: (C.PART_HEART, "$n's heart is torn from $s chest.", C.OBJ_VNUM_TORN_HEART),
    5: (C.PART_ARMS, "$n's arm is sliced from $s dead body.", C.OBJ_VNUM_SLICED_ARM),
    6: (C.PART_LEGS, "$n's leg is sliced from $s dead body.", C.OBJ_VNUM_SLICED_LEG),
    7: (C.PART_BRAINS, "$n's head is shattered, and $s brains splash all over you.", C.OBJ_VNUM_BRAINS),
}


# C: fight.c death_cry
def death_cry(ch) -> None:
    """"Improved Death_cry contributed by Diavolo."."""
    from charm.entities.create import create_object
    from charm.entities.handler import obj_to_room
    from charm.net.act import act

    game = _game()
    vnum = 0
    msg = "You hear $n's death cry."
    n = number_bits(4)
    if n == 0:
        msg = "$n hits the ground ... DEAD."
    elif n == 1 and not ch.is_npc:
        # A player's material is NULL in the C (new_char never sets it); a mob's is str_dup'd, so never NULL, and
        # case 1 falls through to case 2 for it.
        msg = "$n splatters blood on your armor."
    elif n in _DEATH_PARTS or n == 1:
        part, text, obj_vnum = _DEATH_PARTS[2 if n == 1 else n]
        if ch.parts & part:
            msg, vnum = text, obj_vnum
    act(msg, ch, None, None, C.TO_ROOM)

    if vnum != 0:
        name = ch.short_descr if ch.is_npc else ch.name
        obj = create_object(game, game.index.get_obj_index(vnum), 0)
        obj.timer = number_range(4, 7)
        obj.short_descr = _name_into(obj.short_descr, name)
        obj.description = _name_into(obj.description, name)
        if obj.item_type == C.ITEM_FOOD:
            if ch.form & C.FORM_POISON:
                obj.value[3] = 1
            elif not ch.form & C.FORM_EDIBLE:
                obj.item_type = C.ITEM_TRASH
        obj_to_room(obj, ch.in_room)

    msg = "You hear something's death cry." if ch.is_npc else "You hear someone's death cry."
    was_in_room = ch.in_room
    for door in range(6):
        pexit = was_in_room.exit[door]
        if pexit is not None and pexit.to_room is not None and pexit.to_room is not was_in_room:
            ch.in_room = pexit.to_room
            act(msg, ch, None, None, C.TO_ROOM)
    ch.in_room = was_in_room


# C: fight.c raw_kill
def raw_kill(victim) -> None:
    from charm.data.races import RACE_TABLE
    from charm.entities.handler import affect_remove, extract_char

    game = _game()
    stop_fighting(game, victim, True)
    death_cry(victim)
    make_corpse(victim)
    if victim.is_npc:
        victim.index.killed += 1
        # kill_table[level].killed++ too, in the C; nothing reads kill_table, so the port doesn't keep it
        extract_char(game, victim, True)
        return
    extract_char(game, victim, False)
    while victim.affected:
        affect_remove(victim, victim.affected[0])
    victim.affected_by = RACE_TABLE[victim.race].aff
    for i in range(4):
        victim.armor[i] = 100
    victim.position = C.POS_RESTING
    victim.hit = max(1, victim.hit)
    victim.mana = max(1, victim.mana)
    victim.move = max(1, victim.move)


# C: fight.c group_gain
def group_gain(ch, victim) -> None:
    from charm.commands.comm import is_same_group
    from charm.core.log import bug
    from charm.entities.handler import is_evil, is_good, obj_from_char, obj_to_room
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.update import gain_exp

    # "Monsters don't get kill xp's or alignment changes. P-killing doesn't help either. Dying of mortal wounds or
    # poison doesn't give xp to anyone!"
    if victim is ch:
        return
    members = 0
    group_levels = 0
    for gch in ch.in_room.people:
        if is_same_group(gch, ch):
            members += 1
            group_levels += c_div(gch.level, 2) if gch.is_npc else gch.level
    if members == 0:
        bug("Group_gain: members.", members)
        members = 1
        group_levels = ch.level
    for gch in list(ch.in_room.people):
        if not is_same_group(gch, ch) or gch.is_npc:
            continue
        xp = xp_compute(gch, victim, group_levels)
        send_to_char("You receive %d experience points.\n\r" % xp, gch)
        gain_exp(gch, xp)
        # sic: the killer's equipment is checked, once for each member, not the member's own (#75)
        for obj in list(ch.carrying):
            if obj.wear_loc == C.WEAR_NONE:
                continue
            if ((obj.extra_flags & C.ITEM_ANTI_EVIL and is_evil(ch))
                    or (obj.extra_flags & C.ITEM_ANTI_GOOD and is_good(ch))
                    or (obj.extra_flags & C.ITEM_ANTI_NEUTRAL and _is_neutral(ch))):
                act("You are zapped by $p.", ch, obj, None, C.TO_CHAR)
                act("$n is zapped by $p.", ch, obj, None, C.TO_ROOM)
                obj_from_char(obj)
                obj_to_room(obj, ch.in_room)


_BASE_EXP = {-9: 1, -8: 2, -7: 5, -6: 9, -5: 11, -4: 22, -3: 33, -2: 50, -1: 66, 0: 83, 1: 99, 2: 121, 3: 143,
             4: 165}


# C: fight.c xp_compute
def xp_compute(gch, victim, total_levels: int) -> int:
    """Compute xp for a kill, and adjust the killer's alignment."""
    level_range = victim.level - gch.level
    base_exp = _BASE_EXP.get(level_range, 0)  # "compute the base exp"
    if level_range > 4:
        base_exp = 160 + 20 * (level_range - 4)

    # "do alignment computations"
    align = victim.alignment - gch.alignment
    if victim.act & C.ACT_NOALIGN:
        pass  # "no change"
    elif align > 500:  # "monster is more good than slayer"
        change = c_div(c_div((align - 500) * base_exp, 500) * gch.level, total_levels)
        change = max(1, change)
        gch.alignment = sh_int(max(-1000, gch.alignment - change))
    elif align < -500:  # "monster is more evil than slayer"
        change = c_div(c_div((-1 * align - 500) * base_exp, 500) * gch.level, total_levels)
        change = max(1, change)
        gch.alignment = sh_int(min(1000, gch.alignment + change))
    else:  # "improve this someday"
        change = c_div(c_div(gch.alignment * base_exp, 500) * gch.level, total_levels)
        gch.alignment = sh_int(gch.alignment - change)

    # "calculate exp multiplier"
    va = victim.alignment
    if victim.act & C.ACT_NOALIGN:
        xp = base_exp
    elif gch.alignment > 500:  # "for goodie two shoes"
        if va < -750:
            xp = c_div(base_exp * 4, 3)
        elif va < -500:
            xp = c_div(base_exp * 5, 4)
        elif va > 750:
            xp = c_div(base_exp, 4)
        elif va > 500:
            xp = c_div(base_exp, 2)
        elif va > 250:
            xp = c_div(base_exp * 3, 4)
        else:
            xp = base_exp
    elif gch.alignment < -500:  # "for baddies"
        if va > 750:
            xp = c_div(base_exp * 5, 4)
        elif va > 500:
            xp = c_div(base_exp * 11, 10)
        elif va < -750:
            xp = c_div(base_exp, 2)
        elif va < -500:
            xp = c_div(base_exp * 3, 4)
        elif va < -250:
            xp = c_div(base_exp * 9, 10)
        else:
            xp = base_exp
    elif gch.alignment > 200:  # "a little good"
        if va < -500:
            xp = c_div(base_exp * 6, 5)
        elif va > 750:
            xp = c_div(base_exp, 2)
        elif va > 0:
            xp = c_div(base_exp * 3, 4)
        else:
            xp = base_exp
    elif gch.alignment < -200:  # "a little bad"
        if va > 500:
            xp = c_div(base_exp * 6, 5)
        elif va < -750:
            xp = c_div(base_exp, 2)
        elif va < 0:
            xp = c_div(base_exp * 3, 4)
        else:
            xp = base_exp
    else:  # "neutral"
        if va > 500 or va < -500:
            xp = c_div(base_exp * 4, 3)
        elif -200 < va < 200:
            xp = c_div(base_exp, 2)
        else:
            xp = base_exp

    if gch.level < 6:  # "more exp at the low levels"
        xp = c_div(10 * xp, gch.level + 4)
    if gch.level > 35:  # "less at high"
        xp = c_div(15 * xp, gch.level - 25)
    # "reduce for playing time": "compute quarter-hours per level"
    played = gch.played + int(_game().current_time - gch.logon)
    time_per_level = c_div(c_div(4 * played, 3600), gch.level)
    time_per_level = max(2, min(time_per_level, 12))
    if gch.level < 15:  # "make it a curve"
        time_per_level = max(time_per_level, 15 - gch.level)
    xp = c_div(xp * time_per_level, 12)
    xp = number_range(c_div(xp * 3, 4), c_div(xp * 5, 4))  # "randomize the rewards"
    xp = c_div(xp * gch.level, max(1, total_levels - 1))  # "adjust for grouping"
    return xp


_DAMAGE_WORDS = (  # (the most dam_percent each is for, the word for "you", the word for "$n")
    (5, "scratch", "scratches"), (10, "graze", "grazes"), (15, "hit", "hits"), (20, "injure", "injures"),
    (25, "wound", "wounds"), (30, "maul", "mauls"), (35, "decimate", "decimates"), (40, "devastate", "devastates"),
    (45, "maim", "maims"), (50, "MUTILATE", "MUTILATES"), (55, "DISEMBOWEL", "DISEMBOWELS"),
    (60, "DISMEMBER", "DISMEMBERS"), (65, "MASSACRE", "MASSACRES"), (70, "MANGLE", "MANGLES"),
    (75, "*** DEMOLISH ***", "*** DEMOLISHES ***"), (80, "*** DEVASTATE ***", "*** DEVASTATES ***"),
    (85, "=== OBLITERATE ===", "=== OBLITERATES ==="), (90, ">>> ANNIHILATE <<<", ">>> ANNIHILATES <<<"),
    (95, "<<< ERADICATE >>>", "<<< ERADICATES >>>"),
)


# C: fight.c dam_message
def dam_message(ch, victim, dam: int, dt: int, immune: bool) -> None:
    from charm.core.log import bug
    from charm.data.skills import SKILL_TABLE
    from charm.net.act import act

    if victim.max_hit == 0:
        raise CWouldCrash("fight.c dam_message: divides by the victim's max_hit, which is 0")
    dam_percent = c_div(100 * dam, victim.max_hit)
    if ch is None or victim is None:
        return
    if dam == 0:
        vs, vp = "miss", "misses"
    else:
        vs, vp = "do UNSPEAKABLE things to", "does UNSPEAKABLE things to"
        for most, s, p in _DAMAGE_WORDS:
            if dam_percent <= most:
                vs, vp = s, p
                break
    punct = "." if dam_percent <= 45 else "!"

    buf3 = None
    if dt == C.TYPE_HIT:
        if ch is victim:
            buf1 = "{3$n %s $melf%s{x" % (vp, punct)
            buf2 = "{2You %s yourself%s{x" % (vs, punct)
        else:
            buf1 = "{3$n %s $N%s{x" % (vp, punct)
            buf2 = "{2You %s $N%s{x" % (vs, punct)
            buf3 = "{4$n %s you%s{x" % (vp, punct)
    else:
        if 0 <= dt < C.MAX_SKILL:
            if dt >= len(SKILL_TABLE):
                raise NotPorted(f"fight.c dam_message: dt {dt}, a skill_table row past the table (a NULL noun)")
            attack = SKILL_TABLE[dt].noun_damage
        elif C.TYPE_HIT <= dt < C.TYPE_HIT + C.MAX_DAMAGE_MESSAGE:
            attack = _attack(dt - C.TYPE_HIT).noun
        else:
            bug("Dam_message: bad dt %d.", dt)
            dt = C.TYPE_HIT
            attack = _attack(0).name
        if attack is None:
            raise NotPorted(f"fight.c dam_message: dt {dt}'s noun is NULL")
        if immune:
            if ch is victim:
                buf1 = "{3$n is unaffected by $s own %s.{x" % attack
                buf2 = "{2Luckily, you are immune to that.{x"
            else:
                buf1 = "{3$N is unaffected by $n's %s!{x" % attack
                buf2 = "{2$N is unaffected by your %s!{x" % attack
                buf3 = "{4$n's %s is powerless against you.{x" % attack
        else:
            if ch is victim:
                buf1 = "{3$n's %s %s $m%s{x" % (attack, vp, punct)
                buf2 = "{2Your %s %s you%s{x" % (attack, vp, punct)
            else:
                buf1 = "{3$n's %s %s $N%s{x" % (attack, vp, punct)
                buf2 = "{2Your %s %s $N%s{x" % (attack, vp, punct)
                buf3 = "{4$n's %s %s you%s{x" % (attack, vp, punct)
    if ch is victim:
        act(buf1, ch, None, None, C.TO_ROOM)
        act(buf2, ch, None, None, C.TO_CHAR)
    else:
        act(buf1, ch, None, victim, C.TO_NOTVICT)
        act(buf2, ch, None, victim, C.TO_CHAR)
        act(buf3, ch, None, victim, C.TO_VICT)


# C: fight.c disarm
def disarm(ch, victim) -> None:
    """Disarm a creature. "Caller must check for successful attack."."""
    from charm.commands.obj import get_obj
    from charm.entities.handler import can_see_obj, get_eq_char, obj_from_char, obj_to_char, obj_to_room
    from charm.net.act import act

    obj = get_eq_char(victim, C.WEAR_WIELD)
    if obj is None:
        return
    if obj.extra_flags & C.ITEM_NOREMOVE:
        act("{5$S weapon won't budge!{x", ch, None, victim, C.TO_CHAR)
        act("{5$n tries to disarm you, but your weapon won't budge!{x", ch, None, victim, C.TO_VICT)
        act("{5$n tries to disarm $N, but fails.{x", ch, None, victim, C.TO_NOTVICT)
        return
    act("{5$n DISARMS you and sends your weapon flying!{x", ch, None, victim, C.TO_VICT)
    act("{5You disarm $N!{x", ch, None, victim, C.TO_CHAR)
    act("{5$n disarms $N!{x", ch, None, victim, C.TO_NOTVICT)
    obj_from_char(obj)
    if obj.extra_flags & (C.ITEM_NODROP | C.ITEM_INVENTORY):
        obj_to_char(obj, victim)
    else:
        obj_to_room(obj, victim.in_room)
        if victim.is_npc and victim.wait == 0 and can_see_obj(victim, obj):
            get_obj(victim, obj, None)


def _skill_level(sn: int, ch) -> int:
    from charm.data.skills import SKILL_TABLE

    return SKILL_TABLE[sn].skill_level[ch.class_]


def _beats(sn: int) -> int:
    from charm.data.skills import SKILL_TABLE

    return SKILL_TABLE[sn].beats


def _daze_state(ch, npulse: int) -> None:
    """DAZE_STATE."""
    ch.daze = sh_int(max(ch.daze, npulse))


def _kill_stealing(ch, victim) -> bool:
    from charm.commands.comm import is_same_group
    from charm.net.output import send_to_char

    if victim.is_npc and victim.fighting is not None and not is_same_group(ch, victim.fighting):
        send_to_char("Kill stealing is not permitted.\n\r", ch)
        return True
    return False


def _target(ch, arg: str, none_fighting: str):
    """The skills' victim: whom ch is fighting if no one is named, or the one named in the room."""
    from charm.entities.handler import get_char_room
    from charm.net.output import send_to_char

    if arg == "":
        if ch.fighting is None:
            send_to_char(none_fighting, ch)
        return ch.fighting
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
    return victim


# C: fight.c do_berserk
def do_berserk(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.core.rng import number_fuzzy
    from charm.entities.handler import affect_to_char, get_skill, is_affected, is_affected_by
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve
    from charm.world.index import Affect
    from charm.world.lookup import skill_lookup

    gsn = _gsn("gsn_berserk")
    chance = get_skill(ch, gsn)
    if (chance == 0 or (ch.is_npc and not ch.off_flags & C.OFF_BERSERK)
            or (not ch.is_npc and ch.level < _skill_level(gsn, ch))):
        send_to_char("You turn red in the face, but nothing happens.\n\r", ch)
        return
    if is_affected(ch, C.AFF_BERSERK) or is_affected_by(ch, gsn) or is_affected_by(ch, skill_lookup("frenzy")):
        send_to_char("You get a little madder.\n\r", ch)
        return
    if is_affected(ch, C.AFF_CALM):
        send_to_char("You're feeling to mellow to berserk.\n\r", ch)  # sic (#77)
        return
    if ch.mana < 50:
        send_to_char("You can't get up enough energy.\n\r", ch)
        return
    # "modifiers": "fighting"
    if ch.position == C.POS_FIGHTING:
        chance += 10
    # "damage -- below 50% of hp helps, above hurts"
    if ch.max_hit == 0:
        raise CWouldCrash("fight.c do_berserk: divides by max_hit, which is 0")
    hp_percent = c_div(100 * ch.hit, ch.max_hit)
    chance += 25 - c_div(hp_percent, 2)
    if number_percent() < chance:
        wait_state(ch, C.PULSE_VIOLENCE)
        ch.mana = sh_int(ch.mana - 50)
        ch.move = sh_int(c_div(ch.move, 2))
        # "heal a little damage"
        ch.hit = sh_int(ch.hit + ch.level * 2)
        ch.hit = min(ch.hit, ch.max_hit)
        send_to_char("Your pulse races as you are consumed by rage!\n\r", ch)
        act("$n gets a wild look in $s eyes.", ch, None, None, C.TO_ROOM)
        check_improve(ch, gsn, True, 2)
        duration = number_fuzzy(c_div(ch.level, 8))
        modifier = max(1, c_div(ch.level, 5))
        for location in (C.APPLY_HITROLL, C.APPLY_DAMROLL):
            affect_to_char(ch, Affect(where=C.TO_AFFECTS, type=gsn, level=ch.level, duration=duration,
                                      location=location, modifier=modifier, bitvector=C.AFF_BERSERK))
        affect_to_char(ch, Affect(where=C.TO_AFFECTS, type=gsn, level=ch.level, duration=duration,
                                  location=C.APPLY_AC, modifier=max(10, 10 * c_div(ch.level, 5)),
                                  bitvector=C.AFF_BERSERK))
    else:
        wait_state(ch, 3 * C.PULSE_VIOLENCE)
        ch.mana = sh_int(ch.mana - 25)
        ch.move = sh_int(c_div(ch.move, 2))
        send_to_char("Your pulse speeds up, but nothing happens.\n\r", ch)
        check_improve(ch, gsn, False, 2)


# C: fight.c do_bash
def do_bash(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_ac, get_curr_stat, get_skill, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_bash")
    _, arg = one_argument(argument)
    chance = get_skill(ch, gsn)
    if (chance == 0 or (ch.is_npc and not ch.off_flags & C.OFF_BASH)
            or (not ch.is_npc and ch.level < _skill_level(gsn, ch))):
        send_to_char("Bashing? What's that?\n\r", ch)
        return
    victim = _target(ch, arg, "But you aren't fighting anyone!\n\r")
    if victim is None:
        return
    if victim.position < C.POS_FIGHTING:
        act("You'll have to let $M get back up first.", ch, None, victim, C.TO_CHAR)
        return
    if victim is ch:
        send_to_char("You try to bash your brains out, but fail.\n\r", ch)
        return
    if is_safe(ch, victim) or _kill_stealing(ch, victim):
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
        act("But $N is your friend!", ch, None, victim, C.TO_CHAR)
        return
    # "modifiers": "size  and weight"
    chance += c_div(ch.carry_weight, 250)
    chance -= c_div(victim.carry_weight, 200)
    if ch.size < victim.size:
        chance += (ch.size - victim.size) * 15
    else:
        chance += (ch.size - victim.size) * 10
    # "stats"
    chance += get_curr_stat(ch, C.STAT_STR)
    chance -= c_div(get_curr_stat(victim, C.STAT_DEX) * 4, 3)
    chance -= c_div(get_ac(victim, C.AC_BASH), 25)
    # "speed"
    if ch.off_flags & C.OFF_FAST or is_affected(ch, C.AFF_HASTE):
        chance += 10
    if victim.off_flags & C.OFF_FAST or is_affected(victim, C.AFF_HASTE):
        chance -= 30
    # "level"
    chance += ch.level - victim.level
    if not victim.is_npc and chance < get_skill(victim, _gsn("gsn_dodge")):
        # (the C's own dodge of a bash is commented out; only the penalty is left)
        chance -= 3 * (get_skill(victim, _gsn("gsn_dodge")) - chance)
    # "now the attack"
    if number_percent() < chance:
        act("{5$n sends you sprawling with a powerful bash!{x", ch, None, victim, C.TO_VICT)
        act("{5You slam into $N, and send $M flying!{x", ch, None, victim, C.TO_CHAR)
        act("{5$n sends $N sprawling with a powerful bash.{x", ch, None, victim, C.TO_NOTVICT)
        check_improve(ch, gsn, True, 1)
        _daze_state(victim, 3 * C.PULSE_VIOLENCE)
        wait_state(ch, _beats(gsn))
        victim.position = C.POS_RESTING
        damage(ch, victim, number_range(2, 2 + 2 * ch.size + c_div(chance, 20)), gsn, C.DAM_BASH, False)
    else:
        damage(ch, victim, 0, gsn, C.DAM_BASH, False)
        act("{5You fall flat on your face!{x", ch, None, victim, C.TO_CHAR)
        act("{5$n falls flat on $s face.{x", ch, None, victim, C.TO_NOTVICT)
        act("{5You evade $n's bash, causing $m to fall flat on $s face.{x", ch, None, victim, C.TO_VICT)
        check_improve(ch, gsn, False, 1)
        ch.position = C.POS_RESTING
        wait_state(ch, c_div(_beats(gsn) * 3, 2))
    check_killer(ch, victim)


_DIRT_TERRAIN = {C.SECT_INSIDE: -20, C.SECT_CITY: -10, C.SECT_FIELD: 5, C.SECT_MOUNTAIN: -10, C.SECT_DESERT: 10}


# C: fight.c do_dirt
def do_dirt(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import affect_to_char, get_curr_stat, get_skill, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve
    from charm.world.index import Affect

    gsn = _gsn("gsn_dirt")
    _, arg = one_argument(argument)
    chance = get_skill(ch, gsn)
    if (chance == 0 or (ch.is_npc and not ch.off_flags & C.OFF_KICK_DIRT)
            or (not ch.is_npc and ch.level < _skill_level(gsn, ch))):
        send_to_char("You get your feet dirty.\n\r", ch)
        return
    victim = _target(ch, arg, "But you aren't in combat!\n\r")
    if victim is None:
        return
    if is_affected(victim, C.AFF_BLIND):
        act("$E's already been blinded.", ch, None, victim, C.TO_CHAR)
        return
    if victim is ch:
        send_to_char("Very funny.\n\r", ch)
        return
    if is_safe(ch, victim) or _kill_stealing(ch, victim):
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
        act("But $N is such a good friend!", ch, None, victim, C.TO_CHAR)
        return
    # "modifiers": "dexterity"
    chance += get_curr_stat(ch, C.STAT_DEX)
    chance -= 2 * get_curr_stat(victim, C.STAT_DEX)
    # "speed"
    if ch.off_flags & C.OFF_FAST or is_affected(ch, C.AFF_HASTE):
        chance += 10
    if victim.off_flags & C.OFF_FAST or is_affected(victim, C.AFF_HASTE):
        chance -= 25
    # "level"
    chance += (ch.level - victim.level) * 2
    # "sloppy hack to prevent false zeroes"
    if chance % 5 == 0:  # non-negative: a C % is 0 for the same values, signed or not
        chance += 1
    # "terrain"
    sector = ch.in_room.sector_type
    if sector in (C.SECT_WATER_SWIM, C.SECT_WATER_NOSWIM, C.SECT_AIR):
        chance = 0
    else:
        chance += _DIRT_TERRAIN.get(sector, 0)
    if chance == 0:
        send_to_char("There isn't any dirt to kick.\n\r", ch)
        return
    # "now the attack"
    if number_percent() < chance:
        act("{5$n is blinded by the dirt in $s eyes!{x", victim, None, None, C.TO_ROOM)
        act("{5$n kicks dirt in your eyes!{x", ch, None, victim, C.TO_VICT)
        damage(ch, victim, number_range(2, 5), gsn, C.DAM_NONE, False)
        send_to_char("{5You can't see a thing!{x\n\r", victim)
        check_improve(ch, gsn, True, 2)
        wait_state(ch, _beats(gsn))
        affect_to_char(victim, Affect(where=C.TO_AFFECTS, type=gsn, level=ch.level, duration=0,
                                      location=C.APPLY_HITROLL, modifier=-4, bitvector=C.AFF_BLIND))
    else:
        damage(ch, victim, 0, gsn, C.DAM_NONE, True)
        check_improve(ch, gsn, False, 2)
        wait_state(ch, _beats(gsn))
    check_killer(ch, victim)


# C: fight.c do_trip
def do_trip(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_curr_stat, get_skill, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_trip")
    _, arg = one_argument(argument)
    chance = get_skill(ch, gsn)
    if (chance == 0 or (ch.is_npc and not ch.off_flags & C.OFF_TRIP)
            or (not ch.is_npc and ch.level < _skill_level(gsn, ch))):
        send_to_char("Tripping?  What's that?\n\r", ch)
        return
    victim = _target(ch, arg, "But you aren't fighting anyone!\n\r")
    if victim is None:
        return
    if is_safe(ch, victim) or _kill_stealing(ch, victim):
        return
    if is_affected(victim, C.AFF_FLYING):
        act("$S feet aren't on the ground.", ch, None, victim, C.TO_CHAR)
        return
    if victim.position < C.POS_FIGHTING:
        act("$N is already down.", ch, None, victim, C.TO_CHAR)
        return
    if victim is ch:
        send_to_char("{5You fall flat on your face!{x\n\r", ch)
        wait_state(ch, 2 * _beats(gsn))
        act("{5$n trips over $s own feet!{x", ch, None, None, C.TO_ROOM)
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
        act("$N is your beloved master.", ch, None, victim, C.TO_CHAR)
        return
    # "modifiers": "size"
    if ch.size < victim.size:
        chance += (ch.size - victim.size) * 10  # "bigger = harder to trip"
    # "dex"
    chance += get_curr_stat(ch, C.STAT_DEX)
    chance -= c_div(get_curr_stat(victim, C.STAT_DEX) * 3, 2)
    # "speed"
    if ch.off_flags & C.OFF_FAST or is_affected(ch, C.AFF_HASTE):
        chance += 10
    if victim.off_flags & C.OFF_FAST or is_affected(victim, C.AFF_HASTE):
        chance -= 20
    # "level"
    chance += (ch.level - victim.level) * 2
    # "now the attack"
    if number_percent() < chance:
        act("{5$n trips you and you go down!{x", ch, None, victim, C.TO_VICT)
        act("{5You trip $N and $N goes down!{x", ch, None, victim, C.TO_CHAR)
        act("{5$n trips $N, sending $M to the ground.{x", ch, None, victim, C.TO_NOTVICT)
        check_improve(ch, gsn, True, 1)
        _daze_state(victim, 2 * C.PULSE_VIOLENCE)
        wait_state(ch, _beats(gsn))
        victim.position = C.POS_RESTING
        damage(ch, victim, number_range(2, 2 + 2 * victim.size), gsn, C.DAM_BASH, True)
    else:
        damage(ch, victim, 0, gsn, C.DAM_BASH, True)
        wait_state(ch, c_div(_beats(gsn) * 2, 3))
        check_improve(ch, gsn, False, 1)
    check_killer(ch, victim)


# C: fight.c do_backstab
def do_backstab(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_char_room, get_eq_char, get_skill, is_awake
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_backstab")
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Backstab whom?\n\r", ch)
        return
    if ch.fighting is not None:
        send_to_char("You're facing the wrong end.\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim is ch:
        send_to_char("How can you sneak up on yourself?\n\r", ch)
        return
    if is_safe(ch, victim) or _kill_stealing(ch, victim):
        return
    if get_eq_char(ch, C.WEAR_WIELD) is None:
        send_to_char("You need to wield a weapon to backstab.\n\r", ch)
        return
    if victim.hit < c_div(victim.max_hit, 3):
        act("$N is hurt and suspicious ... you can't sneak up.", ch, None, victim, C.TO_CHAR)
        return
    check_killer(ch, victim)
    wait_state(ch, _beats(gsn))
    if number_percent() < get_skill(ch, gsn) or (get_skill(ch, gsn) >= 2 and not is_awake(victim)):
        check_improve(ch, gsn, True, 1)
        multi_hit(ch, victim, gsn)
    else:
        check_improve(ch, gsn, False, 1)
        damage(ch, victim, 0, gsn, C.DAM_NONE, True)


# C: fight.c do_rescue
def do_rescue(ch, argument: str) -> None:
    from charm.commands.comm import is_same_group, wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_char_room, get_skill
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_rescue")
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Rescue whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim is ch:
        send_to_char("What about fleeing instead?\n\r", ch)
        return
    if not ch.is_npc and victim.is_npc:
        send_to_char("Doesn't need your help!\n\r", ch)
        return
    if ch.fighting is victim:
        send_to_char("Too late.\n\r", ch)
        return
    fch = victim.fighting
    if fch is None:
        send_to_char("That person is not fighting right now.\n\r", ch)
        return
    if fch.is_npc and not is_same_group(ch, victim):
        send_to_char("Kill stealing is not permitted.\n\r", ch)
        return
    wait_state(ch, _beats(gsn))
    if number_percent() > get_skill(ch, gsn):
        send_to_char("You fail the rescue.\n\r", ch)
        check_improve(ch, gsn, False, 1)
        return
    act("{5You rescue $N!{x", ch, None, victim, C.TO_CHAR)
    act("{5$n rescues you!{x", ch, None, victim, C.TO_VICT)
    act("{5$n rescues $N!{x", ch, None, victim, C.TO_NOTVICT)
    check_improve(ch, gsn, True, 1)
    game = _game()
    stop_fighting(game, fch, False)
    stop_fighting(game, victim, False)
    check_killer(ch, fch)
    set_fighting(ch, fch)  # sic: a rescuer already fighting keeps that fight (#77)
    set_fighting(fch, ch)


# C: fight.c do_kick
def do_kick(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.entities.handler import get_skill
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_kick")
    if not ch.is_npc and ch.level < _skill_level(gsn, ch):
        send_to_char("You better leave the martial arts to fighters.\n\r", ch)
        return
    if ch.is_npc and not ch.off_flags & C.OFF_KICK:
        return
    victim = ch.fighting
    if victim is None:
        send_to_char("You aren't fighting anyone.\n\r", ch)
        return
    wait_state(ch, _beats(gsn))
    if get_skill(ch, gsn) > number_percent():
        damage(ch, victim, number_range(1, ch.level), gsn, C.DAM_BASH, True)
        check_improve(ch, gsn, True, 1)
    else:
        damage(ch, victim, 0, gsn, C.DAM_BASH, True)
        check_improve(ch, gsn, False, 1)
    check_killer(ch, victim)


# C: fight.c do_disarm
def do_disarm(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.entities.handler import get_curr_stat, get_eq_char, get_skill, get_weapon_skill, get_weapon_sn
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.skills import check_improve

    gsn = _gsn("gsn_disarm")
    hth = 0
    chance = get_skill(ch, gsn)
    if chance == 0:
        send_to_char("You don't know how to disarm opponents.\n\r", ch)
        return
    if get_eq_char(ch, C.WEAR_WIELD) is None:
        hth = get_skill(ch, _gsn("gsn_hand_to_hand"))
        if hth == 0 or (ch.is_npc and not ch.off_flags & C.OFF_DISARM):
            send_to_char("You must wield a weapon to disarm.\n\r", ch)
            return
    victim = ch.fighting
    if victim is None:
        send_to_char("You aren't fighting anyone.\n\r", ch)
        return
    if get_eq_char(victim, C.WEAR_WIELD) is None:
        send_to_char("Your opponent is not wielding a weapon.\n\r", ch)
        return
    # "find weapon skills"
    ch_weapon = get_weapon_skill(ch, get_weapon_sn(ch))
    vict_weapon = get_weapon_skill(victim, get_weapon_sn(victim))
    ch_vict_weapon = get_weapon_skill(ch, get_weapon_sn(victim))
    # "modifiers": "skill"
    if get_eq_char(ch, C.WEAR_WIELD) is None:
        chance = c_div(chance * hth, 150)
    else:
        chance = c_div(chance * ch_weapon, 100)
    chance += c_div(c_div(ch_vict_weapon, 2) - vict_weapon, 2)
    # "dex vs. strength"
    chance += get_curr_stat(ch, C.STAT_DEX)
    chance -= 2 * get_curr_stat(victim, C.STAT_STR)
    # "level"
    chance += (ch.level - victim.level) * 2
    # "and now the attack"
    if number_percent() < chance:
        wait_state(ch, _beats(gsn))
        disarm(ch, victim)
        check_improve(ch, gsn, True, 1)
    else:
        wait_state(ch, _beats(gsn))
        act("{5You fail to disarm $N.{x", ch, None, victim, C.TO_CHAR)
        act("{5$n tries to disarm you, but fails.{x", ch, None, victim, C.TO_VICT)
        act("{5$n tries to disarm $N, but fails.{x", ch, None, victim, C.TO_NOTVICT)
        check_improve(ch, gsn, False, 1)
    check_killer(ch, victim)


# C: fight.c do_kill
def do_kill(ch, argument: str) -> None:
    from charm.commands.comm import is_same_group, wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_char_room, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Kill whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    # (The C's "You must MURDER a player" check is commented out: "Allow player killing".)
    if victim is ch:
        send_to_char("You hit yourself.  Ouch!\n\r", ch)
        multi_hit(ch, ch, C.TYPE_UNDEFINED)
        return
    if is_safe(ch, victim):
        return
    if victim.fighting is not None and not is_same_group(ch, victim.fighting):
        send_to_char("Kill stealing is not permitted.\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
        act("$N is your beloved master.", ch, None, victim, C.TO_CHAR)
        return
    if ch.position == C.POS_FIGHTING:
        send_to_char("You do the best you can!\n\r", ch)
        return
    wait_state(ch, 1 * C.PULSE_VIOLENCE)
    check_killer(ch, victim)
    multi_hit(ch, victim, C.TYPE_UNDEFINED)


# C: fight.c do_murde
def do_murde(ch, argument: str) -> None:
    from charm.net.output import send_to_char

    send_to_char("If you want to MURDER, spell it out.\n\r", ch)


# C: fight.c do_murder
def do_murder(ch, argument: str) -> None:
    from charm.commands.comm import do_yell, is_same_group, wait_state
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_char_room, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Murder whom?\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM) or (ch.is_npc and ch.act & C.ACT_PET):
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim is ch:
        send_to_char("Suicide is a mortal sin.\n\r", ch)
        return
    if is_safe(ch, victim):
        return
    if victim.is_npc and victim.fighting is not None and not is_same_group(ch, victim.fighting):
        send_to_char("Kill stealing is not permitted.\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
        act("$N is your beloved master.", ch, None, victim, C.TO_CHAR)
        return
    if ch.position == C.POS_FIGHTING:
        send_to_char("You do the best you can!\n\r", ch)
        return
    wait_state(ch, 1 * C.PULSE_VIOLENCE)
    if ch.is_npc:
        buf = "Help! I am being attacked by %s!" % ch.short_descr
    else:
        buf = "Help!  I am being attacked by %s!" % ch.name
    do_yell(victim, buf)
    check_killer(ch, victim)
    multi_hit(ch, victim, C.TYPE_UNDEFINED)


# C: fight.c do_flee
def do_flee(ch, argument: str) -> None:
    from charm.commands.move import move_char
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.update import gain_exp

    victim = ch.fighting
    if victim is None:
        if ch.position == C.POS_FIGHTING:
            ch.position = C.POS_STANDING
        send_to_char("You aren't fighting anyone.\n\r", ch)
        return
    was_in = ch.in_room
    for _attempt in range(6):
        door = number_door()
        pexit = was_in.exit[door]
        if (pexit is None or pexit.to_room is None or pexit.exit_info & C.EX_CLOSED
                or number_range(0, ch.daze) != 0
                or (ch.is_npc and pexit.to_room.room_flags & C.ROOM_NO_MOB)):
            continue
        move_char(ch, door, False)
        now_in = ch.in_room
        if now_in is was_in:
            continue
        ch.in_room = was_in
        act("$n has fled!", ch, None, None, C.TO_ROOM)
        ch.in_room = now_in
        if not ch.is_npc:
            send_to_char("You flee from combat!\n\r", ch)
            if ch.class_ == 2 and number_percent() < 3 * c_div(ch.level, 2):
                send_to_char("You snuck away safely.\n\r", ch)
            else:
                send_to_char("You lost 10 exp.\n\r", ch)
                gain_exp(ch, -10)
        stop_fighting(_game(), ch, True)
        return
    send_to_char("PANIC! You couldn't escape!\n\r", ch)


# C: fight.c do_surrender
def do_surrender(ch, argument: str) -> None:
    from charm.net.act import act
    from charm.net.output import send_to_char
    from charm.systems.mobprog import has_trigger, mp_percent_trigger

    mob = ch.fighting
    if mob is None:
        send_to_char("But you're not fighting!\n\r", ch)
        return
    act("You surrender to $N!", ch, None, mob, C.TO_CHAR)
    act("$n surrenders to you!", ch, None, mob, C.TO_VICT)
    act("$n tries to surrender to $N!", ch, None, mob, C.TO_NOTVICT)
    stop_fighting(_game(), ch, True)
    if (not ch.is_npc and mob.is_npc
            and (not has_trigger(mob, C.TRIG_SURR) or not mp_percent_trigger(mob, ch, None, None, C.TRIG_SURR))):
        act("$N seems to ignore your cowardly act!", ch, None, mob, C.TO_CHAR)
        multi_hit(mob, ch, C.TYPE_UNDEFINED)


# C: fight.c do_sla
def do_sla(ch, argument: str) -> None:
    from charm.net.output import send_to_char

    send_to_char("If you want to SLAY, spell it out.\n\r", ch)


# C: fight.c do_slay
def do_slay(ch, argument: str) -> None:
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_char_room, get_trust
    from charm.net.act import act
    from charm.net.output import send_to_char

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Slay whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if ch is victim:
        send_to_char("Suicide is a mortal sin.\n\r", ch)
        return
    if not victim.is_npc and victim.level >= get_trust(ch):
        send_to_char("You failed.\n\r", ch)
        return
    act("{1You slay $M in cold blood!{x", ch, None, victim, C.TO_CHAR)
    act("{1$n slays you in cold blood!{x", ch, None, victim, C.TO_VICT)
    act("{1$n slays $N in cold blood!{x", ch, None, victim, C.TO_NOTVICT)
    raw_kill(victim)


# C: fight.c stop_fighting
def stop_fighting(game, ch, f_both: bool) -> None:
    for fch in game.char_list:
        if fch is ch or (f_both and fch.fighting is ch):
            fch.fighting = None
            fch.position = fch.default_pos if fch.is_npc else C.POS_STANDING
            update_pos(fch)


# C: fight.c update_pos
def update_pos(victim) -> None:
    if victim.hit > 0:
        if victim.position <= C.POS_STUNNED:
            victim.position = C.POS_STANDING
        return
    if victim.is_npc and victim.hit < 1:
        victim.position = C.POS_DEAD
        return
    if victim.hit <= -11:
        victim.position = C.POS_DEAD
        return
    if victim.hit <= -6:
        victim.position = C.POS_MORTAL
    elif victim.hit <= -3:
        victim.position = C.POS_INCAP
    else:
        victim.position = C.POS_STUNNED


# C: fight.c is_safe
def is_safe(ch, victim) -> bool:
    from charm.entities.handler import is_affected, is_clan, is_immortal
    from charm.net.act import act
    from charm.net.output import send_to_char

    if victim.in_room is None or ch.in_room is None:
        return True
    if victim.fighting is ch or victim is ch:
        return False
    if is_immortal(ch) and ch.level > C.LEVEL_IMMORTAL:
        return False
    if victim.is_npc:
        # "killing mobiles"
        if victim.in_room.room_flags & C.ROOM_SAFE:
            send_to_char("Not in this room.\n\r", ch)
            return True
        if victim.index.shop is not None:
            send_to_char("The shopkeeper wouldn't like that.\n\r", ch)
            return True
        # "no killing healers, trainers, etc"
        if victim.act & (C.ACT_TRAIN | C.ACT_PRACTICE | C.ACT_IS_HEALER | C.ACT_IS_CHANGER):
            send_to_char("I don't think Mota would approve.\n\r", ch)
            return True
        if not ch.is_npc:
            if victim.act & C.ACT_PET:
                act("But $N looks so cute and cuddly...", ch, None, victim, C.TO_CHAR)
                return True
            if is_affected(victim, C.AFF_CHARM) and ch is not victim.master:
                send_to_char("You don't own that monster.\n\r", ch)
                return True
    elif ch.is_npc:
        # "killing players", "NPC doing the killing"
        if victim.in_room.room_flags & C.ROOM_SAFE:
            send_to_char("Not in this room.\n\r", ch)
            return True
        if is_affected(ch, C.AFF_CHARM) and ch.master is not None and ch.master.fighting is not victim:
            send_to_char("Players are your friends!\n\r", ch)
            return True
    else:
        # "player doing the killing"
        if not is_clan(ch):
            send_to_char("Join a clan if you want to kill players.\n\r", ch)
            return True
        if victim.act & (C.PLR_KILLER | C.PLR_THIEF):
            return False
        if not is_clan(victim):
            send_to_char("They aren't in a clan, leave them alone.\n\r", ch)
            return True
        if ch.level > victim.level + 8:
            send_to_char("Pick on someone your own size.\n\r", ch)
            return True
    return False
