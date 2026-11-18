"""act_move.c and act_enter.c: walking, doors and locks, positions and furniture, sneak and hide, recall, train,
and portals.

Exit, greet and entry triggers are scanned (charm.systems.mobprog); running one isn't ported, and no stock area
has any. Recalling out of a fight needs a fight, so it waits for P4 to be reached, though it's ported.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_move.c, src/act_enter.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.cint import c_div, sh_int
from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.core.strings import str_cmp
from charm.data import constants as C
from charm.data.classes import CLASS_TABLE
from charm.net.act import act, act_new
from charm.net.output import send_to_char

DIR_NAME = ("north", "east", "south", "west", "up", "down")
REV_DIR = (2, 3, 0, 1, 5, 4)
MOVEMENT_LOSS = (1, 2, 2, 3, 4, 6, 4, 1, 6, 10, 6)  # by sector type
_DOOR_WORDS = (("n", "north"), ("e", "east"), ("s", "south"), ("w", "west"), ("u", "up"), ("d", "down"))


# C: act_move.c move_char
def move_char(ch, door: int, follow: bool) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.info import do_look
    from charm.entities.handler import (can_see_room, char_from_room, char_to_room, get_trust, is_affected,
                                        is_immortal, is_room_owner, next_in_room, room_is_private)
    from charm.systems.mobprog import has_trigger, mp_exit_trigger, mp_greet_trigger, mp_percent_trigger

    if door < 0 or door > 5:
        bug("Do_move: bad door %d.", door)
        return
    # "Exit trigger, if activated, bail out. Only PCs are triggered."
    if not ch.is_npc and mp_exit_trigger(ch, door):
        return
    in_room = ch.in_room
    pexit = in_room.exit[door]
    to_room = pexit.to_room if pexit is not None else None
    if pexit is None or to_room is None or not can_see_room(ch, to_room):
        send_to_char("Alas, you cannot go that way.\n\r", ch)
        return
    if (pexit.exit_info & C.EX_CLOSED
            and (not is_affected(ch, C.AFF_PASS_DOOR) or pexit.exit_info & C.EX_NOPASS)
            and not get_trust(ch) >= C.ANGEL):
        act("The $d is closed.", ch, None, pexit.keyword, C.TO_CHAR)
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is not None and in_room is ch.master.in_room:
        send_to_char("What?  And leave your beloved master?\n\r", ch)
        return
    if not is_room_owner(ch, to_room) and room_is_private(to_room):
        send_to_char("That room is private right now.\n\r", ch)
        return

    if not ch.is_npc:
        for i_class in range(C.MAX_CLASS):
            for i_guild in range(C.MAX_GUILD):
                if i_class != ch.class_ and to_room.vnum == CLASS_TABLE[i_class].guild[i_guild]:
                    send_to_char("You aren't allowed in there.\n\r", ch)
                    return
        if in_room.sector_type == C.SECT_AIR or to_room.sector_type == C.SECT_AIR:
            if not is_affected(ch, C.AFF_FLYING) and not is_immortal(ch):
                send_to_char("You can't fly.\n\r", ch)
                return
        if ((in_room.sector_type == C.SECT_WATER_NOSWIM or to_room.sector_type == C.SECT_WATER_NOSWIM)
                and not is_affected(ch, C.AFF_FLYING)):
            # "Look for a boat."
            found = is_immortal(ch) or any(obj.item_type == C.ITEM_BOAT for obj in ch.carrying)
            if not found:
                send_to_char("You need a boat to go there.\n\r", ch)
                return
        move = (MOVEMENT_LOSS[min(C.SECT_MAX - 1, in_room.sector_type)]
                + MOVEMENT_LOSS[min(C.SECT_MAX - 1, to_room.sector_type)])
        move = c_div(move, 2)  # "i.e. the average"
        # "conditional effects"
        if is_affected(ch, C.AFF_FLYING) or is_affected(ch, C.AFF_HASTE):
            move = c_div(move, 2)
        if is_affected(ch, C.AFF_SLOW):
            move *= 2
        if ch.move < move:
            send_to_char("You are too exhausted.\n\r", ch)
            return
        wait_state(ch, 1)
        ch.move -= move

    if not is_affected(ch, C.AFF_SNEAK) and ch.invis_level < C.LEVEL_HERO:
        act("$n leaves $T.", ch, None, DIR_NAME[door], C.TO_ROOM)
    char_from_room(ch)
    char_to_room(ch, to_room)
    if not is_affected(ch, C.AFF_SNEAK) and ch.invis_level < C.LEVEL_HERO:
        act("$n has arrived.", ch, None, None, C.TO_ROOM)
    do_look(ch, "auto")

    if in_room is to_room:  # "no circular follows"
        return
    fch = in_room.people[0] if in_room.people else None
    while fch is not None:
        fch_next = next_in_room(fch)  # taken before fch moves, as the C does
        if fch.master is ch and is_affected(fch, C.AFF_CHARM) and fch.position < C.POS_STANDING:
            do_stand(fch, "")
        if fch.master is ch and fch.position == C.POS_STANDING and can_see_room(fch, to_room):
            if ch.in_room.room_flags & C.ROOM_LAW and fch.is_npc and fch.act & C.ACT_AGGRESSIVE:
                act("You can't bring $N into the city.", ch, None, fch, C.TO_CHAR)
                act("You aren't allowed in the city.", fch, None, None, C.TO_CHAR)
                fch = fch_next
                continue
            act("You follow $N.", fch, None, ch, C.TO_CHAR)
            move_char(fch, door, True)
        fch = fch_next

    # "If someone is following the char, these triggers get activated for the followers before the char, but
    # it's safer this way..."
    if ch.is_npc and has_trigger(ch, C.TRIG_ENTRY):
        mp_percent_trigger(ch, None, None, None, C.TRIG_ENTRY)
    if not ch.is_npc:
        mp_greet_trigger(ch)


# C: act_move.c do_north
def do_north(ch, argument: str) -> None:
    move_char(ch, C.DIR_NORTH, False)


# C: act_move.c do_east
def do_east(ch, argument: str) -> None:
    move_char(ch, C.DIR_EAST, False)


# C: act_move.c do_south
def do_south(ch, argument: str) -> None:
    move_char(ch, C.DIR_SOUTH, False)


# C: act_move.c do_west
def do_west(ch, argument: str) -> None:
    move_char(ch, C.DIR_WEST, False)


# C: act_move.c do_up
def do_up(ch, argument: str) -> None:
    move_char(ch, C.DIR_UP, False)


# C: act_move.c do_down
def do_down(ch, argument: str) -> None:
    move_char(ch, C.DIR_DOWN, False)


# C: act_move.c find_door
def find_door(ch, arg: str) -> int:
    from charm.entities.handler import is_name

    for door, (short, full) in enumerate(_DOOR_WORDS):
        if str_cmp(arg, short) or str_cmp(arg, full):
            break
    else:
        for door in range(6):
            pexit = ch.in_room.exit[door]
            if (pexit is not None and pexit.exit_info & C.EX_ISDOOR and pexit.keyword is not None
                    and is_name(arg, pexit.keyword)):
                return door
        act("I see no $T here.", ch, None, arg, C.TO_CHAR)
        return -1
    pexit = ch.in_room.exit[door]
    if pexit is None:
        act("I see no door $T here.", ch, None, arg, C.TO_CHAR)
        return -1
    if not pexit.exit_info & C.EX_ISDOOR:
        send_to_char("You can't do that.\n\r", ch)
        return -1
    return door


def _other_side(ch, door: int):
    """The exit back from the room a door leads to, if it leads back here: the C's pexit_rev test."""
    to_room = ch.in_room.exit[door].to_room
    if to_room is None:
        return None, None
    rev = to_room.exit[REV_DIR[door]]
    return (to_room, rev) if rev is not None and rev.to_room is ch.in_room else (to_room, None)


# C: act_move.c do_open
def do_open(ch, argument: str) -> None:
    from charm.entities.handler import get_obj_here

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Open what?\n\r", ch)
        return
    obj = get_obj_here(ch, arg)
    if obj is not None:
        if obj.item_type == C.ITEM_PORTAL:  # "open portal"
            if not obj.value[1] & C.EX_ISDOOR:
                send_to_char("You can't do that.\n\r", ch)
                return
            if not obj.value[1] & C.EX_CLOSED:
                send_to_char("It's already open.\n\r", ch)
                return
            if obj.value[1] & C.EX_LOCKED:
                send_to_char("It's locked.\n\r", ch)
                return
            obj.value[1] &= ~C.EX_CLOSED
            act("You open $p.", ch, obj, None, C.TO_CHAR)
            act("$n opens $p.", ch, obj, None, C.TO_ROOM)
            return
        if obj.item_type != C.ITEM_CONTAINER:  # "'open object'"
            send_to_char("That's not a container.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSED:
            send_to_char("It's already open.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSEABLE:
            send_to_char("You can't do that.\n\r", ch)
            return
        if obj.value[1] & C.CONT_LOCKED:
            send_to_char("It's locked.\n\r", ch)
            return
        obj.value[1] &= ~C.CONT_CLOSED
        act("You open $p.", ch, obj, None, C.TO_CHAR)
        act("$n opens $p.", ch, obj, None, C.TO_ROOM)
        return
    door = find_door(ch, arg)
    if door >= 0:  # "'open door'"
        pexit = ch.in_room.exit[door]
        if not pexit.exit_info & C.EX_CLOSED:
            send_to_char("It's already open.\n\r", ch)
            return
        if pexit.exit_info & C.EX_LOCKED:
            send_to_char("It's locked.\n\r", ch)
            return
        pexit.exit_info &= ~C.EX_CLOSED
        act("$n opens the $d.", ch, None, pexit.keyword, C.TO_ROOM)
        send_to_char("Ok.\n\r", ch)
        to_room, rev = _other_side(ch, door)  # "open the other side"
        if rev is not None:
            rev.exit_info &= ~C.EX_CLOSED
            for rch in list(to_room.people):
                act("The $d opens.", rch, None, rev.keyword, C.TO_CHAR)


# C: act_move.c do_close
def do_close(ch, argument: str) -> None:
    from charm.entities.handler import get_obj_here

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Close what?\n\r", ch)
        return
    obj = get_obj_here(ch, arg)
    if obj is not None:
        if obj.item_type == C.ITEM_PORTAL:  # "portal stuff"
            if not obj.value[1] & C.EX_ISDOOR or obj.value[1] & C.EX_NOCLOSE:
                send_to_char("You can't do that.\n\r", ch)
                return
            if obj.value[1] & C.EX_CLOSED:
                send_to_char("It's already closed.\n\r", ch)
                return
            obj.value[1] |= C.EX_CLOSED
            act("You close $p.", ch, obj, None, C.TO_CHAR)
            act("$n closes $p.", ch, obj, None, C.TO_ROOM)
            return
        if obj.item_type != C.ITEM_CONTAINER:  # "'close object'"
            send_to_char("That's not a container.\n\r", ch)
            return
        if obj.value[1] & C.CONT_CLOSED:
            send_to_char("It's already closed.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSEABLE:
            send_to_char("You can't do that.\n\r", ch)
            return
        obj.value[1] |= C.CONT_CLOSED
        act("You close $p.", ch, obj, None, C.TO_CHAR)
        act("$n closes $p.", ch, obj, None, C.TO_ROOM)
        return
    door = find_door(ch, arg)
    if door >= 0:  # "'close door'"
        pexit = ch.in_room.exit[door]
        if pexit.exit_info & C.EX_CLOSED:
            send_to_char("It's already closed.\n\r", ch)
            return
        pexit.exit_info |= C.EX_CLOSED
        act("$n closes the $d.", ch, None, pexit.keyword, C.TO_ROOM)
        send_to_char("Ok.\n\r", ch)
        to_room, rev = _other_side(ch, door)  # "close the other side"
        if rev is not None:
            rev.exit_info |= C.EX_CLOSED
            for rch in list(to_room.people):
                act("The $d closes.", rch, None, rev.keyword, C.TO_CHAR)


# C: act_move.c has_key
def has_key(ch, key: int) -> bool:
    return any(obj.index.vnum == key for obj in ch.carrying)


# C: act_move.c do_lock
def do_lock(ch, argument: str) -> None:
    from charm.entities.handler import get_obj_here

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Lock what?\n\r", ch)
        return
    obj = get_obj_here(ch, arg)
    if obj is not None:
        if obj.item_type == C.ITEM_PORTAL:  # "portal stuff"
            if not obj.value[1] & C.EX_ISDOOR or obj.value[1] & C.EX_NOCLOSE:
                send_to_char("You can't do that.\n\r", ch)
                return
            if not obj.value[1] & C.EX_CLOSED:
                send_to_char("It's not closed.\n\r", ch)
                return
            if obj.value[4] < 0 or obj.value[1] & C.EX_NOLOCK:
                send_to_char("It can't be locked.\n\r", ch)
                return
            if not has_key(ch, obj.value[4]):
                send_to_char("You lack the key.\n\r", ch)
                return
            if obj.value[1] & C.EX_LOCKED:
                send_to_char("It's already locked.\n\r", ch)
                return
            obj.value[1] |= C.EX_LOCKED
            act("You lock $p.", ch, obj, None, C.TO_CHAR)
            act("$n locks $p.", ch, obj, None, C.TO_ROOM)
            return
        if obj.item_type != C.ITEM_CONTAINER:  # "'lock object'"
            send_to_char("That's not a container.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSED:
            send_to_char("It's not closed.\n\r", ch)
            return
        if obj.value[2] < 0:
            send_to_char("It can't be locked.\n\r", ch)
            return
        if not has_key(ch, obj.value[2]):
            send_to_char("You lack the key.\n\r", ch)
            return
        if obj.value[1] & C.CONT_LOCKED:
            send_to_char("It's already locked.\n\r", ch)
            return
        obj.value[1] |= C.CONT_LOCKED
        act("You lock $p.", ch, obj, None, C.TO_CHAR)
        act("$n locks $p.", ch, obj, None, C.TO_ROOM)
        return
    door = find_door(ch, arg)
    if door >= 0:  # "'lock door'"
        pexit = ch.in_room.exit[door]
        if not pexit.exit_info & C.EX_CLOSED:
            send_to_char("It's not closed.\n\r", ch)
            return
        if pexit.key < 0:
            send_to_char("It can't be locked.\n\r", ch)
            return
        if not has_key(ch, pexit.key):
            send_to_char("You lack the key.\n\r", ch)
            return
        if pexit.exit_info & C.EX_LOCKED:
            send_to_char("It's already locked.\n\r", ch)
            return
        pexit.exit_info |= C.EX_LOCKED
        send_to_char("*Click*\n\r", ch)
        act("$n locks the $d.", ch, None, pexit.keyword, C.TO_ROOM)
        _, rev = _other_side(ch, door)  # "lock the other side"
        if rev is not None:
            rev.exit_info |= C.EX_LOCKED


# C: act_move.c do_unlock
def do_unlock(ch, argument: str) -> None:
    from charm.entities.handler import get_obj_here

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Unlock what?\n\r", ch)
        return
    obj = get_obj_here(ch, arg)
    if obj is not None:
        if obj.item_type == C.ITEM_PORTAL:  # "portal stuff"
            if not obj.value[1] & C.EX_ISDOOR:
                send_to_char("You can't do that.\n\r", ch)
                return
            if not obj.value[1] & C.EX_CLOSED:
                send_to_char("It's not closed.\n\r", ch)
                return
            if obj.value[4] < 0:
                send_to_char("It can't be unlocked.\n\r", ch)
                return
            if not has_key(ch, obj.value[4]):
                send_to_char("You lack the key.\n\r", ch)
                return
            if not obj.value[1] & C.EX_LOCKED:
                send_to_char("It's already unlocked.\n\r", ch)
                return
            obj.value[1] &= ~C.EX_LOCKED
            act("You unlock $p.", ch, obj, None, C.TO_CHAR)
            act("$n unlocks $p.", ch, obj, None, C.TO_ROOM)
            return
        if obj.item_type != C.ITEM_CONTAINER:  # "'unlock object'"
            send_to_char("That's not a container.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSED:
            send_to_char("It's not closed.\n\r", ch)
            return
        if obj.value[2] < 0:
            send_to_char("It can't be unlocked.\n\r", ch)
            return
        if not has_key(ch, obj.value[2]):
            send_to_char("You lack the key.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_LOCKED:
            send_to_char("It's already unlocked.\n\r", ch)
            return
        obj.value[1] &= ~C.CONT_LOCKED
        act("You unlock $p.", ch, obj, None, C.TO_CHAR)
        act("$n unlocks $p.", ch, obj, None, C.TO_ROOM)
        return
    door = find_door(ch, arg)
    if door >= 0:  # "'unlock door'"
        pexit = ch.in_room.exit[door]
        if not pexit.exit_info & C.EX_CLOSED:
            send_to_char("It's not closed.\n\r", ch)
            return
        if pexit.key < 0:
            send_to_char("It can't be unlocked.\n\r", ch)
            return
        if not has_key(ch, pexit.key):
            send_to_char("You lack the key.\n\r", ch)
            return
        if not pexit.exit_info & C.EX_LOCKED:
            send_to_char("It's already unlocked.\n\r", ch)
            return
        pexit.exit_info &= ~C.EX_LOCKED
        send_to_char("*Click*\n\r", ch)
        act("$n unlocks the $d.", ch, None, pexit.keyword, C.TO_ROOM)
        _, rev = _other_side(ch, door)  # "unlock the other side"
        if rev is not None:
            rev.exit_info &= ~C.EX_LOCKED


# C: act_move.c do_pick
def do_pick(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.core.rng import number_percent
    from charm.data.skills import SKILL_TABLE
    from charm.entities.handler import get_obj_here, get_skill, is_awake, is_immortal
    from charm.systems.skills import check_improve
    from charm.world.lookup import GSN

    gsn = GSN["gsn_pick_lock"]
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Pick what?\n\r", ch)
        return
    wait_state(ch, SKILL_TABLE[gsn].beats)
    for gch in list(ch.in_room.people):  # "look for guards"
        if gch.is_npc and is_awake(gch) and ch.level + 5 < gch.level:
            act("$N is standing too close to the lock.", ch, None, gch, C.TO_CHAR)
            return
    if not ch.is_npc and number_percent() > get_skill(ch, gsn):
        send_to_char("You failed.\n\r", ch)
        check_improve(ch, gsn, False, 2)
        return
    obj = get_obj_here(ch, arg)
    if obj is not None:
        if obj.item_type == C.ITEM_PORTAL:  # "portal stuff"
            if not obj.value[1] & C.EX_ISDOOR:
                send_to_char("You can't do that.\n\r", ch)
                return
            if not obj.value[1] & C.EX_CLOSED:
                send_to_char("It's not closed.\n\r", ch)
                return
            if obj.value[4] < 0:
                send_to_char("It can't be unlocked.\n\r", ch)
                return
            if obj.value[1] & C.EX_PICKPROOF:
                send_to_char("You failed.\n\r", ch)
                return
            obj.value[1] &= ~C.EX_LOCKED  # the C doesn't check that it was locked (#43)
            act("You pick the lock on $p.", ch, obj, None, C.TO_CHAR)
            act("$n picks the lock on $p.", ch, obj, None, C.TO_ROOM)
            check_improve(ch, gsn, True, 2)
            return
        if obj.item_type != C.ITEM_CONTAINER:  # "'pick object'"
            send_to_char("That's not a container.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_CLOSED:
            send_to_char("It's not closed.\n\r", ch)
            return
        if obj.value[2] < 0:
            send_to_char("It can't be unlocked.\n\r", ch)
            return
        if not obj.value[1] & C.CONT_LOCKED:
            send_to_char("It's already unlocked.\n\r", ch)
            return
        if obj.value[1] & C.CONT_PICKPROOF:
            send_to_char("You failed.\n\r", ch)
            return
        obj.value[1] &= ~C.CONT_LOCKED
        act("You pick the lock on $p.", ch, obj, None, C.TO_CHAR)
        act("$n picks the lock on $p.", ch, obj, None, C.TO_ROOM)
        check_improve(ch, gsn, True, 2)
        return
    door = find_door(ch, arg)
    if door >= 0:  # "'pick door'"
        pexit = ch.in_room.exit[door]
        if not pexit.exit_info & C.EX_CLOSED and not is_immortal(ch):
            send_to_char("It's not closed.\n\r", ch)
            return
        if pexit.key < 0 and not is_immortal(ch):
            send_to_char("It can't be picked.\n\r", ch)
            return
        if not pexit.exit_info & C.EX_LOCKED:
            send_to_char("It's already unlocked.\n\r", ch)
            return
        if pexit.exit_info & C.EX_PICKPROOF and not is_immortal(ch):
            send_to_char("You failed.\n\r", ch)
            return
        pexit.exit_info &= ~C.EX_LOCKED
        send_to_char("*Click*\n\r", ch)
        act("$n picks the $d.", ch, None, pexit.keyword, C.TO_ROOM)
        check_improve(ch, gsn, True, 2)
        _, rev = _other_side(ch, door)  # "pick the other side"
        if rev is not None:
            rev.exit_info &= ~C.EX_LOCKED


def _furniture(ch, argument: str):
    """get_obj_list (ch, argument, ch->in_room->contents)."""
    from charm.entities.handler import get_obj_list

    return get_obj_list(ch, argument, ch.in_room.contents)


def _where(obj, at: int, on: int) -> str:
    """Which of the three words the C picks: at, then on, then in."""
    return "at" if obj.value[2] & at else "on" if obj.value[2] & on else "in"


# C: act_move.c do_stand
def do_stand(ch, argument: str) -> None:
    from charm.commands.info import do_look
    from charm.entities.handler import count_users, is_affected

    obj = None
    if argument != "":
        if ch.position == C.POS_FIGHTING:
            send_to_char("Maybe you should finish fighting first?\n\r", ch)
            return
        obj = _furniture(ch, argument)
        if obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
        if obj.item_type != C.ITEM_FURNITURE or not obj.value[2] & (C.STAND_AT | C.STAND_ON | C.STAND_IN):
            send_to_char("You can't seem to find a place to stand.\n\r", ch)
            return
        if ch.on is not obj and count_users(obj) >= obj.value[0]:
            act_new("There's no room to stand on $p.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            return
        ch.on = obj

    if ch.position == C.POS_SLEEPING:
        if is_affected(ch, C.AFF_SLEEP):
            send_to_char("You can't wake up!\n\r", ch)
            return
        if obj is None:
            send_to_char("You wake and stand up.\n\r", ch)
            act("$n wakes and stands up.", ch, None, None, C.TO_ROOM)
            ch.on = None
        else:
            w = _where(obj, C.STAND_AT, C.STAND_ON)
            act_new(f"You wake and stand {w} $p.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            act(f"$n wakes and stands {w} $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_STANDING
        do_look(ch, "auto")
    elif ch.position in (C.POS_RESTING, C.POS_SITTING):
        if obj is None:
            send_to_char("You stand up.\n\r", ch)
            act("$n stands up.", ch, None, None, C.TO_ROOM)
            ch.on = None
        else:
            w = _where(obj, C.STAND_AT, C.STAND_ON)
            act(f"You stand {w} $p.", ch, obj, None, C.TO_CHAR)
            act("$n stands on $p." if w == "in" else f"$n stands {w} $p.", ch, obj, None, C.TO_ROOM)  # sic (#44)
        ch.position = C.POS_STANDING
    elif ch.position == C.POS_STANDING:
        send_to_char("You are already standing.\n\r", ch)
    elif ch.position == C.POS_FIGHTING:
        send_to_char("You are already fighting!\n\r", ch)


# C: act_move.c do_rest
def do_rest(ch, argument: str) -> None:
    from charm.entities.handler import count_users, is_affected

    if ch.position == C.POS_FIGHTING:
        send_to_char("You are already fighting!\n\r", ch)
        return
    # "okay, now that we know we can rest, find an object to rest on"
    if argument != "":
        obj = _furniture(ch, argument)
        if obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
    else:
        obj = ch.on
    if obj is not None:
        if obj.item_type != C.ITEM_FURNITURE or not obj.value[2] & (C.REST_ON | C.REST_IN | C.REST_AT):
            send_to_char("You can't rest on that.\n\r", ch)
            return
        if ch.on is not obj and count_users(obj) >= obj.value[0]:
            act_new("There's no more room on $p.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            return
        ch.on = obj

    w = _where(obj, C.REST_AT, C.REST_ON) if obj is not None else None
    if ch.position == C.POS_SLEEPING:
        if is_affected(ch, C.AFF_SLEEP):
            send_to_char("You can't wake up!\n\r", ch)
            return
        if obj is None:
            send_to_char("You wake up and start resting.\n\r", ch)
            act("$n wakes up and starts resting.", ch, None, None, C.TO_ROOM)
        else:
            act_new(f"You wake up and rest {w} $p.", ch, obj, None, C.TO_CHAR, C.POS_SLEEPING)
            act(f"$n wakes up and rests {w} $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_RESTING
    elif ch.position == C.POS_RESTING:
        send_to_char("You are already resting.\n\r", ch)
    elif ch.position == C.POS_STANDING:
        if obj is None:
            send_to_char("You rest.\n\r", ch)
            act("$n sits down and rests.", ch, None, None, C.TO_ROOM)
        elif w == "at":
            act("You sit down at $p and rest.", ch, obj, None, C.TO_CHAR)
            act("$n sits down at $p and rests.", ch, obj, None, C.TO_ROOM)
        elif w == "on":
            act("You sit on $p and rest.", ch, obj, None, C.TO_CHAR)
            act("$n sits on $p and rests.", ch, obj, None, C.TO_ROOM)
        else:
            act("You rest in $p.", ch, obj, None, C.TO_CHAR)
            act("$n rests in $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_RESTING
    elif ch.position == C.POS_SITTING:
        if obj is None:
            send_to_char("You rest.\n\r", ch)
            act("$n rests.", ch, None, None, C.TO_ROOM)
        else:
            act(f"You rest {w} $p.", ch, obj, None, C.TO_CHAR)
            act(f"$n rests {w} $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_RESTING


# C: act_move.c do_sit
def do_sit(ch, argument: str) -> None:
    from charm.entities.handler import count_users, is_affected

    if ch.position == C.POS_FIGHTING:
        send_to_char("Maybe you should finish this fight first?\n\r", ch)
        return
    # "okay, now that we know we can sit, find an object to sit on"
    if argument != "":
        obj = _furniture(ch, argument)
        if obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
    else:
        obj = ch.on
    if obj is not None:
        if obj.item_type != C.ITEM_FURNITURE or not obj.value[2] & (C.SIT_ON | C.SIT_IN | C.SIT_AT):
            send_to_char("You can't sit on that.\n\r", ch)
            return
        if ch.on is not obj and count_users(obj) >= obj.value[0]:
            act_new("There's no more room on $p.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            return
        ch.on = obj

    w = _where(obj, C.SIT_AT, C.SIT_ON) if obj is not None else None
    if ch.position == C.POS_SLEEPING:
        if is_affected(ch, C.AFF_SLEEP):
            send_to_char("You can't wake up!\n\r", ch)
            return
        if obj is None:
            send_to_char("You wake and sit up.\n\r", ch)
            act("$n wakes and sits up.", ch, None, None, C.TO_ROOM)
        else:
            act_new(f"You wake and sit {w} $p.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            act("$n wakes and sits at $p." if w == "on" else f"$n wakes and sits {w} $p.", ch, obj, None,
                C.TO_ROOM)  # sic: "at" for "on" (#44)
        ch.position = C.POS_SITTING
    elif ch.position == C.POS_RESTING:
        if obj is None:
            send_to_char("You stop resting.\n\r", ch)
        elif w in ("at", "on"):  # sic: furniture you sit in says nothing (#44)
            act(f"You sit {w} $p.", ch, obj, None, C.TO_CHAR)
            act(f"$n sits {w} $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_SITTING
    elif ch.position == C.POS_SITTING:
        send_to_char("You are already sitting down.\n\r", ch)
    elif ch.position == C.POS_STANDING:
        if obj is None:
            send_to_char("You sit down.\n\r", ch)
            act("$n sits down on the ground.", ch, None, None, C.TO_ROOM)
        elif w == "at":
            act("You sit down at $p.", ch, obj, None, C.TO_CHAR)
            act("$n sits down at $p.", ch, obj, None, C.TO_ROOM)
        elif w == "on":
            act("You sit on $p.", ch, obj, None, C.TO_CHAR)
            act("$n sits on $p.", ch, obj, None, C.TO_ROOM)
        else:
            act("You sit down in $p.", ch, obj, None, C.TO_CHAR)
            act("$n sits down in $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_SITTING


# C: act_move.c do_sleep
def do_sleep(ch, argument: str) -> None:
    from charm.entities.handler import count_users

    if ch.position == C.POS_SLEEPING:
        send_to_char("You are already sleeping.\n\r", ch)
    elif ch.position in (C.POS_RESTING, C.POS_SITTING, C.POS_STANDING):
        if argument == "" and ch.on is None:
            send_to_char("You go to sleep.\n\r", ch)
            act("$n goes to sleep.", ch, None, None, C.TO_ROOM)
            ch.position = C.POS_SLEEPING
            return
        # "find an object and sleep on it"
        obj = ch.on if argument == "" else _furniture(ch, argument)
        if obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
        if obj.item_type != C.ITEM_FURNITURE or not obj.value[2] & (C.SLEEP_ON | C.SLEEP_IN | C.SLEEP_AT):
            send_to_char("You can't sleep on that!\n\r", ch)
            return
        if ch.on is not obj and count_users(obj) >= obj.value[0]:
            act_new("There is no room on $p for you.", ch, obj, None, C.TO_CHAR, C.POS_DEAD)
            return
        ch.on = obj
        w = _where(obj, C.SLEEP_AT, C.SLEEP_ON)
        act(f"You go to sleep {w} $p.", ch, obj, None, C.TO_CHAR)
        act(f"$n goes to sleep {w} $p.", ch, obj, None, C.TO_ROOM)
        ch.position = C.POS_SLEEPING
    elif ch.position == C.POS_FIGHTING:
        send_to_char("You are already fighting!\n\r", ch)


# C: act_move.c do_wake
def do_wake(ch, argument: str) -> None:
    from charm.entities.handler import get_char_room, is_affected, is_awake

    _, arg = one_argument(argument)
    if arg == "":
        do_stand(ch, "")
        return
    if not is_awake(ch):
        send_to_char("You are asleep yourself!\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if is_awake(victim):
        act("$N is already awake.", ch, None, victim, C.TO_CHAR)
        return
    if is_affected(victim, C.AFF_SLEEP):
        act("You can't wake $M!", ch, None, victim, C.TO_CHAR)
        return
    act_new("$n wakes you.", ch, None, victim, C.TO_VICT, C.POS_SLEEPING)
    do_stand(ch, "")  # sic: the C stands ch, not the victim (#41)


# C: act_move.c do_sneak
def do_sneak(ch, argument: str) -> None:
    from charm.core.rng import number_percent
    from charm.entities.handler import affect_strip, affect_to_char, get_skill, is_affected
    from charm.systems.skills import check_improve
    from charm.world.index import Affect
    from charm.world.lookup import GSN

    gsn = GSN["gsn_sneak"]
    send_to_char("You attempt to move silently.\n\r", ch)
    affect_strip(ch, gsn)
    if is_affected(ch, C.AFF_SNEAK):
        return
    if number_percent() < get_skill(ch, gsn):
        check_improve(ch, gsn, True, 3)
        affect_to_char(ch, Affect(where=C.TO_AFFECTS, type=gsn, level=ch.level, duration=ch.level,
                                  location=C.APPLY_NONE, modifier=0, bitvector=C.AFF_SNEAK))
    else:
        check_improve(ch, gsn, False, 3)


# C: act_move.c do_hide
def do_hide(ch, argument: str) -> None:
    from charm.core.rng import number_percent
    from charm.entities.handler import get_skill
    from charm.systems.skills import check_improve
    from charm.world.lookup import GSN

    gsn = GSN["gsn_hide"]
    send_to_char("You attempt to hide.\n\r", ch)
    ch.affected_by &= ~C.AFF_HIDE
    if number_percent() < get_skill(ch, gsn):
        ch.affected_by |= C.AFF_HIDE
        check_improve(ch, gsn, True, 3)
    else:
        check_improve(ch, gsn, False, 3)


# C: act_move.c do_visible
def do_visible(ch, argument: str) -> None:
    from charm.entities.handler import affect_strip
    from charm.world.lookup import GSN

    affect_strip(ch, GSN["gsn_invis"])
    affect_strip(ch, GSN["gsn_mass_invis"])
    affect_strip(ch, GSN["gsn_sneak"])
    ch.affected_by &= ~(C.AFF_HIDE | C.AFF_INVISIBLE | C.AFF_SNEAK)
    send_to_char("Ok.\n\r", ch)


# C: act_move.c do_recall
def do_recall(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.commands.info import do_look
    from charm.core.rng import number_percent
    from charm.entities import game as game_module
    from charm.entities.handler import char_from_room, char_to_room, get_skill, is_affected
    from charm.systems.fight import stop_fighting
    from charm.systems.skills import check_improve
    from charm.systems.update import gain_exp
    from charm.world.lookup import GSN

    game = game_module.current
    if ch.is_npc and not ch.act & C.ACT_PET:
        send_to_char("Only players can recall.\n\r", ch)
        return
    act("$n prays for transportation!", ch, None, None, C.TO_ROOM)
    location = game.index.get_room_index(C.ROOM_VNUM_TEMPLE)
    if location is None:
        send_to_char("You are completely lost.\n\r", ch)
        return
    if ch.in_room is location:
        return
    if ch.in_room.room_flags & C.ROOM_NO_RECALL or is_affected(ch, C.AFF_CURSE):
        send_to_char("Mota has forsaken you.\n\r", ch)
        return
    if ch.fighting is not None:
        gsn = GSN["gsn_recall"]
        skill = get_skill(ch, gsn)
        if number_percent() < c_div(80 * skill, 100):
            check_improve(ch, gsn, False, 6)
            wait_state(ch, 4)
            send_to_char("You failed!.\n\r", ch)
            return
        lose = 25 if ch.desc is not None else 50
        gain_exp(ch, 0 - lose)
        check_improve(ch, gsn, True, 4)
        send_to_char("You recall from combat!  You lose %d exps.\n\r" % lose, ch)
        stop_fighting(game, ch, True)
    ch.move = c_div(ch.move, 2)
    act("$n disappears.", ch, None, None, C.TO_ROOM)
    char_from_room(ch)
    char_to_room(ch, location)
    act("$n appears in the room.", ch, None, None, C.TO_ROOM)
    do_look(ch, "auto")
    if ch.pet is not None:
        do_recall(ch.pet, "")


_STATS = (("str", C.STAT_STR, "strength"), ("int", C.STAT_INT, "intelligence"), ("wis", C.STAT_WIS, "wisdom"),
          ("dex", C.STAT_DEX, "dexterity"), ("con", C.STAT_CON, "constitution"))


# C: act_move.c do_train
def do_train(ch, argument: str) -> None:
    from charm.entities.handler import get_max_train

    if ch.is_npc:
        return
    # "Check for trainer."
    if not any(mob.is_npc and mob.act & C.ACT_TRAIN for mob in ch.in_room.people):
        send_to_char("You can't do that here.\n\r", ch)
        return
    if argument == "":
        send_to_char("You have %d training sessions.\n\r" % ch.train, ch)
        argument = "foo"
    cost = 1  # the C sets 1 for a prime stat too: every cost is 1
    stat, output = -1, None
    for word, s, name in _STATS:
        if str_cmp(argument, word):
            stat, output = s, name
            break
    else:
        if not (str_cmp(argument, "hp") or str_cmp(argument, "mana")):
            buf = "You can train:"
            for word, s, _ in _STATS:
                if ch.perm_stat[s] < get_max_train(ch, s):
                    buf += " " + word
            buf += " hp mana"
            if buf[-1] != ":":  # always, since " hp mana" is there
                send_to_char(buf + ".\n\r", ch)
            else:
                # "This message dedicated to Jordan ... you big stud!"
                act("You have nothing left to train, you $T!", ch, None,
                    "big stud" if ch.sex == C.SEX_MALE else "hot babe" if ch.sex == C.SEX_FEMALE else "wild thing",
                    C.TO_CHAR)
            return
    if str_cmp("hp", argument):
        if cost > ch.train:
            send_to_char("You don't have enough training sessions.\n\r", ch)
            return
        ch.train = sh_int(ch.train - cost)
        ch.pcdata.perm_hit = sh_int(ch.pcdata.perm_hit + 10)
        ch.max_hit = sh_int(ch.max_hit + 10)
        ch.hit = sh_int(ch.hit + 10)
        act("Your durability increases!", ch, None, None, C.TO_CHAR)
        act("$n's durability increases!", ch, None, None, C.TO_ROOM)
        return
    if str_cmp("mana", argument):
        if cost > ch.train:
            send_to_char("You don't have enough training sessions.\n\r", ch)
            return
        ch.train = sh_int(ch.train - cost)
        ch.pcdata.perm_mana = sh_int(ch.pcdata.perm_mana + 10)
        ch.max_mana = sh_int(ch.max_mana + 10)
        ch.mana = sh_int(ch.mana + 10)
        act("Your power increases!", ch, None, None, C.TO_CHAR)
        act("$n's power increases!", ch, None, None, C.TO_ROOM)
        return
    if ch.perm_stat[stat] >= get_max_train(ch, stat):
        act("Your $T is already at maximum.", ch, None, output, C.TO_CHAR)
        return
    if cost > ch.train:
        send_to_char("You don't have enough training sessions.\n\r", ch)
        return
    ch.train = sh_int(ch.train - cost)
    ch.perm_stat[stat] = sh_int(ch.perm_stat[stat] + 1)
    act("Your $T increases!", ch, None, output, C.TO_CHAR)
    act("$n's $T increases!", ch, None, output, C.TO_ROOM)


# C: act_enter.c get_random_room
def get_random_room(ch):
    """'random room generation procedure'. Loops until it finds one, as the C does."""
    from charm.core.rng import number_range
    from charm.entities import game as game_module
    from charm.entities.handler import can_see_room, room_is_private

    index = game_module.current.index
    while True:
        room = index.get_room_index(number_range(0, 65535))
        if (room is not None and can_see_room(ch, room) and not room_is_private(room)
                and not room.room_flags & (C.ROOM_PRIVATE | C.ROOM_SOLITARY | C.ROOM_SAFE)
                and (ch.is_npc or ch.act & C.ACT_AGGRESSIVE or not room.room_flags & C.ROOM_LAW)):
            return room


# C: act_enter.c do_enter
def do_enter(ch, argument: str) -> None:
    """'RT Enter portals'."""
    from charm.commands.info import do_look
    from charm.core.rng import number_percent
    from charm.entities import game as game_module
    from charm.entities.handler import (can_see_room, char_from_room, char_to_room, extract_obj, get_trust,
                                        is_affected, next_in_room, obj_from_room, obj_to_room, room_is_private)
    from charm.systems.mobprog import has_trigger, mp_greet_trigger, mp_percent_trigger

    game = game_module.current
    if ch.fighting is not None:
        return
    if argument == "":
        send_to_char("Nope, can't do it.\n\r", ch)
        return
    # "nifty portal stuff"
    old_room = ch.in_room
    portal = _furniture(ch, argument)
    if portal is None:
        send_to_char("You don't see that here.\n\r", ch)
        return
    if portal.item_type != C.ITEM_PORTAL or (portal.value[1] & C.EX_CLOSED and not get_trust(ch) >= C.ANGEL):
        send_to_char("You can't seem to find a way in.\n\r", ch)
        return
    if (not get_trust(ch) >= C.ANGEL and not portal.value[2] & C.GATE_NOCURSE
            and (is_affected(ch, C.AFF_CURSE) or old_room.room_flags & C.ROOM_NO_RECALL)):
        send_to_char("Something prevents you from leaving...\n\r", ch)
        return
    if portal.value[2] & C.GATE_RANDOM or portal.value[3] == -1:
        location = get_random_room(ch)
        portal.value[3] = location.vnum  # "for record keeping :)"
    elif portal.value[2] & C.GATE_BUGGY and number_percent() < 5:
        location = get_random_room(ch)
    else:
        location = game.index.get_room_index(portal.value[3])
    if (location is None or location is old_room or not can_see_room(ch, location)
            or (room_is_private(location) and not get_trust(ch) >= C.IMPLEMENTOR)):
        act("$p doesn't seem to go anywhere.", ch, portal, None, C.TO_CHAR)
        return
    if ch.is_npc and ch.act & C.ACT_AGGRESSIVE and location.room_flags & C.ROOM_LAW:
        send_to_char("Something prevents you from leaving...\n\r", ch)
        return

    act("$n steps into $p.", ch, portal, None, C.TO_ROOM)
    if portal.value[2] & C.GATE_NORMAL_EXIT:
        act("You enter $p.", ch, portal, None, C.TO_CHAR)
    else:
        act("You walk through $p and find yourself somewhere else...", ch, portal, None, C.TO_CHAR)
    char_from_room(ch)
    char_to_room(ch, location)
    if portal.value[2] & C.GATE_GOWITH:  # "take the gate along"
        obj_from_room(portal)
        obj_to_room(portal, location)
    if portal.value[2] & C.GATE_NORMAL_EXIT:
        act("$n has arrived.", ch, portal, None, C.TO_ROOM)
    else:
        act("$n has arrived through $p.", ch, portal, None, C.TO_ROOM)
    do_look(ch, "auto")

    if portal.value[0] > 0:  # "charges"
        portal.value[0] -= 1
        if portal.value[0] == 0:
            portal.value[0] = -1
    if old_room is location:  # "protect against circular follows"
        return

    fch = old_room.people[0] if old_room.people else None
    while fch is not None:
        fch_next = next_in_room(fch)
        if portal.value[0] == -1:  # "no following through dead portals"
            fch = fch_next
            continue
        if fch.master is ch and is_affected(fch, C.AFF_CHARM) and fch.position < C.POS_STANDING:
            do_stand(fch, "")
        if fch.master is ch and fch.position == C.POS_STANDING:
            if ch.in_room.room_flags & C.ROOM_LAW and fch.is_npc and fch.act & C.ACT_AGGRESSIVE:
                act("You can't bring $N into the city.", ch, None, fch, C.TO_CHAR)
                act("You aren't allowed in the city.", fch, None, None, C.TO_CHAR)
                fch = fch_next
                continue
            act("You follow $N.", fch, None, ch, C.TO_CHAR)
            do_enter(fch, argument)
            if not any(o is portal for o in game.object_list):
                # The follower took the last charge and extract_obj freed the portal; the C reads it on (#42).
                raise CWouldCrash("act_enter.c do_enter: a follower used up the portal, and the C reads it after "
                                  "extract_obj freed it")
        fch = fch_next

    if portal.value[0] == -1:
        act("$p fades out of existence.", ch, portal, None, C.TO_CHAR)
        if ch.in_room is old_room:
            act("$p fades out of existence.", ch, portal, None, C.TO_ROOM)
        elif old_room.people:
            act("$p fades out of existence.", old_room.people[0], portal, None, C.TO_CHAR)
            act("$p fades out of existence.", old_room.people[0], portal, None, C.TO_ROOM)
        extract_obj(game, portal)

    # "If someone is following the char, these triggers get activated for the followers before the char, but
    # it's safer this way..."
    if ch.is_npc and has_trigger(ch, C.TRIG_ENTRY):
        mp_percent_trigger(ch, None, None, None, C.TRIG_ENTRY)
    if not ch.is_npc:
        mp_greet_trigger(ch)
