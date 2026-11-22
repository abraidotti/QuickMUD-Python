"""Special procedures: the names area files can give a mob in #SPECIALS.

Generated from the C by charm_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: spec_table (special.c). A C table that ends with a NULL sentinel row is scanned up to it; that row isn't
here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/special.c. Licence terms: README.md#licence-terms and doc/.
"""

from charm.data.structs import SpecType

# spec_table, special.c
SPEC_TABLE = (
    SpecType(name="spec_breath_any", function="spec_breath_any"),
    SpecType(name="spec_breath_acid", function="spec_breath_acid"),
    SpecType(name="spec_breath_fire", function="spec_breath_fire"),
    SpecType(name="spec_breath_frost", function="spec_breath_frost"),
    SpecType(name="spec_breath_gas", function="spec_breath_gas"),
    SpecType(name="spec_breath_lightning", function="spec_breath_lightning"),
    SpecType(name="spec_cast_adept", function="spec_cast_adept"),
    SpecType(name="spec_cast_cleric", function="spec_cast_cleric"),
    SpecType(name="spec_cast_judge", function="spec_cast_judge"),
    SpecType(name="spec_cast_mage", function="spec_cast_mage"),
    SpecType(name="spec_cast_undead", function="spec_cast_undead"),
    SpecType(name="spec_executioner", function="spec_executioner"),
    SpecType(name="spec_fido", function="spec_fido"),
    SpecType(name="spec_guard", function="spec_guard"),
    SpecType(name="spec_janitor", function="spec_janitor"),
    SpecType(name="spec_mayor", function="spec_mayor"),
    SpecType(name="spec_poison", function="spec_poison"),
    SpecType(name="spec_thief", function="spec_thief"),
    SpecType(name="spec_nasty", function="spec_nasty"),
    SpecType(name="spec_troll_member", function="spec_troll_member"),
    SpecType(name="spec_ogre_member", function="spec_ogre_member"),
    SpecType(name="spec_patrolman", function="spec_patrolman"),
)
