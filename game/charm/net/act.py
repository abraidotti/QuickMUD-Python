"""act() and act_new: the game's "$n does something to $N" messages, sent to everyone in a room who should see one.

[partial] for now: who receives a message is worked out exactly as the C does, but nobody can receive one yet. A
player needs a connection, which comes with the loop (spike PR 3). A mob receives a message only if it has an ACT
trigger, and running that needs mob programs. If anyone would receive a message, NotPorted is raised. When nobody
would (the common case at boot, such as a mob zapped by its own equipment), act() does nothing, as in the C.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c, src/merc.h. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.data import constants as C


def _receives(to, ch, vch, kind: int, min_pos: int) -> bool:
    if to.is_npc:
        if not to.index.mprog_flags & C.TRIG_ACT:  # HAS_TRIGGER(to, TRIG_ACT)
            return False
    elif getattr(to, "desc", None) is None:
        return False
    if to.position < min_pos:
        return False
    if kind == C.TO_CHAR and to is not ch:
        return False
    if kind == C.TO_VICT and (to is not vch or to is ch):
        return False
    if kind == C.TO_ROOM and to is ch:
        return False
    if kind == C.TO_NOTVICT and (to is ch or to is vch):
        return False
    return True


# C: comm.c act_new [partial]
def act_new(fmt: str | None, ch, arg1, arg2, kind: int, min_pos: int) -> None:
    if not fmt:
        return
    if ch is None or ch.in_room is None:
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
        if _receives(to, ch, vch, kind, min_pos):
            raise NotPorted("comm.c act_new: a message someone would receive (a connection, or a mob's ACT "
                            "trigger)")


def act(fmt: str | None, ch, arg1, arg2, kind: int) -> None:
    """The act() macro: act_new at POS_RESTING."""
    act_new(fmt, ch, arg1, arg2, kind, C.POS_RESTING)
