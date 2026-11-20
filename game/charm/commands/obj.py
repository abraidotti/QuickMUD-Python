"""Objects, all of act_obj.c: get, put, drop, give, wear, wield, hold and remove, the corpse-looting rule, food and
drink, envenom, sacrifice, steal, shops and pet shops, and the magic items (quaff, recite, brandish, zap).

The magic items run up to the spell: obj_cast_spell (charm.systems.magic) raises NotPorted there.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_obj.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import is_number, mult_argument, number_argument, one_argument
from charm.core.cint import c_div, int32
from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.core.rng import number_fuzzy, number_percent, number_range
from charm.core.strings import atoi, smash_tilde, str_cmp, str_prefix
from charm.data import constants as C
from charm.data.attacks import ATTACK_TABLE
from charm.data.attributes import STR_APP
from charm.data.items import LIQ_TABLE
from charm.data.skills import SKILL_TABLE
from charm.entities import game as game_module
from charm.entities.handler import (
    affect_join, affect_strip, affect_to_obj, can_carry_n, can_carry_w, can_drop_obj, can_see, can_see_obj,
    char_to_room, create_money, deduct_cost, equip_char, extract_obj, get_carry_weight, get_char_room,
    get_curr_stat, get_eq_char, get_obj_carry, get_obj_here, get_obj_list, get_obj_number, get_obj_wear,
    get_obj_weight, get_skill, get_true_weight, get_trust, get_weapon_skill, get_weapon_sn, is_affected, is_awake,
    is_clan, is_immortal, is_name, is_obj_stat, obj_from_char, obj_from_obj, obj_from_room, obj_to_char, obj_to_obj,
    obj_to_room, unequip_char, weight_mult)
from charm.net.act import MOB_TRIGGER, act
from charm.net.output import send_to_char
from charm.world.index import Affect
from charm.world.lookup import GSN


def can_wear(obj, part: int) -> bool:
    """CAN_WEAR."""
    return bool(obj.wear_flags & part)


def _is_all(arg: str) -> bool:
    """The C's `!str_cmp (arg, "all") || !str_prefix ("all.", arg)`: 'all' or 'all.<name>'. (Python's str_cmp
    and str_prefix are the C's negated.)"""
    return str_cmp(arg, "all") or str_prefix("all.", arg)


# C: act_obj.c can_loot
def can_loot(ch, obj) -> bool:
    """"RT part of the corpse looting code"."""
    from charm.commands.comm import is_same_group

    if is_immortal(ch):
        return True
    if obj.owner is None:
        return True
    owner = None
    for wch in game_module.current.char_list:
        if str_cmp(wch.name, obj.owner):
            owner = wch  # the last match, as the C's loop runs on
    if owner is None:
        return True
    if str_cmp(ch.name, owner.name):
        return True
    if not owner.is_npc and owner.act & C.PLR_CANLOOT:
        return True
    return is_same_group(ch, owner)


# C: act_obj.c get_obj
def get_obj(ch, obj, container) -> None:
    from charm.commands.comm import do_split, is_same_group

    if not can_wear(obj, C.ITEM_TAKE):
        send_to_char("You can't take that.\n\r", ch)
        return
    if ch.carry_number + get_obj_number(obj) > can_carry_n(ch):
        act("$d: you can't carry that many items.", ch, None, obj.name, C.TO_CHAR)
        return
    if ((obj.in_obj is None or obj.in_obj.carried_by is not ch)
            and get_carry_weight(ch) + get_obj_weight(obj) > can_carry_w(ch)):
        act("$d: you can't carry that much weight.", ch, None, obj.name, C.TO_CHAR)
        return
    if not can_loot(ch, obj):
        act("Corpse looting is not permitted.", ch, None, None, C.TO_CHAR)
        return
    if obj.in_room is not None:
        for gch in obj.in_room.people:
            if gch.on is obj:
                act("$N appears to be using $p.", ch, obj, gch, C.TO_CHAR)
                return
    if container is not None:
        if container.index.vnum == C.OBJ_VNUM_PIT and get_trust(ch) < obj.level:
            send_to_char("You are not powerful enough to use it.\n\r", ch)
            return
        if (container.index.vnum == C.OBJ_VNUM_PIT and not can_wear(container, C.ITEM_TAKE)
                and not is_obj_stat(obj, C.ITEM_HAD_TIMER)):
            obj.timer = 0
        act("You get $p from $P.", ch, obj, container, C.TO_CHAR)
        act("$n gets $p from $P.", ch, obj, container, C.TO_ROOM)
        obj.extra_flags &= ~C.ITEM_HAD_TIMER
        obj_from_obj(obj)
    else:
        act("You get $p.", ch, obj, container, C.TO_CHAR)
        act("$n gets $p.", ch, obj, container, C.TO_ROOM)
        obj_from_room(obj)
    if obj.item_type == C.ITEM_MONEY:
        ch.silver += obj.value[0]
        ch.gold += obj.value[1]
        if ch.act & C.PLR_AUTOSPLIT:  # "AUTOSPLIT code"
            members = 0
            for gch in ch.in_room.people:
                if not is_affected(gch, C.AFF_CHARM) and is_same_group(gch, ch):
                    members += 1
            if members > 1 and (obj.value[0] > 1 or obj.value[1]):
                do_split(ch, "%d %d" % (obj.value[0], obj.value[1]))
        extract_obj(game_module.current, obj)
    else:
        obj_to_char(obj, ch)


# C: act_obj.c do_get
def do_get(ch, argument: str) -> None:
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if str_cmp(arg2, "from"):
        argument, arg2 = one_argument(argument)
    if arg1 == "":  # "Get type."
        send_to_char("Get what?\n\r", ch)
        return
    if arg2 == "":
        if not _is_all(arg1):  # "'get obj'"
            obj = get_obj_list(ch, arg1, ch.in_room.contents)
            if obj is None:
                act("I see no $T here.", ch, None, arg1, C.TO_CHAR)
                return
            get_obj(ch, obj, None)
        else:  # "'get all' or 'get all.obj'"
            found = False
            for obj in list(ch.in_room.contents):
                if (len(arg1) == 3 or is_name(arg1[4:], obj.name)) and can_see_obj(ch, obj):
                    found = True
                    get_obj(ch, obj, None)
            if not found:
                if len(arg1) == 3:
                    send_to_char("I see nothing here.\n\r", ch)
                else:
                    act("I see no $T here.", ch, None, arg1[4:], C.TO_CHAR)
        return
    # "'get ... container'"
    if _is_all(arg2):
        send_to_char("You can't do that.\n\r", ch)
        return
    container = get_obj_here(ch, arg2)
    if container is None:
        act("I see no $T here.", ch, None, arg2, C.TO_CHAR)
        return
    if container.item_type in (C.ITEM_CONTAINER, C.ITEM_CORPSE_NPC):
        pass
    elif container.item_type == C.ITEM_CORPSE_PC:
        if not can_loot(ch, container):
            send_to_char("You can't do that.\n\r", ch)
            return
    else:
        send_to_char("That's not a container.\n\r", ch)
        return
    if container.value[1] & C.CONT_CLOSED:
        act("The $d is closed.", ch, None, container.name, C.TO_CHAR)
        return
    if not _is_all(arg1):  # "'get obj container'"
        obj = get_obj_list(ch, arg1, container.contains)
        if obj is None:
            act("I see nothing like that in the $T.", ch, None, arg2, C.TO_CHAR)
            return
        get_obj(ch, obj, container)
        return
    # "'get all container' or 'get all.obj container'"
    found = False
    for obj in list(container.contains):
        if (len(arg1) == 3 or is_name(arg1[4:], obj.name)) and can_see_obj(ch, obj):
            found = True
            if container.index.vnum == C.OBJ_VNUM_PIT and not is_immortal(ch):
                send_to_char("Don't be so greedy!\n\r", ch)
                return
            get_obj(ch, obj, container)
    if not found:
        if len(arg1) == 3:
            act("I see nothing in the $T.", ch, None, arg2, C.TO_CHAR)
        else:
            act("I see nothing like that in the $T.", ch, None, arg2, C.TO_CHAR)


def _put_messages(ch, obj, container) -> None:
    if container.value[1] & C.CONT_PUT_ON:
        act("$n puts $p on $P.", ch, obj, container, C.TO_ROOM)
        act("You put $p on $P.", ch, obj, container, C.TO_CHAR)
    else:
        act("$n puts $p in $P.", ch, obj, container, C.TO_ROOM)
        act("You put $p in $P.", ch, obj, container, C.TO_CHAR)


# C: act_obj.c do_put
def do_put(ch, argument: str) -> None:
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if str_cmp(arg2, "in") or str_cmp(arg2, "on"):
        argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Put what in what?\n\r", ch)
        return
    if _is_all(arg2):
        send_to_char("You can't do that.\n\r", ch)
        return
    container = get_obj_here(ch, arg2)
    if container is None:
        act("I see no $T here.", ch, None, arg2, C.TO_CHAR)
        return
    if container.item_type != C.ITEM_CONTAINER:
        send_to_char("That's not a container.\n\r", ch)
        return
    if container.value[1] & C.CONT_CLOSED:
        act("The $d is closed.", ch, None, container.name, C.TO_CHAR)
        return
    pit = container.index.vnum == C.OBJ_VNUM_PIT
    if not _is_all(arg1):  # "'put obj container'"
        obj = get_obj_carry(ch, arg1, ch)
        if obj is None:
            send_to_char("You do not have that item.\n\r", ch)
            return
        if obj is container:
            send_to_char("You can't fold it into itself.\n\r", ch)
            return
        if not can_drop_obj(ch, obj):
            send_to_char("You can't let go of it.\n\r", ch)
            return
        if weight_mult(obj) != 100:
            send_to_char("You have a feeling that would be a bad idea.\n\r", ch)
            return
        if (get_obj_weight(obj) + get_true_weight(container) > container.value[0] * 10
                or get_obj_weight(obj) > container.value[3] * 10):
            send_to_char("It won't fit.\n\r", ch)
            return
        if pit and not can_wear(container, C.ITEM_TAKE):
            if obj.timer:
                obj.extra_flags |= C.ITEM_HAD_TIMER
            else:
                obj.timer = number_range(100, 200)
        obj_from_char(obj)
        obj_to_obj(obj, container)
        _put_messages(ch, obj, container)
        return
    # "'put all container' or 'put all.obj container'"
    for obj in list(ch.carrying):
        if ((len(arg1) == 3 or is_name(arg1[4:], obj.name)) and can_see_obj(ch, obj)
                and weight_mult(obj) == 100 and obj.wear_loc == C.WEAR_NONE and obj is not container
                and can_drop_obj(ch, obj)
                and get_obj_weight(obj) + get_true_weight(container) <= container.value[0] * 10
                and get_obj_weight(obj) < container.value[3] * 10):  # sic: < here, > for one object (#57)
            if pit and not can_wear(obj, C.ITEM_TAKE):  # sic: the object's take flag, not the pit's (#58)
                if obj.timer:
                    obj.extra_flags |= C.ITEM_HAD_TIMER
                else:
                    obj.timer = number_range(100, 200)
            obj_from_char(obj)
            obj_to_obj(obj, container)
            _put_messages(ch, obj, container)
    # sic: nothing matched says nothing (#57)


def _dissolves(ch, obj) -> None:
    act("$n drops $p.", ch, obj, None, C.TO_ROOM)
    act("You drop $p.", ch, obj, None, C.TO_CHAR)
    if is_obj_stat(obj, C.ITEM_MELT_DROP):
        act("$p dissolves into smoke.", ch, obj, None, C.TO_ROOM)
        act("$p dissolves into smoke.", ch, obj, None, C.TO_CHAR)
        extract_obj(game_module.current, obj)


_COIN_WORDS = ("coins", "coin", "gold", "silver")


# C: act_obj.c do_drop
def do_drop(ch, argument: str) -> None:
    argument, arg = one_argument(argument)
    if arg == "":
        send_to_char("Drop what?\n\r", ch)
        return
    if is_number(arg):  # "'drop NNNN coins'"
        gold = silver = 0
        amount = atoi(arg)
        argument, arg = one_argument(argument)
        if amount <= 0 or not any(str_cmp(arg, w) for w in _COIN_WORDS):
            send_to_char("Sorry, you can't do that.\n\r", ch)
            return
        if str_cmp(arg, "coins") or str_cmp(arg, "coin") or str_cmp(arg, "silver"):
            if ch.silver < amount:
                send_to_char("You don't have that much silver.\n\r", ch)
                return
            ch.silver -= amount
            silver = amount
        else:
            if ch.gold < amount:
                send_to_char("You don't have that much gold.\n\r", ch)
                return
            ch.gold -= amount
            gold = amount
        game = game_module.current
        for obj in list(ch.in_room.contents):
            vnum = obj.index.vnum
            if vnum == C.OBJ_VNUM_SILVER_ONE:
                silver += 1
            elif vnum == C.OBJ_VNUM_GOLD_ONE:
                gold += 1
            elif vnum == C.OBJ_VNUM_SILVER_SOME:
                silver += obj.value[0]
            elif vnum == C.OBJ_VNUM_GOLD_SOME:
                gold += obj.value[1]
            elif vnum == C.OBJ_VNUM_COINS:
                silver += obj.value[0]
                gold += obj.value[1]
            else:
                continue
            extract_obj(game, obj)
        obj_to_room(create_money(game, int32(gold), int32(silver)), ch.in_room)
        act("$n drops some coins.", ch, None, None, C.TO_ROOM)
        send_to_char("OK.\n\r", ch)
        return
    if not _is_all(arg):  # "'drop obj'"
        obj = get_obj_carry(ch, arg, ch)
        if obj is None:
            send_to_char("You do not have that item.\n\r", ch)
            return
        if not can_drop_obj(ch, obj):
            send_to_char("You can't let go of it.\n\r", ch)
            return
        obj_from_char(obj)
        obj_to_room(obj, ch.in_room)
        _dissolves(ch, obj)
        return
    # "'drop all' or 'drop all.obj'"
    found = False
    for obj in list(ch.carrying):
        if ((len(arg) == 3 or is_name(arg[4:], obj.name)) and can_see_obj(ch, obj)
                and obj.wear_loc == C.WEAR_NONE and can_drop_obj(ch, obj)):
            found = True
            obj_from_char(obj)
            obj_to_room(obj, ch.in_room)
            _dissolves(ch, obj)
    if not found:
        if len(arg) == 3:
            act("You are not carrying anything.", ch, None, arg, C.TO_CHAR)
        else:
            act("You are not carrying any $T.", ch, None, arg[4:], C.TO_CHAR)


# C: act_obj.c do_give
def do_give(ch, argument: str) -> None:
    from charm.systems.mobprog import has_trigger, mp_bribe_trigger, mp_give_trigger

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Give what to whom?\n\r", ch)
        return
    if is_number(arg1):  # "'give NNNN coins victim'"
        amount = atoi(arg1)
        if amount <= 0 or not any(str_cmp(arg2, w) for w in _COIN_WORDS):
            send_to_char("Sorry, you can't do that.\n\r", ch)
            return
        silver = not str_cmp(arg2, "gold")
        argument, arg2 = one_argument(argument)
        if arg2 == "":
            send_to_char("Give what to whom?\n\r", ch)
            return
        victim = get_char_room(ch, arg2)
        if victim is None:
            send_to_char("They aren't here.\n\r", ch)
            return
        if (not silver and ch.gold < amount) or (silver and ch.silver < amount):
            send_to_char("You haven't got that much.\n\r", ch)
            return
        if silver:
            ch.silver -= amount
            victim.silver += amount
        else:
            ch.gold -= amount
            victim.gold += amount
        coin = "silver" if silver else "gold"
        act("$n gives you %d %s." % (amount, coin), ch, None, victim, C.TO_VICT)
        act("$n gives $N some coins.", ch, None, victim, C.TO_NOTVICT)
        act("You give $N %d %s." % (amount, coin), ch, None, victim, C.TO_CHAR)
        if victim.is_npc and has_trigger(victim, C.TRIG_BRIBE):  # "Bribe trigger"
            mp_bribe_trigger(victim, ch, amount if silver else int32(amount * 100))
        if victim.is_npc and victim.act & C.ACT_IS_CHANGER:
            # 95 * amount wraps as the C's int does
            change = c_div(c_div(int32(95 * amount), 100), 100) if silver else int32(95 * amount)
            if not silver and change > victim.silver:
                victim.silver += change
            if silver and change > victim.gold:
                victim.gold += change
            if change < 1 and can_see(victim, ch):
                act("$n tells you 'I'm sorry, you did not give me enough to change.'", victim, None, ch, C.TO_VICT)
                ch.reply = victim
                do_give(victim, "%d %s %s" % (amount, coin, ch.name))
            elif can_see(victim, ch):
                do_give(victim, "%d %s %s" % (change, "gold" if silver else "silver", ch.name))
                if silver:
                    do_give(victim, "%d silver %s" % (int32(c_div(int32(95 * amount), 100) - change * 100), ch.name))
                act("$n tells you 'Thank you, come again.'", victim, None, ch, C.TO_VICT)
                ch.reply = victim
        return
    obj = get_obj_carry(ch, arg1, ch)
    if obj is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    if obj.wear_loc != C.WEAR_NONE:
        send_to_char("You must remove it first.\n\r", ch)
        return
    victim = get_char_room(ch, arg2)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.is_npc and victim.index.shop is not None:
        act("$N tells you 'Sorry, you'll have to sell that.'", ch, None, victim, C.TO_CHAR)
        ch.reply = victim
        return
    if not can_drop_obj(ch, obj):
        send_to_char("You can't let go of it.\n\r", ch)
        return
    if victim.carry_number + get_obj_number(obj) > can_carry_n(victim):
        act("$N has $S hands full.", ch, None, victim, C.TO_CHAR)
        return
    if get_carry_weight(victim) + get_obj_weight(obj) > can_carry_w(victim):
        act("$N can't carry that much weight.", ch, None, victim, C.TO_CHAR)
        return
    if not can_see_obj(victim, obj):
        act("$N can't see it.", ch, None, victim, C.TO_CHAR)
        return
    obj_from_char(obj)
    obj_to_char(obj, victim)
    MOB_TRIGGER[0] = False
    act("$n gives $p to $N.", ch, obj, victim, C.TO_NOTVICT)
    act("$n gives you $p.", ch, obj, victim, C.TO_VICT)
    act("You give $p to $N.", ch, obj, victim, C.TO_CHAR)
    MOB_TRIGGER[0] = True
    if victim.is_npc and has_trigger(victim, C.TRIG_GIVE):  # "Give trigger"
        mp_give_trigger(victim, ch, obj)


# C: act_obj.c remove_obj
def remove_obj(ch, i_wear: int, f_replace: bool) -> bool:
    """"Remove an object"."""
    obj = get_eq_char(ch, i_wear)
    if obj is None:
        return True
    if not f_replace:
        return False
    if obj.extra_flags & C.ITEM_NOREMOVE:
        act("You can't remove $p.", ch, obj, None, C.TO_CHAR)
        return False
    unequip_char(ch, obj)
    act("$n stops using $p.", ch, obj, None, C.TO_ROOM)
    act("You stop using $p.", ch, obj, None, C.TO_CHAR)
    return True


# wear_obj's places that take one item: (wear flag, wear location, to the room, to the wearer).
_ONE_PLACE = (
    (C.ITEM_WEAR_BODY, C.WEAR_BODY, "$n wears $p on $s torso.", "You wear $p on your torso."),
    (C.ITEM_WEAR_HEAD, C.WEAR_HEAD, "$n wears $p on $s head.", "You wear $p on your head."),
    (C.ITEM_WEAR_LEGS, C.WEAR_LEGS, "$n wears $p on $s legs.", "You wear $p on your legs."),
    (C.ITEM_WEAR_FEET, C.WEAR_FEET, "$n wears $p on $s feet.", "You wear $p on your feet."),
    (C.ITEM_WEAR_HANDS, C.WEAR_HANDS, "$n wears $p on $s hands.", "You wear $p on your hands."),
    (C.ITEM_WEAR_ARMS, C.WEAR_ARMS, "$n wears $p on $s arms.", "You wear $p on your arms."),
    (C.ITEM_WEAR_ABOUT, C.WEAR_ABOUT, "$n wears $p about $s torso.", "You wear $p about your torso."),
    (C.ITEM_WEAR_WAIST, C.WEAR_WAIST, "$n wears $p about $s waist.", "You wear $p about your waist."),
)

# The places that take two: (wear flag, first, second, the bug() line, the refusal, then (to the room, to the
# wearer) for the first and for the second).
_TWO_PLACES = {
    C.ITEM_WEAR_FINGER: (C.WEAR_FINGER_L, C.WEAR_FINGER_R, "Wear_obj: no free finger.",
                         "You already wear two rings.\n\r",
                         ("$n wears $p on $s left finger.", "You wear $p on your left finger."),
                         ("$n wears $p on $s right finger.", "You wear $p on your right finger.")),
    C.ITEM_WEAR_NECK: (C.WEAR_NECK_1, C.WEAR_NECK_2, "Wear_obj: no free neck.",
                       "You already wear two neck items.\n\r",
                       ("$n wears $p around $s neck.", "You wear $p around your neck."),
                       ("$n wears $p around $s neck.", "You wear $p around your neck.")),
    C.ITEM_WEAR_WRIST: (C.WEAR_WRIST_L, C.WEAR_WRIST_R, "Wear_obj: no free wrist.",
                        "You already wear two wrist items.\n\r",
                        ("$n wears $p around $s left wrist.", "You wear $p around your left wrist."),
                        ("$n wears $p around $s right wrist.", "You wear $p around your right wrist.")),
}


def _wear_two(ch, obj, f_replace: bool, part: int) -> None:
    from charm.core.log import bug

    first, second, bug_line, refusal, msg_first, msg_second = _TWO_PLACES[part]
    if (get_eq_char(ch, first) is not None and get_eq_char(ch, second) is not None
            and not remove_obj(ch, first, f_replace) and not remove_obj(ch, second, f_replace)):
        return
    for loc, (to_room, to_char) in ((first, msg_first), (second, msg_second)):
        if get_eq_char(ch, loc) is None:
            act(to_room, ch, obj, None, C.TO_ROOM)
            act(to_char, ch, obj, None, C.TO_CHAR)
            equip_char(ch, obj, loc)
            return
    bug(bug_line, 0)
    send_to_char(refusal, ch)


# get_weapon_skill's thresholds for wield's message: (more than this, the message); the last is the rest.
_WIELD_SKILL = (
    (99, "$p feels like a part of you!"), (85, "You feel quite confident with $p."),
    (70, "You are skilled with $p."), (50, "Your skill with $p is adequate."),
    (25, "$p feels a little clumsy in your hands."), (1, "You fumble and almost drop $p."),
    (-1, "You don't even know which end is up on $p."),
)


# C: act_obj.c wear_obj
def wear_obj(ch, obj, f_replace: bool) -> None:
    """"Wear one object. Optional replacement of existing objects. Big repetitive code, ick."."""
    if ch.level < obj.level:
        send_to_char("You must be level %d to use this object.\n\r" % obj.level, ch)
        act("$n tries to use $p, but is too inexperienced.", ch, obj, None, C.TO_ROOM)
        return
    if obj.item_type == C.ITEM_LIGHT:
        if not remove_obj(ch, C.WEAR_LIGHT, f_replace):
            return
        act("$n lights $p and holds it.", ch, obj, None, C.TO_ROOM)
        act("You light $p and hold it.", ch, obj, None, C.TO_CHAR)
        equip_char(ch, obj, C.WEAR_LIGHT)
        return
    for part in (C.ITEM_WEAR_FINGER, C.ITEM_WEAR_NECK):
        if can_wear(obj, part):
            _wear_two(ch, obj, f_replace, part)
            return
    for part, loc, to_room, to_char in _ONE_PLACE:
        if can_wear(obj, part):
            if not remove_obj(ch, loc, f_replace):
                return
            act(to_room, ch, obj, None, C.TO_ROOM)
            act(to_char, ch, obj, None, C.TO_CHAR)
            equip_char(ch, obj, loc)
            return
    if can_wear(obj, C.ITEM_WEAR_WRIST):
        _wear_two(ch, obj, f_replace, C.ITEM_WEAR_WRIST)
        return
    if can_wear(obj, C.ITEM_WEAR_SHIELD):
        if not remove_obj(ch, C.WEAR_SHIELD, f_replace):
            return
        weapon = get_eq_char(ch, C.WEAR_WIELD)
        if weapon is not None and ch.size < C.SIZE_LARGE and weapon.value[4] & C.WEAPON_TWO_HANDS:
            send_to_char("Your hands are tied up with your weapon!\n\r", ch)
            return
        act("$n wears $p as a shield.", ch, obj, None, C.TO_ROOM)
        act("You wear $p as a shield.", ch, obj, None, C.TO_CHAR)
        equip_char(ch, obj, C.WEAR_SHIELD)
        return
    if can_wear(obj, C.ITEM_WIELD):
        if not remove_obj(ch, C.WEAR_WIELD, f_replace):
            return
        if not ch.is_npc and get_obj_weight(obj) > STR_APP[get_curr_stat(ch, C.STAT_STR)].wield * 10:
            send_to_char("It is too heavy for you to wield.\n\r", ch)
            return
        if (not ch.is_npc and ch.size < C.SIZE_LARGE and obj.value[4] & C.WEAPON_TWO_HANDS
                and get_eq_char(ch, C.WEAR_SHIELD) is not None):
            send_to_char("You need two hands free for that weapon.\n\r", ch)
            return
        act("$n wields $p.", ch, obj, None, C.TO_ROOM)
        act("You wield $p.", ch, obj, None, C.TO_CHAR)
        equip_char(ch, obj, C.WEAR_WIELD)
        sn = get_weapon_sn(ch)
        if sn == GSN["gsn_hand_to_hand"]:
            return
        skill = get_weapon_skill(ch, sn)
        act(next(msg for floor, msg in _WIELD_SKILL if skill > floor), ch, obj, None, C.TO_CHAR)
        return
    if can_wear(obj, C.ITEM_HOLD):
        if not remove_obj(ch, C.WEAR_HOLD, f_replace):
            return
        act("$n holds $p in $s hand.", ch, obj, None, C.TO_ROOM)
        act("You hold $p in your hand.", ch, obj, None, C.TO_CHAR)
        equip_char(ch, obj, C.WEAR_HOLD)
        return
    if can_wear(obj, C.ITEM_WEAR_FLOAT):
        if not remove_obj(ch, C.WEAR_FLOAT, f_replace):
            return
        act("$n releases $p to float next to $m.", ch, obj, None, C.TO_ROOM)
        act("You release $p and it floats next to you.", ch, obj, None, C.TO_CHAR)
        equip_char(ch, obj, C.WEAR_FLOAT)
        return
    if f_replace:
        send_to_char("You can't wear, wield, or hold that.\n\r", ch)


# C: act_obj.c do_wear
def do_wear(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Wear, wield, or hold what?\n\r", ch)
        return
    if str_cmp(arg, "all"):
        for obj in list(ch.carrying):
            if obj.wear_loc == C.WEAR_NONE and can_see_obj(ch, obj):
                wear_obj(ch, obj, False)
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    wear_obj(ch, obj, True)


# C: act_obj.c do_remove
def do_remove(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Remove what?\n\r", ch)
        return
    obj = get_obj_wear(ch, arg)
    if obj is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    remove_obj(ch, obj.wear_loc, True)


# -- food, drink and poison ---------------------------------------------------------------------------------------

def _liquid(n: int, where: str):
    """liq_table[n]. The C table ends in a row of NULLs and has no bounds check, so a number past the liquids (or
    below 0) reads a NULL name or memory past the table."""
    if n < 0 or n >= len(LIQ_TABLE):
        raise CWouldCrash(f"act_obj.c {where}: liquid {n} is past liq_table")
    return LIQ_TABLE[n]


def _attack_damage(n: int) -> int:
    """attack_table[n].damage, with n >= 0: the closing row of NULLs has damage 0, and past it is past the table."""
    if n == len(ATTACK_TABLE):
        return 0
    if n > len(ATTACK_TABLE):
        raise CWouldCrash(f"act_obj.c do_envenom: attack {n} is past attack_table")
    return ATTACK_TABLE[n].damage


def _wait(ch, sn_name: str) -> None:
    from charm.commands.comm import wait_state

    wait_state(ch, SKILL_TABLE[GSN[sn_name]].beats)


# C: act_obj.c do_envenom
def do_envenom(ch, argument: str) -> None:
    """"for poisoning weapons and food/drink"."""
    from charm.systems.skills import check_improve

    if argument == "":  # "find out what"
        send_to_char("Envenom what item?\n\r", ch)
        return
    obj = get_obj_list(ch, argument, ch.carrying)
    if obj is None:
        send_to_char("You don't have that item.\n\r", ch)
        return
    gsn = GSN["gsn_envenom"]
    skill = get_skill(ch, gsn)
    if skill < 1:
        send_to_char("Are you crazy? You'd poison yourself!\n\r", ch)
        return
    if obj.item_type in (C.ITEM_FOOD, C.ITEM_DRINK_CON):
        if is_obj_stat(obj, C.ITEM_BLESS) or is_obj_stat(obj, C.ITEM_BURN_PROOF):
            act("You fail to poison $p.", ch, obj, None, C.TO_CHAR)
            return
        if number_percent() < skill:  # "success!"
            act("$n treats $p with deadly poison.", ch, obj, None, C.TO_ROOM)
            act("You treat $p with deadly poison.", ch, obj, None, C.TO_CHAR)
            if not obj.value[3]:
                obj.value[3] = 1
                check_improve(ch, gsn, True, 4)
            _wait(ch, "gsn_envenom")
            return
        act("You fail to poison $p.", ch, obj, None, C.TO_CHAR)
        if not obj.value[3]:
            check_improve(ch, gsn, False, 4)
        _wait(ch, "gsn_envenom")
        return
    if obj.item_type == C.ITEM_WEAPON:
        if (obj.value[4] & (C.WEAPON_FLAMING | C.WEAPON_FROST | C.WEAPON_VAMPIRIC | C.WEAPON_SHARP | C.WEAPON_VORPAL
                            | C.WEAPON_SHOCKING)
                or is_obj_stat(obj, C.ITEM_BLESS) or is_obj_stat(obj, C.ITEM_BURN_PROOF)):
            act("You can't seem to envenom $p.", ch, obj, None, C.TO_CHAR)
            return
        if obj.value[3] < 0 or _attack_damage(obj.value[3]) == C.DAM_BASH:
            send_to_char("You can only envenom edged weapons.\n\r", ch)
            return
        if obj.value[4] & C.WEAPON_POISON:
            act("$p is already envenomed.", ch, obj, None, C.TO_CHAR)
            return
        percent = number_percent()
        if percent < skill:
            affect_to_obj(obj, Affect(where=C.TO_WEAPON, type=GSN["gsn_poison"],
                                      level=c_div(ch.level * percent, 100),
                                      duration=c_div(c_div(ch.level, 2) * percent, 100), location=0, modifier=0,
                                      bitvector=C.WEAPON_POISON))
            act("$n coats $p with deadly venom.", ch, obj, None, C.TO_ROOM)
            act("You coat $p with venom.", ch, obj, None, C.TO_CHAR)
            check_improve(ch, gsn, True, 3)
            _wait(ch, "gsn_envenom")
            return
        act("You fail to envenom $p.", ch, obj, None, C.TO_CHAR)
        check_improve(ch, gsn, False, 3)
        _wait(ch, "gsn_envenom")
        return
    act("You can't poison $p.", ch, obj, None, C.TO_CHAR)


# C: act_obj.c do_fill
def do_fill(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Fill what?\n\r", ch)
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    fountain = next((f for f in ch.in_room.contents if f.item_type == C.ITEM_FOUNTAIN), None)
    if fountain is None:
        send_to_char("There is no fountain here!\n\r", ch)
        return
    if obj.item_type != C.ITEM_DRINK_CON:
        send_to_char("You can't fill that.\n\r", ch)
        return
    if obj.value[1] != 0 and obj.value[2] != fountain.value[2]:
        send_to_char("There is already another liquid in it.\n\r", ch)
        return
    if obj.value[1] >= obj.value[0]:
        send_to_char("Your container is full.\n\r", ch)
        return
    name = _liquid(fountain.value[2], "do_fill").liq_name
    act("You fill $p with %s from $P." % name, ch, obj, fountain, C.TO_CHAR)
    act("$n fills $p with %s from $P." % name, ch, obj, fountain, C.TO_ROOM)
    obj.value[2] = fountain.value[2]
    obj.value[1] = obj.value[0]


# C: act_obj.c do_pour
def do_pour(ch, argument: str) -> None:
    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        send_to_char("Pour what into what?\n\r", ch)
        return
    out = get_obj_carry(ch, arg, ch)
    if out is None:
        send_to_char("You don't have that item.\n\r", ch)
        return
    if out.item_type != C.ITEM_DRINK_CON:
        send_to_char("That's not a drink container.\n\r", ch)
        return
    if str_cmp(argument, "out"):
        if out.value[1] == 0:
            send_to_char("It's already empty.\n\r", ch)
            return
        out.value[1] = 0
        out.value[3] = 0
        name = _liquid(out.value[2], "do_pour").liq_name
        act("You invert $p, spilling %s all over the ground." % name, ch, out, None, C.TO_CHAR)
        act("$n inverts $p, spilling %s all over the ground." % name, ch, out, None, C.TO_ROOM)
        return
    vch = None
    into = get_obj_here(ch, argument)
    if into is None:
        vch = get_char_room(ch, argument)
        if vch is None:
            send_to_char("Pour into what?\n\r", ch)
            return
        into = get_eq_char(vch, C.WEAR_HOLD)
        if into is None:
            send_to_char("They aren't holding anything.", ch)  # sic: no line end (#60)
            return
    if into.item_type != C.ITEM_DRINK_CON:
        send_to_char("You can only pour into other drink containers.\n\r", ch)
        return
    if into is out:
        send_to_char("You cannot change the laws of physics!\n\r", ch)
        return
    if into.value[1] != 0 and into.value[2] != out.value[2]:
        send_to_char("They don't hold the same liquid.\n\r", ch)
        return
    if out.value[1] == 0:
        act("There's nothing in $p to pour.", ch, out, None, C.TO_CHAR)
        return
    if into.value[1] >= into.value[0]:
        act("$p is already filled to the top.", ch, into, None, C.TO_CHAR)
        return
    amount = min(out.value[1], into.value[0] - into.value[1])
    into.value[1] += amount
    out.value[1] -= amount
    into.value[2] = out.value[2]
    name = _liquid(out.value[2], "do_pour").liq_name
    if vch is None:
        act("You pour %s from $p into $P." % name, ch, out, into, C.TO_CHAR)
        act("$n pours %s from $p into $P." % name, ch, out, into, C.TO_ROOM)
    else:
        act("You pour some %s for $N." % name, ch, None, vch, C.TO_CHAR)
        act("$n pours you some %s." % name, ch, None, vch, C.TO_VICT)
        act("$n pours some %s for $N." % name, ch, None, vch, C.TO_NOTVICT)


def _poisoned(ch, level: int, duration: int) -> None:
    act("$n chokes and gags.", ch, None, None, C.TO_ROOM)
    send_to_char("You choke and gag.\n\r", ch)
    affect_join(ch, Affect(where=C.TO_AFFECTS, type=GSN["gsn_poison"], level=number_fuzzy(level),
                           duration=duration, location=C.APPLY_NONE, modifier=0, bitvector=C.AFF_POISON))


# C: act_obj.c do_drink
def do_drink(ch, argument: str) -> None:
    from charm.systems.update import gain_condition

    _, arg = one_argument(argument)
    if arg == "":
        obj = next((o for o in ch.in_room.contents if o.item_type == C.ITEM_FOUNTAIN), None)
        if obj is None:
            send_to_char("Drink what?\n\r", ch)
            return
    else:
        obj = get_obj_here(ch, arg)
        if obj is None:
            send_to_char("You can't find it.\n\r", ch)
            return
    if not ch.is_npc and ch.pcdata.condition[C.COND_DRUNK] > 10:
        send_to_char("You fail to reach your mouth.  *Hic*\n\r", ch)
        return
    if obj.item_type == C.ITEM_FOUNTAIN:
        liquid = obj.value[2]
        if liquid < 0:
            bug("Do_drink: bad liquid number %d.", liquid)
            liquid = obj.value[2] = 0
        amount = _liquid(liquid, "do_drink").liq_affect[4] * 3
    elif obj.item_type == C.ITEM_DRINK_CON:
        if obj.value[1] <= 0:
            send_to_char("It is already empty.\n\r", ch)
            return
        liquid = obj.value[2]
        if liquid < 0:
            bug("Do_drink: bad liquid number %d.", liquid)
            liquid = obj.value[2] = 0
        amount = min(_liquid(liquid, "do_drink").liq_affect[4], obj.value[1])
    else:
        send_to_char("You can't drink from that.\n\r", ch)
        return
    if not ch.is_npc and not is_immortal(ch) and ch.pcdata.condition[C.COND_FULL] > 45:
        send_to_char("You're too full to drink more.\n\r", ch)
        return
    liq = LIQ_TABLE[liquid]
    act("$n drinks $T from $p.", ch, obj, liq.liq_name, C.TO_ROOM)
    act("You drink $T from $p.", ch, obj, liq.liq_name, C.TO_CHAR)
    gain_condition(ch, C.COND_DRUNK, c_div(amount * liq.liq_affect[C.COND_DRUNK], 36))
    gain_condition(ch, C.COND_FULL, c_div(amount * liq.liq_affect[C.COND_FULL], 4))
    gain_condition(ch, C.COND_THIRST, c_div(amount * liq.liq_affect[C.COND_THIRST], 10))
    gain_condition(ch, C.COND_HUNGER, c_div(amount * liq.liq_affect[C.COND_HUNGER], 2))
    if not ch.is_npc and ch.pcdata.condition[C.COND_DRUNK] > 10:
        send_to_char("You feel drunk.\n\r", ch)
    if not ch.is_npc and ch.pcdata.condition[C.COND_FULL] > 40:
        send_to_char("You are full.\n\r", ch)
    if not ch.is_npc and ch.pcdata.condition[C.COND_THIRST] > 40:
        send_to_char("Your thirst is quenched.\n\r", ch)
    if obj.value[3] != 0:  # "The drink was poisoned !"
        _poisoned(ch, amount, 3 * amount)
    if obj.value[0] > 0:
        obj.value[1] -= amount


# C: act_obj.c do_eat
def do_eat(ch, argument: str) -> None:
    from charm.systems.magic import obj_cast_spell
    from charm.systems.update import gain_condition

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Eat what?\n\r", ch)
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    if not is_immortal(ch):
        if obj.item_type not in (C.ITEM_FOOD, C.ITEM_PILL):
            send_to_char("That's not edible.\n\r", ch)
            return
        if not ch.is_npc and ch.pcdata.condition[C.COND_FULL] > 40:
            send_to_char("You are too full to eat more.\n\r", ch)
            return
    act("$n eats $p.", ch, obj, None, C.TO_ROOM)
    act("You eat $p.", ch, obj, None, C.TO_CHAR)
    if obj.item_type == C.ITEM_FOOD:
        if not ch.is_npc:
            condition = ch.pcdata.condition[C.COND_HUNGER]
            gain_condition(ch, C.COND_FULL, obj.value[0])
            gain_condition(ch, C.COND_HUNGER, obj.value[1])
            if condition == 0 and ch.pcdata.condition[C.COND_HUNGER] > 0:
                send_to_char("You are no longer hungry.\n\r", ch)
            elif ch.pcdata.condition[C.COND_FULL] > 40:
                send_to_char("You are full.\n\r", ch)
        if obj.value[3] != 0:  # "The food was poisoned!"
            _poisoned(ch, obj.value[0], 2 * obj.value[0])
    elif obj.item_type == C.ITEM_PILL:
        for sn in obj.value[1:4]:
            obj_cast_spell(sn, obj.value[0], ch, ch, None)
    extract_obj(game_module.current, obj)


# -- sacrifice and steal ------------------------------------------------------------------------------------------

# C: act_obj.c do_sacrifice
def do_sacrifice(ch, argument: str) -> None:
    from charm.commands.comm import do_split, is_same_group
    from charm.net.wiznet import wiznet

    _, arg = one_argument(argument)
    if arg == "" or str_cmp(arg, ch.name):
        act("$n offers $mself to Mota, who graciously declines.", ch, None, None, C.TO_ROOM)
        send_to_char("Mota appreciates your offer and may accept it later.\n\r", ch)
        return
    obj = get_obj_list(ch, arg, ch.in_room.contents)
    if obj is None:
        send_to_char("You can't find it.\n\r", ch)
        return
    if obj.item_type == C.ITEM_CORPSE_PC and obj.contains:
        send_to_char("Mota wouldn't like that.\n\r", ch)
        return
    if not can_wear(obj, C.ITEM_TAKE) or can_wear(obj, C.ITEM_NO_SAC):
        act("$p is not an acceptable sacrifice.", ch, obj, None, C.TO_CHAR)
        return
    if obj.in_room is not None:
        for gch in obj.in_room.people:
            if gch.on is obj:
                act("$N appears to be using $p.", ch, obj, gch, C.TO_CHAR)
                return
    silver = max(1, obj.level * 3)
    if obj.item_type not in (C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC):
        silver = min(silver, obj.cost)
    if silver == 1:
        send_to_char("Mota gives you one silver coin for your sacrifice.\n\r", ch)
    else:
        send_to_char("Mota gives you %d silver coins for your sacrifice.\n\r" % silver, ch)
    ch.silver += silver
    if ch.act & C.PLR_AUTOSPLIT:  # "AUTOSPLIT code"
        # sic: charmed followers count here, though do_split leaves them out (#61)
        members = sum(1 for gch in ch.in_room.people if is_same_group(gch, ch))
        if members > 1 and silver > 1:
            do_split(ch, "%d" % silver)
    act("$n sacrifices $p to Mota.", ch, obj, None, C.TO_ROOM)
    wiznet(game_module.current, "$N sends up $p as a burnt offering.", ch, obj, C.WIZ_SACCING, 0, 0)
    extract_obj(game_module.current, obj)


_STEAL_YELLS = ("%s is a lousy thief!", "%s couldn't rob %s way out of a paper bag!", "%s tried to rob me!",
                "Keep your hands out of there, %s!")


# C: act_obj.c do_steal
def do_steal(ch, argument: str) -> None:
    from charm.commands.comm import do_yell, wait_state
    from charm.commands.move import do_wake
    from charm.net.wiznet import wiznet
    from charm.persist.player import save_char_obj
    from charm.systems.fight import is_safe, multi_hit
    from charm.systems.skills import check_improve

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Steal what from whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg2)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim is ch:
        send_to_char("That's pointless.\n\r", ch)
        return
    if is_safe(ch, victim):
        return
    if victim.is_npc and victim.position == C.POS_FIGHTING:
        send_to_char("Kill stealing is not permitted.\n\rYou'd better not -- you might get hit.\n\r", ch)
        return
    gsn = GSN["gsn_steal"]
    wait_state(ch, SKILL_TABLE[gsn].beats)
    percent = number_percent()
    if not is_awake(victim):
        percent -= 10
    elif not can_see(victim, ch):
        percent += 25
    else:
        percent += 50
    if (((ch.level + 7 < victim.level or ch.level - 7 > victim.level) and not victim.is_npc and not ch.is_npc)
            or (not ch.is_npc and percent > get_skill(ch, gsn))
            or (not ch.is_npc and not is_clan(ch))):
        send_to_char("Oops.\n\r", ch)  # "Failure."
        affect_strip(ch, GSN["gsn_sneak"])
        ch.affected_by &= ~C.AFF_SNEAK
        # sic: act adds its own line end, so these send an empty line after them (#60)
        act("$n tried to steal from you.\n\r", ch, None, victim, C.TO_VICT)
        act("$n tried to steal from $N.\n\r", ch, None, victim, C.TO_NOTVICT)
        pick = number_range(0, 3)
        if pick == 1:
            buf = _STEAL_YELLS[1] % (ch.name, "her" if ch.sex == 2 else "his")  # format: sprintf
        else:
            buf = _STEAL_YELLS[pick] % ch.name  # format: sprintf
        if not is_awake(victim):
            do_wake(victim, "")
        if is_awake(victim):
            do_yell(victim, buf)
        if not ch.is_npc:
            if victim.is_npc:
                check_improve(ch, gsn, False, 2)
                multi_hit(victim, ch, C.TYPE_UNDEFINED)
            else:
                wiznet(game_module.current, "$N tried to steal from %s." % victim.name, ch, None, C.WIZ_FLAGS, 0,
                       0)
                if not ch.act & C.PLR_THIEF:
                    ch.act |= C.PLR_THIEF
                    send_to_char("*** You are now a THIEF!! ***\n\r", ch)
                    save_char_obj(game_module.current, ch)
        return
    if any(str_cmp(arg1, w) for w in ("coin", "coins", "gold", "silver")):
        gold = c_div(victim.gold * number_range(1, ch.level), C.MAX_LEVEL)
        silver = c_div(victim.silver * number_range(1, ch.level), C.MAX_LEVEL)
        if gold <= 0 and silver <= 0:
            send_to_char("You couldn't get any coins.\n\r", ch)
            return
        ch.gold += gold
        ch.silver += silver
        victim.silver -= silver
        victim.gold -= gold
        if silver <= 0:
            send_to_char("Bingo!  You got %d gold coins.\n\r" % gold, ch)
        elif gold <= 0:
            send_to_char("Bingo!  You got %d silver coins.\n\r" % silver, ch)
        else:
            send_to_char("Bingo!  You got %d silver and %d gold coins.\n\r" % (silver, gold), ch)
        check_improve(ch, gsn, True, 2)
        return
    obj = get_obj_carry(victim, arg1, ch)
    if obj is None:
        send_to_char("You can't find it.\n\r", ch)
        return
    if not can_drop_obj(ch, obj) or obj.extra_flags & C.ITEM_INVENTORY or obj.level > ch.level:
        send_to_char("You can't pry it away.\n\r", ch)
        return
    if ch.carry_number + get_obj_number(obj) > can_carry_n(ch):
        send_to_char("You have your hands full.\n\r", ch)
        return
    if ch.carry_weight + get_obj_weight(obj) > can_carry_w(ch):
        send_to_char("You can't carry that much weight.\n\r", ch)
        return
    obj_from_char(obj)
    obj_to_char(obj, ch)
    act("You pocket $p.", ch, obj, None, C.TO_CHAR)
    check_improve(ch, gsn, True, 2)
    send_to_char("Got it!\n\r", ch)


# -- the magic items ----------------------------------------------------------------------------------------------

# C: act_obj.c do_quaff
def do_quaff(ch, argument: str) -> None:
    from charm.systems.magic import obj_cast_spell

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Quaff what?\n\r", ch)
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        send_to_char("You do not have that potion.\n\r", ch)
        return
    if obj.item_type != C.ITEM_POTION:
        send_to_char("You can quaff only potions.\n\r", ch)
        return
    if ch.level < obj.level:
        send_to_char("This liquid is too powerful for you to drink.\n\r", ch)
        return
    act("$n quaffs $p.", ch, obj, None, C.TO_ROOM)
    act("You quaff $p.", ch, obj, None, C.TO_CHAR)
    for sn in obj.value[1:4]:
        obj_cast_spell(sn, obj.value[0], ch, ch, None)
    extract_obj(game_module.current, obj)


def _invoke_skill(ch, gsn_name: str) -> int:
    """The magic items' chance: 20 + skill * 4 / 5."""
    return 20 + c_div(get_skill(ch, GSN[gsn_name]) * 4, 5)


# C: act_obj.c do_recite
def do_recite(ch, argument: str) -> None:
    from charm.systems.magic import obj_cast_spell
    from charm.systems.skills import check_improve

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    scroll = get_obj_carry(ch, arg1, ch)
    if scroll is None:
        send_to_char("You do not have that scroll.\n\r", ch)
        return
    if scroll.item_type != C.ITEM_SCROLL:
        send_to_char("You can recite only scrolls.\n\r", ch)
        return
    if ch.level < scroll.level:
        send_to_char("This scroll is too complex for you to comprehend.\n\r", ch)
        return
    obj = None
    if arg2 == "":
        victim = ch
    else:
        victim = get_char_room(ch, arg2)
        if victim is None:
            obj = get_obj_here(ch, arg2)
            if obj is None:
                send_to_char("You can't find it.\n\r", ch)
                return
    act("$n recites $p.", ch, scroll, None, C.TO_ROOM)
    act("You recite $p.", ch, scroll, None, C.TO_CHAR)
    gsn = GSN["gsn_scrolls"]
    if number_percent() >= _invoke_skill(ch, "gsn_scrolls"):
        send_to_char("You mispronounce a syllable.\n\r", ch)
        check_improve(ch, gsn, False, 2)
    else:
        for sn in scroll.value[1:4]:
            obj_cast_spell(sn, scroll.value[0], ch, victim, obj)
        check_improve(ch, gsn, True, 2)
    extract_obj(game_module.current, scroll)


# C: act_obj.c do_brandish
def do_brandish(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.systems.magic import obj_cast_spell, spell_fun
    from charm.systems.skills import check_improve

    staff = get_eq_char(ch, C.WEAR_HOLD)
    if staff is None:
        send_to_char("You hold nothing in your hand.\n\r", ch)
        return
    if staff.item_type != C.ITEM_STAFF:
        send_to_char("You can brandish only with a staff.\n\r", ch)
        return
    sn = staff.value[3]
    if sn < 0 or sn >= C.MAX_SKILL or spell_fun(sn) is None:
        bug("Do_brandish: bad sn %d.", sn)
        return
    wait_state(ch, 2 * C.PULSE_VIOLENCE)
    gsn = GSN["gsn_staves"]
    if staff.value[2] > 0:
        act("$n brandishes $p.", ch, staff, None, C.TO_ROOM)
        act("You brandish $p.", ch, staff, None, C.TO_CHAR)
        if ch.level < staff.level or number_percent() >= _invoke_skill(ch, "gsn_staves"):
            act("You fail to invoke $p.", ch, staff, None, C.TO_CHAR)
            act("...and nothing happens.", ch, None, None, C.TO_ROOM)
            check_improve(ch, gsn, False, 2)
        else:
            target = SKILL_TABLE[sn].target
            for vch in list(ch.in_room.people):
                if target in (C.TAR_IGNORE, C.TAR_CHAR_SELF):
                    if vch is not ch:
                        continue
                elif target == C.TAR_CHAR_OFFENSIVE:
                    if vch.is_npc if ch.is_npc else not vch.is_npc:
                        continue
                elif target == C.TAR_CHAR_DEFENSIVE:
                    if not vch.is_npc if ch.is_npc else vch.is_npc:
                        continue
                else:
                    bug("Do_brandish: bad target for sn %d.", sn)
                    return
                obj_cast_spell(staff.value[3], staff.value[0], ch, vch, None)
                check_improve(ch, gsn, True, 2)
    staff.value[2] -= 1
    if staff.value[2] <= 0:
        # sic: "Your $p" and "$n's $p" put "a burnt staff" after them (#60)
        act("$n's $p blazes bright and is gone.", ch, staff, None, C.TO_ROOM)
        act("Your $p blazes bright and is gone.", ch, staff, None, C.TO_CHAR)
        extract_obj(game_module.current, staff)


# C: act_obj.c do_zap
def do_zap(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.systems.magic import obj_cast_spell
    from charm.systems.skills import check_improve

    _, arg = one_argument(argument)
    if arg == "" and ch.fighting is None:
        send_to_char("Zap whom or what?\n\r", ch)
        return
    wand = get_eq_char(ch, C.WEAR_HOLD)
    if wand is None:
        send_to_char("You hold nothing in your hand.\n\r", ch)
        return
    if wand.item_type != C.ITEM_WAND:
        send_to_char("You can zap only with a wand.\n\r", ch)
        return
    obj = None
    if arg == "":
        if ch.fighting is None:
            send_to_char("Zap whom or what?\n\r", ch)
            return
        victim = ch.fighting
    else:
        victim = get_char_room(ch, arg)
        if victim is None:
            obj = get_obj_here(ch, arg)
            if obj is None:
                send_to_char("You can't find it.\n\r", ch)
                return
    wait_state(ch, 2 * C.PULSE_VIOLENCE)
    gsn = GSN["gsn_wands"]
    if wand.value[2] > 0:
        if victim is not None:
            act("$n zaps $N with $p.", ch, wand, victim, C.TO_NOTVICT)
            act("You zap $N with $p.", ch, wand, victim, C.TO_CHAR)
            act("$n zaps you with $p.", ch, wand, victim, C.TO_VICT)
        else:
            act("$n zaps $P with $p.", ch, wand, obj, C.TO_ROOM)
            act("You zap $P with $p.", ch, wand, obj, C.TO_CHAR)
        if ch.level < wand.level or number_percent() >= _invoke_skill(ch, "gsn_wands"):
            act("Your efforts with $p produce only smoke and sparks.", ch, wand, None, C.TO_CHAR)
            act("$n's efforts with $p produce only smoke and sparks.", ch, wand, None, C.TO_ROOM)
            check_improve(ch, gsn, False, 2)
        else:
            obj_cast_spell(wand.value[3], wand.value[0], ch, victim, obj)
            check_improve(ch, gsn, True, 2)
    wand.value[2] -= 1
    if wand.value[2] <= 0:
        # sic: "Your $p" and "$n's $p" put "a small wand" after them (#60)
        act("$n's $p explodes into fragments.", ch, wand, None, C.TO_ROOM)
        act("Your $p explodes into fragments.", ch, wand, None, C.TO_CHAR)
        extract_obj(game_module.current, wand)


# -- shops ----------------------------------------------------------------------------------------------------------

def _same_item(a, b) -> bool:
    """The shops' test for one stock line: the same prototype and short description."""
    return a.index is b.index and str_cmp(a.short_descr, b.short_descr)


# C: act_obj.c find_keeper
def find_keeper(ch):
    """"Shopping commands."."""
    from charm.commands.comm import do_say

    keeper = next((k for k in ch.in_room.people if k.is_npc and k.index.shop is not None), None)
    if keeper is None:
        send_to_char("You can't do that here.\n\r", ch)
        return None
    shop = keeper.index.shop
    # (The C's refusal of killers and thieves is commented out.)
    hour = game_module.current.time_info.hour  # "Shop hours."
    if hour < shop.open_hour:
        do_say(keeper, "Sorry, I am closed. Come back later.")
        return None
    if hour > shop.close_hour:
        do_say(keeper, "Sorry, I am closed. Come back tomorrow.")
        return None
    if not can_see(keeper, ch):  # "Invisible or hidden people."
        do_say(keeper, "I don't trade with folks I can't see.")
        return None
    return keeper


# C: act_obj.c obj_to_keeper
def obj_to_keeper(obj, ch) -> None:
    """"insert an object at the right spot for the keeper": after its duplicates, unless the keeper's are unlimited
    (ITEM_INVENTORY), when the new one is destroyed."""
    at = None
    for i, t_obj in enumerate(ch.carrying):  # "see if any duplicates are found"
        if obj.index is t_obj.index and str_cmp(obj.short_descr, t_obj.short_descr):
            if is_obj_stat(t_obj, C.ITEM_INVENTORY):  # "if this is an unlimited item, destroy the new one"
                extract_obj(game_module.current, obj)
                return
            obj.cost = t_obj.cost  # "keep it standard"
            at = i
            break
    if at is None:
        ch.carrying.insert(0, obj)
    else:
        ch.carrying.insert(at + 1, obj)
    obj.carried_by = ch
    obj.in_room = None
    obj.in_obj = None
    ch.carry_number += get_obj_number(obj)
    ch.carry_weight += get_obj_weight(obj)


# C: act_obj.c get_obj_keeper
def get_obj_keeper(ch, keeper, argument: str):
    """"get an object from a shopkeeper's list": each stock line counts once."""
    number, arg = number_argument(argument)
    count = 0
    stock = keeper.carrying
    i = 0
    while i < len(stock):
        obj = stock[i]
        if obj.wear_loc == C.WEAR_NONE and can_see_obj(keeper, obj) and can_see_obj(ch, obj) and is_name(arg, obj.name):
            count += 1
            if count == number:
                return obj
            while i + 1 < len(stock) and _same_item(stock[i], stock[i + 1]):  # "skip other objects of the same name"
                i += 1
        i += 1
    return None


# C: act_obj.c get_cost
def get_cost(keeper, obj, f_buy: bool) -> int:
    if obj is None or keeper.index.shop is None:
        return 0
    shop = keeper.index.shop
    if f_buy:
        cost = c_div(obj.cost * shop.profit_buy, 100)
    else:
        cost = 0
        if obj.item_type in shop.buy_type:
            cost = c_div(obj.cost * shop.profit_sell, 100)
        if not is_obj_stat(obj, C.ITEM_SELL_EXTRACT):
            for obj2 in keeper.carrying:
                if _same_item(obj, obj2):
                    cost = c_div(cost, 2) if is_obj_stat(obj2, C.ITEM_INVENTORY) else c_div(cost * 3, 4)
    if obj.item_type in (C.ITEM_STAFF, C.ITEM_WAND):
        if obj.value[1] == 0:
            cost = c_div(cost, 4)
        else:
            cost = c_div(cost * obj.value[2], obj.value[1])
    return int32(cost)


def _pet_room(ch, where: str):
    """The room the pet shop's pets wait in: the next vnum, or for new Thalos's shop (9621), 9706."""
    ix = game_module.current.index
    room = ix.get_room_index(9706 if ch.in_room.vnum == 9621 else ch.in_room.vnum + 1)  # "hack to make new thalos
    if room is None:                                                                     # pets work"
        bug("%s: bad pet shop at vnum %%d." % where, ch.in_room.vnum)
    return room


def _buy_pet(ch, argument: str) -> None:
    from charm.commands.comm import add_follower
    from charm.entities.create import create_mobile
    from charm.systems.skills import check_improve

    argument = smash_tilde(argument)
    if ch.is_npc:
        return
    argument, arg = one_argument(argument)
    room = _pet_room(ch, "Do_buy")
    if room is None:
        send_to_char("Sorry, you can't buy that here.\n\r", ch)
        return
    in_room = ch.in_room
    ch.in_room = room
    pet = get_char_room(ch, arg)
    ch.in_room = in_room
    if pet is None or not pet.act & C.ACT_PET:
        send_to_char("Sorry, you can't buy that here.\n\r", ch)
        return
    if ch.pet is not None:
        send_to_char("You already own a pet.\n\r", ch)
        return
    cost = 10 * pet.level * pet.level
    if ch.silver + 100 * ch.gold < cost:
        send_to_char("You can't afford it.\n\r", ch)
        return
    if ch.level < pet.level:
        send_to_char("You're not powerful enough to master this pet.\n\r", ch)
        return
    roll = number_percent()  # "haggle"
    gsn = GSN["gsn_haggle"]
    if roll < get_skill(ch, gsn):
        cost -= c_div(c_div(cost, 2) * roll, 100)
        send_to_char("You haggle the price down to %d coins.\n\r" % cost, ch)
        check_improve(ch, gsn, True, 4)
    game = game_module.current
    deduct_cost(ch, cost)
    pet = create_mobile(game, pet.index)
    pet.act |= C.ACT_PET
    pet.affected_by |= C.AFF_CHARM
    pet.comm = C.COMM_NOTELL | C.COMM_NOSHOUT | C.COMM_NOCHANNELS
    argument, arg = one_argument(argument)
    if arg != "":
        pet.name = "%s %s" % (pet.name, arg)
    pet.description = "%sA neck tag says 'I belong to %s'.\n\r" % (pet.description, ch.name)
    char_to_room(pet, ch.in_room)
    add_follower(game, pet, ch)
    pet.leader = ch
    ch.pet = pet
    send_to_char("Enjoy your pet.\n\r", ch)
    act("$n bought $N as a pet.", ch, None, pet, C.TO_ROOM)


# C: act_obj.c do_buy
def do_buy(ch, argument: str) -> None:
    from charm.entities.create import create_object
    from charm.systems.skills import check_improve

    if argument == "":
        send_to_char("Buy what?\n\r", ch)
        return
    if ch.in_room.room_flags & C.ROOM_PET_SHOP:
        _buy_pet(ch, argument)
        return
    keeper = find_keeper(ch)
    if keeper is None:
        return
    number, arg = mult_argument(argument)
    obj = get_obj_keeper(ch, keeper, arg)
    cost = get_cost(keeper, obj, True)
    if number < 1 or number > 99:
        act("$n tells you 'Get real!", keeper, None, ch, C.TO_VICT)  # sic: no closing quote (#60)
        return
    if cost <= 0 or not can_see_obj(ch, obj):
        act("$n tells you 'I don't sell that -- try 'list''.", keeper, None, ch, C.TO_VICT)
        ch.reply = keeper
        return
    stock = keeper.carrying
    if not is_obj_stat(obj, C.ITEM_INVENTORY):
        count = 1
        for t_obj in stock[stock.index(obj) + 1:]:
            if count >= number:
                break
            if _same_item(t_obj, obj):
                count += 1
            else:
                break
        if count < number:
            act("$n tells you 'I don't have that many in stock.", keeper, None, ch, C.TO_VICT)  # sic (#60)
            ch.reply = keeper
            return
    if ch.silver + ch.gold * 100 < cost * number:
        if number > 1:
            act("$n tells you 'You can't afford to buy that many.", keeper, obj, ch, C.TO_VICT)  # sic (#60)
        else:
            act("$n tells you 'You can't afford to buy $p'.", keeper, obj, ch, C.TO_VICT)
        ch.reply = keeper
        return
    if obj.level > ch.level:
        act("$n tells you 'You can't use $p yet'.", keeper, obj, ch, C.TO_VICT)
        ch.reply = keeper
        return
    if ch.carry_number + number * get_obj_number(obj) > can_carry_n(ch):
        send_to_char("You can't carry that many items.\n\r", ch)
        return
    if ch.carry_weight + number * get_obj_weight(obj) > can_carry_w(ch):
        send_to_char("You can't carry that much weight.\n\r", ch)
        return
    roll = number_percent()  # "haggle"
    gsn = GSN["gsn_haggle"]
    if not is_obj_stat(obj, C.ITEM_SELL_EXTRACT) and roll < get_skill(ch, gsn):
        cost -= c_div(c_div(obj.cost, 2) * roll, 100)
        act("You haggle with $N.", ch, None, keeper, C.TO_CHAR)
        check_improve(ch, gsn, True, 4)
    if number > 1:
        act("$n buys $p[%d]." % number, ch, obj, None, C.TO_ROOM)
        act("You buy $p[%d] for %d silver." % (number, cost * number), ch, obj, None, C.TO_CHAR)
    else:
        act("$n buys $p.", ch, obj, None, C.TO_ROOM)
        act("You buy $p for %d silver." % cost, ch, obj, None, C.TO_CHAR)
    deduct_cost(ch, cost * number)
    keeper.gold += c_div(cost * number, 100)
    keeper.silver += cost * number - c_div(cost * number, 100) * 100
    game = game_module.current
    for _ in range(number):
        if obj.extra_flags & C.ITEM_INVENTORY:
            t_obj = create_object(game, obj.index, obj.level)
        else:
            t_obj = obj
            at = stock.index(obj)
            obj = stock[at + 1] if at + 1 < len(stock) else None
            obj_from_char(t_obj)
        if t_obj.timer > 0 and not is_obj_stat(t_obj, C.ITEM_HAD_TIMER):
            t_obj.timer = 0
        t_obj.extra_flags &= ~C.ITEM_HAD_TIMER
        obj_to_char(t_obj, ch)
        if cost < t_obj.cost:
            t_obj.cost = cost


# C: act_obj.c do_list
def do_list(ch, argument: str) -> None:
    if ch.in_room.room_flags & C.ROOM_PET_SHOP:
        room = _pet_room(ch, "Do_list")
        if room is None:
            send_to_char("You can't do that here.\n\r", ch)
            return
        found = False
        for pet in room.people:
            if pet.act & C.ACT_PET:
                if not found:
                    found = True
                    send_to_char("Pets for sale:\n\r", ch)
                send_to_char("[%2d] %8d - %s\n\r" % (pet.level, 10 * pet.level * pet.level, pet.short_descr), ch)
        if not found:
            send_to_char("Sorry, we're out of pets right now.\n\r", ch)
        return
    keeper = find_keeper(ch)
    if keeper is None:
        return
    _, arg = one_argument(argument)
    found = False
    stock = keeper.carrying
    i = 0
    while i < len(stock):
        obj = stock[i]
        if (obj.wear_loc == C.WEAR_NONE and can_see_obj(ch, obj) and (cost := get_cost(keeper, obj, True)) > 0
                and (arg == "" or is_name(arg, obj.name))):
            if not found:
                found = True
                send_to_char("[Lv Price Qty] Item\n\r", ch)
            if is_obj_stat(obj, C.ITEM_INVENTORY):
                send_to_char("[%2d %5d -- ] %s\n\r" % (obj.level, cost, obj.short_descr), ch)
            else:
                count = 1
                while i + 1 < len(stock) and _same_item(stock[i], stock[i + 1]):
                    i += 1
                    count += 1
                obj = stock[i]
                send_to_char("[%2d %5d %2d ] %s\n\r" % (obj.level, cost, count, obj.short_descr), ch)
        i += 1
    if not found:
        send_to_char("You can't buy anything here.\n\r", ch)


# C: act_obj.c do_sell
def do_sell(ch, argument: str) -> None:
    from charm.systems.skills import check_improve

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Sell what?\n\r", ch)
        return
    keeper = find_keeper(ch)
    if keeper is None:
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        act("$n tells you 'You don't have that item'.", keeper, None, ch, C.TO_VICT)
        ch.reply = keeper
        return
    if not can_drop_obj(ch, obj):
        send_to_char("You can't let go of it.\n\r", ch)
        return
    if not can_see_obj(keeper, obj):
        act("$n doesn't see what you are offering.", keeper, None, ch, C.TO_VICT)
        return
    cost = get_cost(keeper, obj, False)
    if cost <= 0:
        act("$n looks uninterested in $p.", keeper, obj, ch, C.TO_VICT)
        return
    if cost > keeper.silver + 100 * keeper.gold:
        act("$n tells you 'I'm afraid I don't have enough wealth to buy $p.", keeper, obj, ch, C.TO_VICT)  # sic (#60)
        return
    act("$n sells $p.", ch, obj, None, C.TO_ROOM)
    roll = number_percent()  # "haggle"
    gsn = GSN["gsn_haggle"]
    if not is_obj_stat(obj, C.ITEM_SELL_EXTRACT) and roll < get_skill(ch, gsn):
        send_to_char("You haggle with the shopkeeper.\n\r", ch)
        cost += c_div(c_div(obj.cost, 2) * roll, 100)
        cost = min(cost, c_div(95 * get_cost(keeper, obj, True), 100))
        cost = min(cost, keeper.silver + 100 * keeper.gold)
        check_improve(ch, gsn, True, 4)
    gold = c_div(cost, 100)
    # sic: "piece" or "pieces" goes by the whole price, not the gold (#60)
    act("You sell $p for %d silver and %d gold piece%s." % (cost - gold * 100, gold, "" if cost == 1 else "s"),
        ch, obj, None, C.TO_CHAR)
    ch.gold += gold
    ch.silver += cost - gold * 100
    deduct_cost(keeper, cost)
    if keeper.gold < 0:
        keeper.gold = 0
    if keeper.silver < 0:
        keeper.silver = 0
    if obj.item_type == C.ITEM_TRASH or is_obj_stat(obj, C.ITEM_SELL_EXTRACT):
        extract_obj(game_module.current, obj)
    else:
        obj_from_char(obj)
        if obj.timer:
            obj.extra_flags |= C.ITEM_HAD_TIMER
        else:
            obj.timer = number_range(50, 100)
        obj_to_keeper(obj, keeper)


# C: act_obj.c do_value
def do_value(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Value what?\n\r", ch)
        return
    keeper = find_keeper(ch)
    if keeper is None:
        return
    obj = get_obj_carry(ch, arg, ch)
    if obj is None:
        act("$n tells you 'You don't have that item'.", keeper, None, ch, C.TO_VICT)
        ch.reply = keeper
        return
    if not can_see_obj(keeper, obj):
        act("$n doesn't see what you are offering.", keeper, None, ch, C.TO_VICT)
        return
    if not can_drop_obj(ch, obj):
        send_to_char("You can't let go of it.\n\r", ch)
        return
    cost = get_cost(keeper, obj, False)
    if cost <= 0:
        act("$n looks uninterested in $p.", keeper, obj, ch, C.TO_VICT)
        return
    act("$n tells you 'I'll give you %d silver and %d gold coins for $p'." % (cost - c_div(cost, 100) * 100,
                                                                             c_div(cost, 100)), keeper, obj, ch,
        C.TO_VICT)
    ch.reply = keeper
