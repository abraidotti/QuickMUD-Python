"""Objects, act_obj.c's first part: get, put, drop, give, wear, wield, hold and remove, and the corpse-looting rule.

The rest of act_obj.c (food and drink, shops, sacrifice, steal and the magic items) comes in P3's next PR.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_obj.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import is_number, one_argument
from charm.core.cint import c_div, int32
from charm.core.rng import number_range
from charm.core.strings import atoi, str_cmp, str_prefix
from charm.data import constants as C
from charm.data.attributes import STR_APP
from charm.entities import game as game_module
from charm.entities.handler import (
    can_carry_n, can_carry_w, can_drop_obj, can_see, can_see_obj, create_money, equip_char, extract_obj,
    get_carry_weight, get_char_room, get_curr_stat, get_eq_char, get_obj_carry, get_obj_here, get_obj_list,
    get_obj_number, get_obj_wear, get_obj_weight, get_true_weight, get_trust, get_weapon_skill, get_weapon_sn,
    is_affected, is_immortal, is_name, is_obj_stat, obj_from_char, obj_from_obj, obj_from_room, obj_to_char,
    obj_to_obj, obj_to_room, unequip_char, weight_mult)
from charm.net.act import MOB_TRIGGER, act
from charm.net.output import send_to_char
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
