"""magic.c but the spells: casting (do_cast), the magic items' casting (obj_cast_spell), the words a caster utters,
and the saving throws.

The spells are in quickmud.systems.spells, found by the C function's name (#74, PRs 3 and 4).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/magic.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div, sh_int
from quickmud.core.errors import NotPorted
from quickmud.core.log import bug
from quickmud.core.rng import number_percent
from quickmud.data import constants as C
from quickmud.data.skills import SKILL_TABLE


def spell_fun(sn: int) -> str | None:
    """skill_table[sn].spell_fun for 0 <= sn < MAX_SKILL. The C array has MAX_SKILL rows and the table fills only
    the first ones, so the rest are zeros: no spell function."""
    return SKILL_TABLE[sn].spell_fun if sn < len(SKILL_TABLE) else None


def cast_spell(sn: int, level: int, ch, vo, target: int) -> None:
    """(*skill_table[sn].spell_fun) (sn, level, ch, vo, target)."""
    from quickmud.systems.spells import SPELLS

    name = SKILL_TABLE[sn].spell_fun
    if name == "spell_null":
        spell_null(sn, level, ch, vo, target)
        return
    fn = SPELLS.get(name)
    if fn is None:
        raise NotPorted(f"magic.c {name} (the spell {SKILL_TABLE[sn].name})")
    fn(sn, level, ch, vo, target)


_SYLLABLES = (  # say_spell's syl_table, in order: the first that starts what's left of the name is used
    (" ", " "), ("ar", "abra"), ("au", "kada"), ("bless", "fido"), ("blind", "nose"), ("bur", "mosa"),
    ("cu", "judi"), ("de", "oculo"), ("en", "unso"), ("light", "dies"), ("lo", "hi"), ("mor", "zak"),
    ("move", "sido"), ("ness", "lacri"), ("ning", "illa"), ("per", "duda"), ("ra", "gru"), ("fresh", "ima"),
    ("re", "candus"), ("son", "sabru"), ("tect", "infra"), ("tri", "cula"), ("ven", "nofo"),
    ("a", "a"), ("b", "b"), ("c", "q"), ("d", "e"), ("e", "z"), ("f", "y"), ("g", "o"), ("h", "p"), ("i", "u"),
    ("j", "y"), ("k", "t"), ("l", "r"), ("m", "w"), ("n", "i"), ("o", "a"), ("p", "s"), ("q", "d"), ("r", "f"),
    ("s", "g"), ("t", "h"), ("u", "j"), ("v", "z"), ("w", "x"), ("x", "n"), ("y", "l"), ("z", "k"),
)


# C: magic.c say_spell
def say_spell(ch, sn: int) -> None:
    """"Utter mystical words for an sn": the real name to the caster's class, the garbled words to the rest."""
    from quickmud.core.strings import str_prefix
    from quickmud.net.act import act

    name = SKILL_TABLE[sn].name
    words = []
    i = 0
    while i < len(name):
        rest = name[i:]
        for old, new in _SYLLABLES:
            if str_prefix(old, rest):
                words.append(new)
                i += len(old)
                break
        else:
            i += 1  # no syllable: the letter is skipped
    buf2 = "$n utters the words, '%s'." % "".join(words)
    buf = "$n utters the words, '%s'." % name
    for rch in list(ch.in_room.people):
        if rch is not ch:
            act(buf if not rch.is_npc and ch.class_ == rch.class_ else buf2, ch, None, rch, C.TO_VICT)


# C: magic.c saves_spell
def saves_spell(level: int, victim, dam_type: int) -> bool:
    from quickmud.data.classes import CLASS_TABLE
    from quickmud.entities.handler import check_immune, is_affected

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


# C: magic.c saves_dispel
def saves_dispel(dis_level: int, spell_level: int, duration: int) -> bool:
    """"RT save for dispels"."""
    if duration == -1:
        spell_level += 5  # "very hard to dispel permanent effects"
    save = 50 + (spell_level - dis_level) * 5
    save = max(5, min(save, 95))
    return number_percent() < save


# C: magic.c check_dispel
def check_dispel(dis_level: int, victim, sn: int) -> bool:
    """"co-routine for dispel magic and cancellation": each of the spell's affects saves in turn (and is weakened
    by a level if it does) until one doesn't, which strips them all."""
    from quickmud.entities.handler import affect_strip, is_affected_by
    from quickmud.net.output import send_to_char

    if is_affected_by(victim, sn):
        for af in list(victim.affected):
            if af.type == sn:
                if not saves_dispel(dis_level, af.level, af.duration):
                    affect_strip(victim, sn)
                    if SKILL_TABLE[sn].msg_off is not None:  # a C pointer: an empty message still sends
                        send_to_char(SKILL_TABLE[sn].msg_off, victim)
                        send_to_char("\n\r", victim)
                    return True
                af.level = sh_int(af.level - 1)
    return False


def _fights_back(sn: int, ch, victim, target: int) -> None:
    """do_cast's and obj_cast_spell's ending: an offensive spell's victim, if it's still in the room and not
    fighting, attacks the caster."""
    from quickmud.systems.fight import check_killer, multi_hit

    kind = SKILL_TABLE[sn].target
    if ((kind == C.TAR_CHAR_OFFENSIVE or (kind == C.TAR_OBJ_CHAR_OFF and target == C.TARGET_CHAR))
            and victim is not ch and victim.master is not ch):
        if ch.in_room is None:
            from quickmud.core.errors import CWouldCrash

            raise CWouldCrash("magic.c: the spell freed its caster, and the C reads the caster's room")
        for vch in list(ch.in_room.people):
            if victim is vch and victim.fighting is None:
                check_killer(victim, ch)
                multi_hit(victim, ch, C.TYPE_UNDEFINED)
                break


# C: magic.c do_cast
def do_cast(ch, argument: str) -> None:
    from quickmud.commands.comm import wait_state
    from quickmud.commands.interp import one_argument
    from quickmud.data.classes import CLASS_TABLE
    from quickmud.entities import game as game_module
    from quickmud.entities.handler import (get_char_room, get_obj_carry, get_obj_here, get_skill, is_affected,
                                        is_name)
    from quickmud.net.output import send_to_char
    from quickmud.systems.fight import check_killer, is_safe, is_safe_spell
    from quickmud.systems.skills import check_improve
    from quickmud.world.lookup import find_spell

    game = game_module.current
    # "Switched NPC's can cast spells, but others can't."
    if ch.is_npc and ch.desc is None:
        return
    target_name, arg1 = one_argument(argument)
    game.target_name = target_name
    _, arg2 = one_argument(target_name)
    if arg1 == "":
        send_to_char("Cast which what where?\n\r", ch)
        return
    sn = find_spell(ch, arg1)
    if (sn < 1 or SKILL_TABLE[sn].spell_fun == "spell_null"
            or (not ch.is_npc and (ch.level < SKILL_TABLE[sn].skill_level[ch.class_]
                                   or ch.pcdata.learned[sn] == 0))):
        send_to_char("You don't know any spells of that name.\n\r", ch)
        return
    skill = SKILL_TABLE[sn]
    if ch.position < skill.minimum_position:
        send_to_char("You can't concentrate enough.\n\r", ch)
        return
    if ch.level + 2 == skill.skill_level[ch.class_]:
        mana = 50
    else:
        mana = max(skill.min_mana, c_div(100, 2 + ch.level - skill.skill_level[ch.class_]))

    # "Locate targets."
    victim = None
    vo = None
    target = C.TARGET_NONE
    kind = skill.target
    if kind == C.TAR_IGNORE:
        pass
    elif kind == C.TAR_CHAR_OFFENSIVE:
        if arg2 == "":
            victim = ch.fighting
            if victim is None:
                send_to_char("Cast the spell on whom?\n\r", ch)
                return
        else:
            victim = get_char_room(ch, target_name)
            if victim is None:
                send_to_char("They aren't here.\n\r", ch)
                return
        # (The C's "You can't do that to yourself." is commented out.)
        if not ch.is_npc:
            if is_safe(ch, victim) and victim is not ch:
                send_to_char("Not on that target.\n\r", ch)
                return
            check_killer(ch, victim)
        if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
            send_to_char("You can't do that on your own follower.\n\r", ch)
            return
        vo = victim
        target = C.TARGET_CHAR
    elif kind == C.TAR_CHAR_DEFENSIVE:
        if arg2 == "":
            victim = ch
        else:
            victim = get_char_room(ch, target_name)
            if victim is None:
                send_to_char("They aren't here.\n\r", ch)
                return
        vo = victim
        target = C.TARGET_CHAR
    elif kind == C.TAR_CHAR_SELF:
        if arg2 != "" and not is_name(target_name, ch.name):
            send_to_char("You cannot cast this spell on another.\n\r", ch)
            return
        vo = ch
        target = C.TARGET_CHAR
    elif kind == C.TAR_OBJ_INV:
        if arg2 == "":
            send_to_char("What should the spell be cast upon?\n\r", ch)
            return
        obj = get_obj_carry(ch, target_name, ch)
        if obj is None:
            send_to_char("You are not carrying that.\n\r", ch)
            return
        vo = obj
        target = C.TARGET_OBJ
    elif kind == C.TAR_OBJ_CHAR_OFF:
        if arg2 == "":
            victim = ch.fighting
            if victim is None:
                send_to_char("Cast the spell on whom or what?\n\r", ch)
                return
            target = C.TARGET_CHAR
        else:
            victim = get_char_room(ch, target_name)
            if victim is not None:
                target = C.TARGET_CHAR
        if target == C.TARGET_CHAR:  # "check the sanity of the attack"
            if is_safe_spell(ch, victim, False) and victim is not ch:
                send_to_char("Not on that target.\n\r", ch)
                return
            if is_affected(ch, C.AFF_CHARM) and ch.master is victim:
                send_to_char("You can't do that on your own follower.\n\r", ch)
                return
            if not ch.is_npc:
                check_killer(ch, victim)
            vo = victim
        else:
            obj = get_obj_here(ch, target_name)
            if obj is None:
                send_to_char("You don't see that here.\n\r", ch)
                return
            vo = obj
            target = C.TARGET_OBJ
    elif kind == C.TAR_OBJ_CHAR_DEF:
        if arg2 == "":
            vo = ch
            target = C.TARGET_CHAR
        else:
            victim = get_char_room(ch, target_name)
            if victim is not None:
                vo = victim
                target = C.TARGET_CHAR
            else:
                obj = get_obj_carry(ch, target_name, ch)
                if obj is None:
                    send_to_char("You don't see that here.\n\r", ch)
                    return
                vo = obj
                target = C.TARGET_OBJ
    else:
        bug("Do_cast: bad target for sn %d.", sn)
        return

    if not ch.is_npc and ch.mana < mana:
        send_to_char("You don't have enough mana.\n\r", ch)
        return
    if skill.name != "ventriloquate":  # str_cmp: the C's compare is case-blind, and names are lower case
        say_spell(ch, sn)
    wait_state(ch, skill.beats)
    if number_percent() > get_skill(ch, sn):
        send_to_char("You lost your concentration.\n\r", ch)
        check_improve(ch, sn, False, 1)
        ch.mana = sh_int(ch.mana - c_div(mana, 2))
    else:
        ch.mana = sh_int(ch.mana - mana)
        if ch.is_npc or CLASS_TABLE[ch.class_].fMana:  # "class has spells"
            cast_spell(sn, ch.level, ch, vo, target)
        else:
            cast_spell(sn, c_div(3 * ch.level, 4), ch, vo, target)
        check_improve(ch, sn, True, 1)
    _fights_back(sn, ch, victim, target)


# C: magic.c obj_cast_spell
def obj_cast_spell(sn: int, level: int, ch, victim, obj) -> None:
    """"Cast spells at targets using a magical object."."""
    from quickmud.entities import game as game_module
    from quickmud.net.output import send_to_char
    from quickmud.systems.fight import is_safe, is_safe_spell

    if sn <= 0:
        return
    if sn >= C.MAX_SKILL or spell_fun(sn) is None:
        bug("Obj_cast_spell: bad sn %d.", sn)
        return
    vo = None
    target = C.TARGET_NONE
    kind = SKILL_TABLE[sn].target
    if kind == C.TAR_IGNORE:
        vo = None
    elif kind == C.TAR_CHAR_OFFENSIVE:
        if victim is None:
            victim = ch.fighting
        if victim is None:
            send_to_char("You can't do that.\n\r", ch)
            return
        if is_safe(ch, victim) and ch is not victim:
            send_to_char("Something isn't right...\n\r", ch)
            return
        vo = victim
        target = C.TARGET_CHAR
    elif kind in (C.TAR_CHAR_DEFENSIVE, C.TAR_CHAR_SELF):
        if victim is None:
            victim = ch
        vo = victim
        target = C.TARGET_CHAR
    elif kind == C.TAR_OBJ_INV:
        if obj is None:
            send_to_char("You can't do that.\n\r", ch)
            return
        vo = obj
        target = C.TARGET_OBJ
    elif kind == C.TAR_OBJ_CHAR_OFF:
        if victim is None and obj is None:
            if ch.fighting is None:
                send_to_char("You can't do that.\n\r", ch)
                return
            victim = ch.fighting
        if victim is not None:
            if is_safe_spell(ch, victim, False) and ch is not victim:
                send_to_char("Somehting isn't right...\n\r", ch)  # sic: the C's spelling (#75)
                return
            vo = victim
            target = C.TARGET_CHAR
        else:
            vo = obj
            target = C.TARGET_OBJ
    elif kind == C.TAR_OBJ_CHAR_DEF:
        if victim is None and obj is None:
            vo = ch
            target = C.TARGET_CHAR
        elif victim is not None:
            vo = victim
            target = C.TARGET_CHAR
        else:
            vo = obj
            target = C.TARGET_OBJ
    else:
        bug("Obj_cast_spell: bad target for sn %d.", sn)
        return
    game_module.current.target_name = ""
    cast_spell(sn, level, ch, vo, target)
    _fights_back(sn, ch, victim, target)


# C: magic.c spell_null
def spell_null(sn: int, level: int, ch, vo, target: int) -> None:
    from quickmud.net.output import send_to_char

    send_to_char("That's not a spell!\n\r", ch)


# C: magic.c slot_lookup
def slot_lookup(slot: int, booting: bool = False) -> int:
    """The sn of the skill with this slot number (old-format objects name their spells by slot), or -1. While the
    world boots (fBootDb) a slot that isn't there stops the game (bug, then abort)."""
    from quickmud.core.log import bug

    if slot <= 0:
        return -1
    for sn, skill in enumerate(SKILL_TABLE[:C.MAX_SKILL]):
        if slot == skill.slot:
            return sn
    if booting:
        bug("Slot_lookup: bad slot %d.", slot)
        raise SystemExit("magic.c slot_lookup: abort ()")
    return -1
