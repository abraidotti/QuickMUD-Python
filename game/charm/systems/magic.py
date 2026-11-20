"""magic.c's obj_cast_spell: what potions, pills, scrolls, staves and wands call.

obj_cast_spell is [partial]: its checks are ported (no spell, a bad spell number or target, no victim, a safe
victim), so the commands that call it run as far as the C does before the spell. Casting the spell itself raises
NotPorted: the spells are P4 (#74, PRs 3 and 4). saves_spell is here for fight.c's poisoned weapons.

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


# C: magic.c saves_spell
def saves_spell(level: int, victim, dam_type: int) -> bool:
    from charm.core.cint import c_div
    from charm.core.rng import number_percent
    from charm.data.classes import CLASS_TABLE
    from charm.entities.handler import check_immune, is_affected

    save = 50 + (victim.level - level) * 5 - victim.saving_throw * 2
    if is_affected(victim, C.AFF_BERSERK):
        save += c_div(victim.level, 2)
    kind = check_immune(victim, dam_type)
    if kind == C.IS_IMMUNE:
        return True
    if kind == C.IS_RESISTANT:
        save += 2
    elif kind == C.IS_VULNERABLE:
        save -= 2
    if not victim.is_npc and CLASS_TABLE[victim.class_].fMana:
        save = c_div(9 * save, 10)
    save = max(5, min(save, 95))
    return number_percent() < save


# C: magic.c obj_cast_spell [partial]
def obj_cast_spell(sn: int, level: int, ch, victim, obj) -> None:
    """[partial]: the spell itself raises NotPorted, but for spell_null."""
    from charm.net.output import send_to_char
    from charm.systems.fight import check_killer, is_safe, is_safe_spell, multi_hit

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
            if is_safe_spell(ch, victim, False) and ch is not victim:
                send_to_char("Somehting isn't right...\n\r", ch)  # sic: the C's spelling (#75)
                return
    elif target == C.TAR_OBJ_CHAR_DEF:
        pass
    else:
        bug("Obj_cast_spell: bad target for sn %d.", sn)
        return
    if SKILL_TABLE[sn].spell_fun != "spell_null":
        raise NotPorted("magic.c obj_cast_spell: the spell %s (%s)" % (SKILL_TABLE[sn].name,
                                                                       SKILL_TABLE[sn].spell_fun))
    spell_null(sn, level, ch, victim, 0)
    if ((target == C.TAR_CHAR_OFFENSIVE or (target == C.TAR_OBJ_CHAR_OFF and victim is not None))
            and victim is not ch and victim.master is not ch):
        for vch in list(ch.in_room.people):
            if victim is vch and victim.fighting is None:
                check_killer(victim, ch)
                multi_hit(victim, ch, C.TYPE_UNDEFINED)
                break


# C: magic.c spell_null
def spell_null(sn: int, level: int, ch, vo, target: int) -> None:
    from charm.net.output import send_to_char

    send_to_char("That's not a spell!\n\r", ch)
