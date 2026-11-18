"""act_move.c's walking: move_char and the six direction commands.

[partial] in one branch: a charmed follower who isn't standing is stood up with do_stand, which isn't ported and
raises NotPorted. Exit, greet and entry triggers are scanned (charm.systems.mobprog); running one isn't ported,
and no stock area has any.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_move.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div
from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.data import constants as C
from charm.data.classes import CLASS_TABLE
from charm.net.act import act
from charm.net.output import send_to_char

DIR_NAME = ("north", "east", "south", "west", "up", "down")
REV_DIR = (2, 3, 0, 1, 5, 4)
MOVEMENT_LOSS = (1, 2, 2, 3, 4, 6, 4, 1, 6, 10, 6)  # by sector type


# C: act_move.c move_char [partial]
def move_char(ch, door: int, follow: bool) -> None:
    """[partial]: standing up a charmed follower (do_stand) raises NotPorted."""
    from charm.commands.comm import wait_state
    from charm.commands.info import do_look
    from charm.entities.handler import (can_see_room, char_from_room, char_to_room, get_trust, is_affected,
                                        is_immortal, is_room_owner, room_is_private)
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
    for fch in list(in_room.people):
        if fch.master is ch and is_affected(fch, C.AFF_CHARM) and fch.position < C.POS_STANDING:
            raise NotPorted("act_move.c move_char: do_stand (a charmed follower who isn't standing)")
        if fch.master is ch and fch.position == C.POS_STANDING and can_see_room(fch, to_room):
            if ch.in_room.room_flags & C.ROOM_LAW and fch.is_npc and fch.act & C.ACT_AGGRESSIVE:
                act("You can't bring $N into the city.", ch, None, fch, C.TO_CHAR)
                act("You aren't allowed in the city.", fch, None, None, C.TO_CHAR)
                continue
            act("You follow $N.", fch, None, ch, C.TO_CHAR)
            move_char(fch, door, True)

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
