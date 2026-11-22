"""Attack types: the damage nouns a mob's or weapon's attack word is looked up in.

Generated from the C by charm_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: attack_table (const.c). A C table that ends with a NULL sentinel row is scanned up to it; that row isn't
here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/const.c. Licence terms: README.md#licence-terms and doc/.
"""

from charm.data.structs import AttackType

# attack_table, const.c
ATTACK_TABLE = (
    AttackType(name="none", noun="hit", damage=-1),
    AttackType(name="slice", noun="slice", damage=3),
    AttackType(name="stab", noun="stab", damage=2),
    AttackType(name="slash", noun="slash", damage=3),
    AttackType(name="whip", noun="whip", damage=3),
    AttackType(name="claw", noun="claw", damage=3),
    AttackType(name="blast", noun="blast", damage=1),
    AttackType(name="pound", noun="pound", damage=1),
    AttackType(name="crush", noun="crush", damage=1),
    AttackType(name="grep", noun="grep", damage=3),
    AttackType(name="bite", noun="bite", damage=2),
    AttackType(name="pierce", noun="pierce", damage=2),
    AttackType(name="suction", noun="suction", damage=1),
    AttackType(name="beating", noun="beating", damage=1),
    AttackType(name="digestion", noun="digestion", damage=7),
    AttackType(name="charge", noun="charge", damage=1),
    AttackType(name="slap", noun="slap", damage=1),
    AttackType(name="punch", noun="punch", damage=1),
    AttackType(name="wrath", noun="wrath", damage=11),
    AttackType(name="magic", noun="magic", damage=11),
    AttackType(name="divine", noun="divine power", damage=10),
    AttackType(name="cleave", noun="cleave", damage=3),
    AttackType(name="scratch", noun="scratch", damage=2),
    AttackType(name="peck", noun="peck", damage=2),
    AttackType(name="peckb", noun="peck", damage=1),
    AttackType(name="chop", noun="chop", damage=3),
    AttackType(name="sting", noun="sting", damage=2),
    AttackType(name="smash", noun="smash", damage=1),
    AttackType(name="shbite", noun="shocking bite", damage=6),
    AttackType(name="flbite", noun="flaming bite", damage=4),
    AttackType(name="frbite", noun="freezing bite", damage=5),
    AttackType(name="acbite", noun="acidic bite", damage=7),
    AttackType(name="chomp", noun="chomp", damage=2),
    AttackType(name="drain", noun="life drain", damage=9),
    AttackType(name="thrust", noun="thrust", damage=2),
    AttackType(name="slime", noun="slime", damage=7),
    AttackType(name="shock", noun="shock", damage=6),
    AttackType(name="thwack", noun="thwack", damage=1),
    AttackType(name="flame", noun="flame", damage=4),
    AttackType(name="chill", noun="chill", damage=5),
)
