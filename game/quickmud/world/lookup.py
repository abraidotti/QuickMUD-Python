"""Name lookups over the game's tables: race, position, sex, size, item type, liquid, weapon class, attack, skill,
clan, and the spell a character can use.

All of them are ROM's idiom (first letters equal ignoring case, and the name a prefix of the entry); they differ in
what they return when nothing matches, which is kept exactly.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/lookup.c, src/handler.c, src/magic.c. Licence terms:
README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.data import attacks, characters, constants, items, races, skills
from quickmud.world.areafile.lookups import prefix_lookup

_RACES = [r.name for r in races.RACE_TABLE]
_POSITIONS = [p.name for p in characters.POSITION_TABLE]
_SEXES = [s.name for s in characters.SEX_TABLE]
_SIZES = [s.name for s in races.SIZE_TABLE]
_ITEMS = [t.name for t in items.ITEM_TABLE]
_LIQUIDS = [q.liq_name for q in items.LIQ_TABLE]
_WEAPONS = [w.name for w in items.WEAPON_TABLE]
_ATTACKS = [a.name for a in attacks.ATTACK_TABLE]
_SKILLS = [s.name for s in skills.SKILL_TABLE]


# C: lookup.c race_lookup
def race_lookup(name: str) -> int:
    return max(prefix_lookup(name, _RACES), 0)  # not found: 0, the "unique" race


# C: lookup.c position_lookup
def position_lookup(name: str) -> int:
    return prefix_lookup(name, _POSITIONS)


# C: lookup.c sex_lookup
def sex_lookup(name: str) -> int:
    return prefix_lookup(name, _SEXES)


# C: lookup.c size_lookup
def size_lookup(name: str) -> int:
    return prefix_lookup(name, _SIZES)


# C: lookup.c item_lookup
def item_lookup(name: str) -> int:
    i = prefix_lookup(name, _ITEMS)
    return items.ITEM_TABLE[i].type if i >= 0 else -1


# C: lookup.c liq_lookup
def liq_lookup(name: str) -> int:
    return prefix_lookup(name, _LIQUIDS)


# C: handler.c weapon_type
def weapon_type(name: str) -> int:
    i = prefix_lookup(name, _WEAPONS)
    return items.WEAPON_TABLE[i].type if i >= 0 else constants.WEAPON_EXOTIC


# C: handler.c attack_lookup
def attack_lookup(name: str) -> int:
    return max(prefix_lookup(name, _ATTACKS), 0)  # not found: 0, "none"


# C: magic.c skill_lookup
def skill_lookup(name: str) -> int:
    return prefix_lookup(name, _SKILLS)


# The gsn globals boot_db fills in ("Assign gsn's for skills which have them"): each skill_table row whose pgsn is
# &gsn_x makes gsn_x its number. weapon_table names its skill that way too ("gsn_dagger").
GSN = {s.pgsn: sn for sn, s in enumerate(skills.SKILL_TABLE) if s.pgsn}


# C: handler.c class_lookup
def class_lookup(name: str) -> int:
    from quickmud.data.classes import CLASS_TABLE
    return prefix_lookup(name, [c.name for c in CLASS_TABLE])


# C: lookup.c clan_lookup
def clan_lookup(name: str) -> int:
    from quickmud.data.clans import CLAN_TABLE
    return max(prefix_lookup(name, [c.name for c in CLAN_TABLE]), 0)  # not found: 0, no clan


# C: magic.c find_spell
def find_spell(ch, name: str) -> int:
    """A skill ch can use if one matches; failing that, the first that matches; or -1."""
    if ch.is_npc:
        return skill_lookup(name)
    found = -1
    for sn, skill in enumerate(skills.SKILL_TABLE):
        if prefix_lookup(name, [skill.name]) == 0:
            if found == -1:
                found = sn
            if ch.level >= skill.skill_level[ch.class_] and ch.pcdata.learned[sn] > 0:
                return sn
    return found


# C: handler.c weapon_lookup
def weapon_lookup(name: str) -> int:
    """The weapon_table row (not its WEAPON_ value), or -1."""
    return prefix_lookup(name, _WEAPONS)


# C: special.c spec_lookup
def spec_lookup(name: str) -> str | None:
    """The special procedure (its function's name, as a mob's spec_fun holds it) whose spec_table name starts
    with name, or None."""
    from quickmud.core.strings import lower, str_prefix
    from quickmud.data.specials import SPEC_TABLE

    for s in SPEC_TABLE:
        if lower(name[:1]) == lower(s.name[:1]) and str_prefix(name, s.name):
            return s.function
    return None


# C: special.c spec_name
def spec_name(function: str) -> str | None:
    """The spec_table name of a special procedure, or None (a mob's spec_fun holds the function's name)."""
    from quickmud.data.specials import SPEC_TABLE

    return next((s.name for s in SPEC_TABLE if s.function == function), None)


# C: lookup.c flag_lookup
def flag_lookup(name: str, table) -> int:
    """The bit of the first flag whose name starts with name, or NO_FLAG (-99, which IS_SET finds set in nearly
    every value)."""
    from quickmud.core.strings import lower, str_prefix
    from quickmud.data import constants as C

    for flag in table:
        if name and lower(name[0]) == lower(flag.name[0]) and str_prefix(name, flag.name):
            return flag.bit
    return C.NO_FLAG
