"""The tables boot_db's loaders look names up in, and ROM's name lookup idiom.

The loader used to read these from the C source at run time (T1). They now come from the generated charm.data
modules; charm_tools checks that the two agree (tools/tests/test_source.py).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/lookup.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass

from charm.core.strings import lower, str_prefix
from charm.data import clans, constants, items, mobprogs, races, skills, specials


class Constants(dict):
    """merc.h's constants by name, as the loader asks for them (``d["ITEM_WEAPON"]``)."""

    def with_prefix(self, prefix: str) -> dict[str, int]:
        """Every numeric constant whose name starts with prefix, e.g. with_prefix("OBJ_VNUM_")."""
        return {k: v for k, v in self.items() if k.startswith(prefix) and isinstance(v, int)}


@dataclass
class LookupTables:
    item_types: list[tuple[str, int]]  # (name, ITEM_ value), in item_table order
    weapon_types: list[tuple[str, int]]
    liquids: list[str]
    races: list[str]
    sizes: list[str]
    mprog_triggers: list[tuple[str, int]]
    clans: list[str]
    specials: list[str]
    defines: Constants
    slots: list[int]  # each skill's slot number (old-format objects name spells by it), by sn

    @classmethod
    def from_data(cls) -> "LookupTables":
        return cls(
            item_types=[(t.name, t.type) for t in items.ITEM_TABLE],
            weapon_types=[(w.name, w.type) for w in items.WEAPON_TABLE],
            liquids=[q.liq_name for q in items.LIQ_TABLE],
            races=[r.name for r in races.RACE_TABLE],
            sizes=[s.name for s in races.SIZE_TABLE],
            mprog_triggers=[(f.name, f.bit) for f in mobprogs.MPROG_FLAGS],
            clans=[c.name for c in clans.CLAN_TABLE],
            specials=[s.name for s in specials.SPEC_TABLE],
            defines=Constants({k: v for k, v in vars(constants).items() if k.isupper() and not k.startswith("_")}),
            slots=[s.slot for s in skills.SKILL_TABLE[:constants.MAX_SKILL]],
        )


def prefix_lookup(name: str, names: list[str]) -> int:
    """The ROM lookup idiom (item_lookup, liq_lookup, clan_lookup, ...): first letters equal, case-insensitively,
    and name a prefix of the entry (``!str_prefix(name, entry)``). Index of the first match, or -1. An empty name
    never matches."""
    if not name:
        return -1
    for i, entry in enumerate(names):
        if entry and lower(entry[0]) == lower(name[0]) and str_prefix(name, entry):
            return i
    return -1

