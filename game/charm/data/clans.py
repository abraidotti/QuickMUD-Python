"""Clans.

Generated from the C by charm_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: clan_table (tables.c). A C table that ends with a NULL sentinel row is scanned up to it; that row isn't
here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/tables.c. Licence terms: README.md#licence-terms and doc/.
"""

from charm.data.structs import ClanType

# clan_table, tables.c
CLAN_TABLE = (
    ClanType(name="", who_name="", hall=3054, independent=True),
    ClanType(name="loner", who_name="[ Loner ] ", hall=3054, independent=True),
    ClanType(name="rom", who_name="[  ROM  ] ", hall=3054, independent=False),
)
