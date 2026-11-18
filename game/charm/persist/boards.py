"""The note boards: loading them at boot, and do_board's listing, which login shows.

[partial]: notes/ is empty in this repo, so every board is too. A board with a notes file raises NotPorted from
load_boards: reading and archiving notes comes with the note commands, after the spike.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/board.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import NotPorted
from charm.core.strings import str_cmp
from charm.data import constants as C
from charm.data.boards import BOARDS
from charm.entities import game as game_module
from charm.entities.handler import get_trust
from charm.net.output import printf_to_char, send_to_char

BOARD_NOACCESS = -1
BOARD_NOTFOUND = -1


# C: board.c load_boards [partial]
def load_boards(game) -> None:
    """[partial]: a board with a notes file (notes/<board>) raises NotPorted."""
    game.notes = [[] for _ in BOARDS]
    for board in BOARDS:
        if game_module.c_path(game, f"{C.NOTE_DIR}/{board.short_name}").exists():
            raise NotPorted(f"board.c load_board: reading notes/{board.short_name}")


# C: board.c board_lookup
def board_lookup(name: str) -> int:
    for i, b in enumerate(BOARDS):
        if str_cmp(b.short_name, name):
            return i
    return BOARD_NOTFOUND


# C: board.c unread_notes
def unread_notes(ch, board: int) -> int:
    if BOARDS[board].read_level > get_trust(ch):
        return BOARD_NOACCESS
    return 0  # the boards are empty (load_boards)


# C: board.c do_board [partial]
def do_board(ch, argument: str) -> None:
    """[partial]: the listing (no argument) is ported; changing board comes with the note commands."""
    if ch.is_npc:
        return
    if argument != "":
        raise NotPorted("board.c do_board: changing board")
    send_to_char("{RNum          Name Unread Description{x\n\r"
                 "{R==== ============ ====== ============================={x\n\r", ch)
    count = 1
    for i, b in enumerate(BOARDS):
        unread = unread_notes(ch, i)
        if unread != BOARD_NOACCESS:
            printf_to_char(ch, "({W%2d{x) {g%12s{x [%s%4d{x] {y%s{x\n\r", count, b.short_name,
                           "{G" if unread else "{g", unread, b.long_name)
            count += 1
    board = BOARDS[ch.pcdata.board]
    printf_to_char(ch, "\n\rYou current board is {W%s{x.\n\r", board.short_name)
    if board.read_level > get_trust(ch):
        send_to_char("You cannot read nor write notes on this board.\n\r", ch)
    elif board.write_level > get_trust(ch):
        send_to_char("You can only read notes from this board.\n\r", ch)
    else:
        send_to_char("You can both read and write on this board.\n\r", ch)
