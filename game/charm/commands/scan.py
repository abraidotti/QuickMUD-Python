"""scan.c: the scan command, which lists who's in this room and the rooms beyond its exits.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/scan.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.errors import CWouldCrash
from charm.core.strings import str_cmp
from charm.data import constants as C
from charm.net.act import act
from charm.net.output import send_to_char

DISTANCE = ("right here.", "nearby to the %s.", "not far %s.", "off in the distance %s.")
_DOORS = (("n", "north"), ("e", "east"), ("s", "south"), ("w", "west"), ("u", "up"), ("d", "down"))


# C: scan.c do_scan
def do_scan(ch, argument: str) -> None:
    """scan: this room and the next one each way; scan <direction>: three rooms that way. Doors don't stop it, and
    the "Looking <direction> you see:" line is made and never sent."""
    from charm.commands.move import DIR_NAME

    _, arg1 = one_argument(argument)
    if arg1 == "":
        act("$n looks all around.", ch, None, None, C.TO_ROOM)
        send_to_char("Looking around you see:\n\r", ch)
        scan_list(ch.in_room, ch, 0, -1)
        for door in range(6):
            ex = ch.in_room.exit[door]
            if ex is not None:
                scan_list(ex.to_room, ch, 1, door)
        return
    door = next((k for k, (short, full) in enumerate(_DOORS) if str_cmp(arg1, short) or str_cmp(arg1, full)), None)
    if door is None:
        send_to_char("Which way do you want to scan?\n\r", ch)
        return
    act("You peer intently $T.", ch, None, DIR_NAME[door], C.TO_CHAR)
    act("$n peers intently $T.", ch, None, DIR_NAME[door], C.TO_ROOM)
    room = ch.in_room
    for depth in range(1, 4):
        if room is None:
            raise CWouldCrash("scan.c do_scan: an exit to no room, and the next look reads its exits")
        ex = room.exit[door]
        if ex is not None:
            room = ex.to_room
            scan_list(ex.to_room, ch, depth, door)


# C: scan.c scan_list
def scan_list(scan_room, ch, depth: int, door: int) -> None:
    from charm.entities.handler import can_see, get_trust

    if scan_room is None:
        return
    for rch in list(scan_room.people):
        if rch is ch:
            continue
        if not rch.is_npc and rch.invis_level > get_trust(ch):
            continue
        if can_see(ch, rch):
            scan_char(rch, ch, depth, door)


# C: scan.c scan_char
def scan_char(victim, ch, depth: int, door: int) -> None:
    from charm.commands.move import DIR_NAME
    from charm.entities.handler import pers

    where = DISTANCE[depth] % DIR_NAME[door] if depth else DISTANCE[0]  # format: sprintf
    send_to_char(pers(victim, ch) + ", " + where + "\n\r", ch)
