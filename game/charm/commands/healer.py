"""healer.c: do_heal, buying a spell from a healer mob (#74, P4 PR 5).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/healer.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.cint import c_div, sh_int
from charm.core.rng import dice
from charm.core.strings import str_prefix
from charm.data import constants as C
from charm.net.act import act
from charm.net.output import send_to_char

_PRICE_LIST = (
    "  light: cure light wounds      10 gold\n\r",
    "  serious: cure serious wounds  15 gold\n\r",
    "  critic: cure critical wounds  25 gold\n\r",
    "  heal: healing spell          50 gold\n\r",
    "  blind: cure blindness         20 gold\n\r",
    "  disease: cure disease         15 gold\n\r",
    "  poison:  cure poison          25 gold\n\r",
    "  uncurse: remove curse          50 gold\n\r",
    "  refresh: restore movement      5 gold\n\r",
    "  mana:  restore mana          10 gold\n\r",
    " Type heal <type> to be healed.\n\r",
)

# What each word buys, in the C's order: (the words that pick it, the spell's C name or None for mana, the skill,
# the words the healer utters, the cost in silver)
_SERVICES = (
    (("light",), "spell_cure_light", "cure light", "judicandus dies", 1000),
    (("serious",), "spell_cure_serious", "cure serious", "judicandus gzfuajg", 1600),
    (("critical",), "spell_cure_critical", "cure critical", "judicandus qfuhuqar", 2500),
    (("heal",), "spell_heal", "heal", "pzar", 5000),
    (("blindness",), "spell_cure_blindness", "cure blindness", "judicandus noselacri", 2000),
    (("disease",), "spell_cure_disease", "cure disease", "judicandus eugzagz", 1500),
    (("poison",), "spell_cure_poison", "cure poison", "judicandus sausabru", 2500),
    (("uncurse", "curse"), "spell_remove_curse", "remove curse", "candussido judifgz", 5000),
    (("mana", "energize"), None, None, "energizer", 1000),
    (("refresh", "moves"), "spell_refresh", "refresh", "candusima", 500),
)


# C: healer.c do_heal
def do_heal(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.entities.handler import deduct_cost
    from charm.systems.spells import SPELLS
    from charm.world.lookup import skill_lookup

    for mob in ch.in_room.people:  # "check for healer"
        if mob.is_npc and mob.act & C.ACT_IS_HEALER:
            break
    else:
        send_to_char("You can't do that here.\n\r", ch)
        return

    _, arg = one_argument(argument)
    if arg == "":
        act("$N says 'I offer the following spells:'", ch, None, mob, C.TO_CHAR)  # "display price list"
        for line in _PRICE_LIST:
            send_to_char(line, ch)
        return

    for words_for, spell_name, skill, words, cost in _SERVICES:
        if any(str_prefix(arg, w) for w in words_for):
            break
    else:
        act("$N says 'Type 'heal' for a list of spells.'", ch, None, mob, C.TO_CHAR)
        return
    sn = skill_lookup(skill) if skill is not None else -1

    if cost > ch.gold * 100 + ch.silver:
        act("$N says 'You do not have enough gold for my services.'", ch, None, mob, C.TO_CHAR)
        return

    wait_state(ch, C.PULSE_VIOLENCE)
    deduct_cost(ch, cost)
    mob.gold += c_div(cost, 100)
    mob.silver += cost % 100  # non-negative: a price
    act("$n utters the words '$T'.", mob, None, words, C.TO_ROOM)

    if spell_name is None:  # "restore mana trap...kinda hackish"
        ch.mana = sh_int(ch.mana + dice(2, 8) + c_div(mob.level, 3))
        ch.mana = min(ch.mana, ch.max_mana)
        send_to_char("A warm glow passes through you.\n\r", ch)
        return
    if sn == -1:
        return
    SPELLS[spell_name](sn, mob.level, mob, ch, C.TARGET_CHAR)
