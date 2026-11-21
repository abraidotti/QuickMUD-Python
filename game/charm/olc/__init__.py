"""The online builder (OLC): the area, room, object, mob, mob program and help editors, and saving areas (P5).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

# olc.h: which editor a connection is in (DESCRIPTOR_DATA's editor)
ED_NONE, ED_AREA, ED_ROOM, ED_OBJECT, ED_MOBILE, ED_MPCODE, ED_HELP = range(7)
