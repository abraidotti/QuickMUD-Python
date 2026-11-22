"""Positions, sexes and wiznet's options.

Generated from the C by quickmud_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: position_table (tables.c), sex_table (tables.c), wiznet_table (const.c). A C table that ends with a NULL
sentinel row is scanned up to it; that row isn't here.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/const.c, src/tables.c. Licence terms: README.md#licence-terms and doc/.
"""

from quickmud.data.structs import PositionType, SexType, WiznetType

# position_table, tables.c
POSITION_TABLE = (
    PositionType(name="dead", short_name="dead"),
    PositionType(name="mortally wounded", short_name="mort"),
    PositionType(name="incapacitated", short_name="incap"),
    PositionType(name="stunned", short_name="stun"),
    PositionType(name="sleeping", short_name="sleep"),
    PositionType(name="resting", short_name="rest"),
    PositionType(name="sitting", short_name="sit"),
    PositionType(name="fighting", short_name="fight"),
    PositionType(name="standing", short_name="stand"),
)

# sex_table, tables.c
SEX_TABLE = (
    SexType(name="none"),
    SexType(name="male"),
    SexType(name="female"),
    SexType(name="either"),
)

# wiznet_table, const.c
WIZNET_TABLE = (
    WiznetType(name="on", flag=1, level=52),
    WiznetType(name="prefix", flag=262144, level=52),
    WiznetType(name="ticks", flag=2, level=52),
    WiznetType(name="logins", flag=4, level=52),
    WiznetType(name="sites", flag=8, level=56),
    WiznetType(name="links", flag=16, level=53),
    WiznetType(name="newbies", flag=131072, level=52),
    WiznetType(name="spam", flag=524288, level=55),
    WiznetType(name="deaths", flag=32, level=52),
    WiznetType(name="resets", flag=64, level=56),
    WiznetType(name="mobdeaths", flag=128, level=56),
    WiznetType(name="flags", flag=256, level=55),
    WiznetType(name="penalties", flag=512, level=55),
    WiznetType(name="saccing", flag=1024, level=55),
    WiznetType(name="levels", flag=2048, level=52),
    WiznetType(name="load", flag=65536, level=58),
    WiznetType(name="restore", flag=32768, level=58),
    WiznetType(name="snoops", flag=16384, level=58),
    WiznetType(name="switches", flag=8192, level=58),
    WiznetType(name="secure", flag=4096, level=59),
)
