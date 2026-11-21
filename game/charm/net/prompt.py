"""bust_a_prompt: a playing character's prompt, from their prompt string's % codes.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.entities.handler import can_see_room, is_affected, is_evil, is_good, is_immortal, room_is_dark
from charm.net.output import colourconv, send_to_char, write_to_buffer

DIR_NAME = ("N", "E", "S", "W", "U", "D")


def _exits(ch) -> str:
    doors = ""
    for door in range(6):
        ex = ch.in_room.exit[door]
        if (ex is not None and ex.to_room is not None
                and (can_see_room(ch, ex.to_room)
                     or (is_affected(ch, C.AFF_INFRARED) and not is_affected(ch, C.AFF_BLIND)))
                and not ex.exit_info & C.EX_CLOSED):
            doors += DIR_NAME[door]
    return doors or "none"


def _code(code: str, ch) -> str:
    if code == "e":
        return _exits(ch)
    if code == "c":
        return "\n\r"
    numbers = {"h": "hit", "H": "max_hit", "m": "mana", "M": "max_mana", "v": "move", "V": "max_move",
               "x": "exp", "W": "wait", "g": "gold", "s": "silver"}
    if code in numbers:
        return str(getattr(ch, numbers[code]))
    if code == "X":
        if ch.is_npc:
            return "0"
        from charm.systems.skills import exp_per_level

        return "%d" % ((ch.level + 1) * exp_per_level(ch, ch.pcdata.points) - ch.exp)
    if code == "a":
        if ch.level > 9:
            return str(ch.alignment)
        return "good" if is_good(ch) else "evil" if is_evil(ch) else "neutral"
    if code == "r":
        if ch.in_room is None:
            return " "
        seen = (not ch.is_npc and ch.act & C.PLR_HOLYLIGHT) or (
            not is_affected(ch, C.AFF_BLIND) and not room_is_dark(ch.in_room))
        return ch.in_room.name if seen else "darkness"
    if code == "R":
        return str(ch.in_room.vnum) if is_immortal(ch) and ch.in_room is not None else " "
    if code == "z":
        return ch.in_room.area.name if is_immortal(ch) and ch.in_room is not None else " "
    if code == "%":
        return "%"
    if code == "o":
        from charm.olc.olc import olc_ed_name
        return olc_ed_name(ch)
    if code == "O":
        from charm.olc.olc import olc_ed_vnum
        return olc_ed_vnum(ch)
    return " "


# C: comm.c bust_a_prompt
def bust_a_prompt(ch) -> None:
    s = ch.prompt
    if s is None or s == "":
        send_to_char(f"{{p<{ch.hit}hp {ch.mana}m {ch.move}mv>{{x {ch.prefix}", ch)
        return
    if ch.comm & C.COMM_AFK:
        send_to_char("{p<AFK>{x ", ch)
        return
    out, i = [], 0
    while i < len(s):
        if s[i] != "%":
            out.append(s[i])
            i += 1
            continue
        i += 1
        out.append(_code(s[i] if i < len(s) else "\0", ch))
        i += 1
    buffer = colourconv("".join(out), ch)
    send_to_char("{p", ch)
    write_to_buffer(ch.desc, buffer)
    send_to_char("{x", ch)
    if ch.prefix:
        write_to_buffer(ch.desc, ch.prefix)
