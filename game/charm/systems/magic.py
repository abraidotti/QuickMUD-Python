"""magic.c's obj_cast_spell: what potions, pills, scrolls, staves and wands call.

obj_cast_spell is [partial]: its checks are ported (no spell, a bad spell number or target, no victim, a safe
victim), so the commands that call it run as far as the C does before the spell. Casting the spell itself, and
TAR_OBJ_CHAR_OFF's check on a victim (fight.c's is_safe_spell), raise NotPorted: the spells are P4.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/magic.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import NotPorted
from charm.core.log import bug
from charm.data import constants as C
from charm.data.skills import SKILL_TABLE


def spell_fun(sn: int) -> str | None:
    """skill_table[sn].spell_fun for 0 <= sn < MAX_SKILL. The C array has MAX_SKILL rows and the table fills only
    the first ones, so the rest are zeros: no spell function."""
    return SKILL_TABLE[sn].spell_fun if sn < len(SKILL_TABLE) else None


# C: magic.c obj_cast_spell [partial]
def obj_cast_spell(sn: int, level: int, ch, victim, obj) -> None:
    """[partial]: the spell itself, and is_safe_spell for TAR_OBJ_CHAR_OFF on a victim, raise NotPorted."""
    from charm.net.output import send_to_char
    from charm.systems.fight import is_safe

    if sn <= 0:
        return
    if sn >= C.MAX_SKILL or spell_fun(sn) is None:
        bug("Obj_cast_spell: bad sn %d.", sn)
        return
    target = SKILL_TABLE[sn].target
    if target == C.TAR_IGNORE:
        pass
    elif target == C.TAR_CHAR_OFFENSIVE:
        if victim is None:
            victim = ch.fighting
        if victim is None:
            send_to_char("You can't do that.\n\r", ch)
            return
        if is_safe(ch, victim) and ch is not victim:
            send_to_char("Something isn't right...\n\r", ch)
            return
    elif target in (C.TAR_CHAR_DEFENSIVE, C.TAR_CHAR_SELF):
        pass
    elif target == C.TAR_OBJ_INV:
        if obj is None:
            send_to_char("You can't do that.\n\r", ch)
            return
    elif target == C.TAR_OBJ_CHAR_OFF:
        if victim is None and obj is None:
            if ch.fighting is None:
                send_to_char("You can't do that.\n\r", ch)
                return
            victim = ch.fighting
        if victim is not None:
            raise NotPorted("fight.c is_safe_spell (obj_cast_spell, %s)" % SKILL_TABLE[sn].name)
    elif target == C.TAR_OBJ_CHAR_DEF:
        pass
    else:
        bug("Obj_cast_spell: bad target for sn %d.", sn)
        return
    # (TAR_OBJ_CHAR_OFF on a victim stopped above, so only TAR_CHAR_OFFENSIVE can start a fight below.)
    if SKILL_TABLE[sn].spell_fun != "spell_null":
        raise NotPorted("magic.c obj_cast_spell: the spell %s (%s)" % (SKILL_TABLE[sn].name,
                                                                       SKILL_TABLE[sn].spell_fun))
    spell_null(sn, level, ch, victim, 0)
    if target == C.TAR_CHAR_OFFENSIVE and victim is not ch and victim.master is not ch:
        for vch in list(ch.in_room.people):
            if victim is vch and victim.fighting is None:
                raise NotPorted("fight.c check_killer and multi_hit (obj_cast_spell's victim fights back)")


# C: magic.c spell_null
def spell_null(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.net.output import send_to_char

    send_to_char("That's not a spell!\n\r", ch)
