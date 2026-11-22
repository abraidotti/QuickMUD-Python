"""act() and act_new: the game's "$n does something to $N" messages, sent to everyone in a room who should see one.

Ported line by line, the $ codes included. A message that reaches a mob with an ACT trigger goes to
mp_act_trigger (quickmud.systems.mobprog), which raises NotPorted if a program would run.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c, src/merc.h. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.log import bug
from quickmud.core.strings import upper
from quickmud.data import constants as C

HE_SHE = ("it", "he", "she")
HIM_HER = ("it", "him", "her")
HIS_HER = ("its", "his", "her")
MOB_TRIGGER = [True]  # MOBtrigger: act()'s switch for mob program triggers


def _sex(ch) -> int:
    return 0 if ch.sex < 0 else (2 if ch.sex > 2 else ch.sex)  # URANGE(0, sex, 2)


def _skip(to, ch, vch, kind: int, min_pos: int) -> bool:
    if (not to.is_npc and to.desc is None) or (to.is_npc and not to.index.mprog_flags & C.TRIG_ACT) \
            or to.position < min_pos:
        return True
    if kind == C.TO_CHAR and to is not ch:
        return True
    if kind == C.TO_VICT and (to is not vch or to is ch):
        return True
    if kind == C.TO_ROOM and to is ch:
        return True
    if kind == C.TO_NOTVICT and (to is ch or to is vch):
        return True
    return False


def _code(code: str, to, ch, arg1, arg2) -> str:
    from quickmud.commands.interp import one_argument
    from quickmud.entities.handler import can_see_obj, pers

    vch, obj1, obj2 = arg2, arg1, arg2
    i = " <@@@> "
    if arg2 is None and "A" <= code <= "Z":
        bug("Act: missing arg2 for code %d.", ord(code))
        return i
    if code == "t":
        if arg1 is not None:  # a pointer test: "" counts
            return arg1
        bug("Act: bad code $t for 'arg1'", 0)
    elif code == "T":
        if arg2 is not None:
            return arg2
        bug("Act: bad code $T for 'arg2'", 0)
    elif code == "n":
        if ch is not None and to is not None:
            return pers(ch, to)
        bug("Act: bad code $n for 'ch' or 'to'", 0)
    elif code == "N":
        if vch is not None and to is not None:
            return pers(vch, to)
        bug("Act: bad code $N for 'vch' or 'to'", 0)
    elif code and code in "eE":
        who = ch if code == "e" else vch
        if who is not None:
            return HE_SHE[_sex(who)]
        bug(f"Act: bad code ${code} for '{'ch' if code == 'e' else 'vch'}'", 0)
    elif code and code in "mM":
        who = ch if code == "m" else vch
        if who is not None:
            return HIM_HER[_sex(who)]
        bug(f"Act: bad code ${code} for '{'ch' if code == 'm' else 'vch'}'", 0)
    elif code and code in "sS":
        who = ch if code == "s" else vch
        if who is not None:
            return HIS_HER[_sex(who)]
        bug(f"Act: bad code ${code} for '{'ch' if code == 's' else 'vch'}'", 0)
    elif code == "p":
        if to is not None and obj1 is not None:
            return obj1.short_descr if can_see_obj(to, obj1) else "something"
        bug("Act: bad code $p for 'to' or 'obj1'", 0)
    elif code == "P":
        if to is not None and obj2 is not None:
            return obj2.short_descr if can_see_obj(to, obj2) else "something"
        bug("Act: bad code $P for 'to' or 'obj2'", 0)
    elif code == "d":
        if arg2 is None or arg2 == "":
            return "door"
        return one_argument(arg2)[1]
    else:
        bug("Act: bad code %d.", ord(code) if code else 0)
    return i


# C: comm.c act_new
def act_new(fmt: str | None, ch, arg1, arg2, kind: int, min_pos: int) -> None:
    from quickmud.net.output import colourconv, write_to_buffer

    if not fmt:  # discard null and zero-length messages
        return
    if ch is None or ch.in_room is None:  # discard null rooms and chars
        return
    people = ch.in_room.people
    vch = arg2
    if kind == C.TO_VICT:
        if vch is None:
            bug("Act: null vch with TO_VICT.", 0)
            return
        if vch.in_room is None:
            return
        people = vch.in_room.people

    for to in list(people):
        if _skip(to, ch, vch, kind, min_pos):
            continue
        out, i = [], 0
        while i < len(fmt):
            if fmt[i] != "$":
                out.append(fmt[i])
                i += 1
                continue
            i += 1
            code = fmt[i] if i < len(fmt) else ""
            out.append(_code(code, to, ch, arg1, arg2))
            i += 1  # past the code (past the end, for a '$' at the very end, where the C reads on)
        buf = "".join(out) + "\n\r"
        # "Kludge to capitalize first letter of buffer, trying to account for { color codes."
        k = 2 if buf[0] == "{" else 0
        if "a" <= buf[k] <= "z":
            buf = buf[:k] + upper(buf[k]) + buf[k + 1:]
        buffer = colourconv(buf, to)
        if to.desc is not None and to.desc.connected == C.CON_PLAYING:
            write_to_buffer(to.desc, buffer)
        elif MOB_TRIGGER[0]:
            from quickmud.systems.mobprog import mp_act_trigger
            mp_act_trigger(buf, to, ch, arg1, arg2, C.TRIG_ACT)


def act(fmt: str | None, ch, arg1, arg2, kind: int) -> None:
    """The act() macro: act_new at POS_RESTING."""
    act_new(fmt, ch, arg1, arg2, kind, C.POS_RESTING)
