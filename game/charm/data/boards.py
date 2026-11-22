"""The note boards. Their notes (note_first) are loaded at boot from notes/, not here.

Generated from the C by charm_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: boards (board.c). A C table that ends with a NULL sentinel row is scanned up to it; that row isn't here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/board.c. Licence terms: README.md#licence-terms and doc/.
"""

from charm.data.structs import BoardData

# boards, board.c
BOARDS = (
    BoardData(
        short_name="General",
        long_name="General discussion",
        read_level=0,
        write_level=2,
        names="all",
        force_type=1,
        purge_days=21,
        note_first=None,
        changed=False,
    ),
    BoardData(
        short_name="Ideas",
        long_name="Suggestion for improvement",
        read_level=0,
        write_level=2,
        names="all",
        force_type=0,
        purge_days=60,
        note_first=None,
        changed=False,
    ),
    BoardData(
        short_name="Announce",
        long_name="Announcements from Immortals",
        read_level=0,
        write_level=52,
        names="all",
        force_type=0,
        purge_days=60,
        note_first=None,
        changed=False,
    ),
    BoardData(
        short_name="Bugs",
        long_name="Typos, bugs, errors",
        read_level=0,
        write_level=1,
        names="imm",
        force_type=0,
        purge_days=60,
        note_first=None,
        changed=False,
    ),
    BoardData(
        short_name="Personal",
        long_name="Personal messages",
        read_level=0,
        write_level=1,
        names="all",
        force_type=2,
        purge_days=28,
        note_first=None,
        changed=False,
    ),
)
