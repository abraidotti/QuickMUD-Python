"""bit.c: OLC's flag helpers. A table is a stat (one value, assigned) or a set of flags (bits, toggled), and
flag_value and flag_string read and write either kind by name.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/bit.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.data import flags as F

# flag_stat_table: (table, stat), in the C's order
FLAG_STAT_TABLE = (
    (F.AREA_FLAGS, False), (F.SEX_FLAGS, True), (F.EXIT_FLAGS, False), (F.DOOR_RESETS, True),
    (F.ROOM_FLAGS, False), (F.SECTOR_FLAGS, True), (F.TYPE_FLAGS, True), (F.EXTRA_FLAGS, False),
    (F.WEAR_FLAGS, False), (F.ACT_FLAGS, False), (F.AFFECT_FLAGS, False), (F.APPLY_FLAGS, True),
    (F.WEAR_LOC_FLAGS, True), (F.WEAR_LOC_STRINGS, True), (F.CONTAINER_FLAGS, False),
    # "ROM specific flags:"
    (F.FORM_FLAGS, False), (F.PART_FLAGS, False), (F.AC_TYPE, True), (F.SIZE_FLAGS, True),
    (F.POSITION_FLAGS, True), (F.OFF_FLAGS, False), (F.IMM_FLAGS, False), (F.RES_FLAGS, False),
    (F.VULN_FLAGS, False), (F.WEAPON_CLASS, True), (F.WEAPON_TYPE2, False), (F.APPLY_TYPES, True),
)


# C: bit.c is_stat
def is_stat(flag_table) -> bool:
    """True if the table is a stat table, False if it's flags (or isn't listed). Tables are compared by identity,
    as the C compares pointers."""
    return any(table is flag_table and stat for table, stat in FLAG_STAT_TABLE)


# C: bit.c flag_value
def flag_value(flag_table, argument: str) -> int:
    """The value of the flags named (several, for a flags table), or NO_FLAG if none is found."""
    from charm.commands.interp import one_argument
    from charm.world.lookup import flag_lookup

    if is_stat(flag_table):
        return flag_lookup(argument, flag_table)
    marked, found = 0, False
    while True:
        argument, word = one_argument(argument)
        if word == "":
            break
        bit = flag_lookup(word, flag_table)
        if bit != C.NO_FLAG:
            marked |= bit
            found = True
    return marked if found else C.NO_FLAG


# C: bit.c flag_string
def flag_string(flag_table, bits: int) -> str:
    """The names of the flags set in bits, space-separated, or a stat's name; "none" if there are none. (The C
    alternates two static buffers of 512 bytes; no table's names come near that.)"""
    names = []
    stat = is_stat(flag_table)
    for flag in flag_table:
        if not stat and bits & flag.bit:
            names.append(flag.name)
        elif flag.bit == bits:
            names.append(flag.name)
            break
    return " ".join(names) if names else "none"
