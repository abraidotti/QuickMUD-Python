"""Name lookups over the game's tables: race, position, sex, size, item type, liquid, weapon class, attack, skill.

All of them are ROM's idiom (first letters equal ignoring case, and the name a prefix of the entry); they differ in
what they return when nothing matches, which is kept exactly.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/lookup.c, src/handler.c, src/magic.c. Licence terms:
README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import attacks, characters, constants, items, races, skills
from charm.world.areafile.lookups import prefix_lookup

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
