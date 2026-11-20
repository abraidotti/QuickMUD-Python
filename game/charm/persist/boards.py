"""The note boards, all of board.c: loading and archiving notes at boot, the note files, the note and board
commands, and writing a note (the CON_NOTE_* states nanny hands over to).

"Note Board system, (c) 1995-96 Erwin S. Andreasen". A board's notes are game.notes[board], oldest first (the C's
note_first list); a character's board is pcdata.board, an index into BOARDS (the C keeps a pointer).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/board.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass

from charm.core import log
from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.core.strings import atoi, lower, smash_tilde, str_cmp
from charm.data import constants as C
from charm.data.boards import BOARDS
from charm.entities import game as game_module
from charm.entities.handler import get_trust, is_full_name, is_immortal
from charm.net.output import printf_to_char, printf_to_desc, send_to_char, send_to_desc, write_to_buffer

BOARD_NOACCESS = -1
BOARD_NOTFOUND = -1

# "The prompt that the character is given after finishing a note with ~ or END"
FINISH_PROMPT = "({WC{x)ontinue, ({WV{x)iew, ({WP{x)ost or ({WF{x)orget it?"

_DAY = 24 * 3600


@dataclass(eq=False)
class Note:
    """NOTE_DATA. A field the C leaves NULL is None."""

    sender: str | None = None
    date: str | None = None
    date_stamp: int = 0
    expire: int = 0
    to_list: str | None = None
    subject: str | None = None
    text: str | None = None


def _path(game, name: str):
    return game_module.c_path(game, f"{C.NOTE_DIR}/{name}")


# C: board.c free_note
def free_note(note: Note) -> None:
    """"recycle a note": the C puts it on a free list; Python frees it once nothing refers to it."""


# C: board.c new_note
def new_note() -> Note:
    """"allocate memory for a new note or recycle", with every field empty."""
    return Note()


def _s(v) -> str:
    """A NULL string in printf: glibc prints "(null)"."""
    return "(null)" if v is None else v


# C: board.c append_note
def append_note(note: Note) -> str:
    """"append this note to the given file": the text append_note writes."""
    return ("Sender  %s~\nDate    %s~\nStamp   %d\nExpire  %d\nTo      %s~\nSubject %s~\nText\n%s~\n\n"
            % (_s(note.sender), _s(note.date), note.date_stamp, note.expire, _s(note.to_list), _s(note.subject),
               _s(note.text)))


def _write(path, text: str, mode: str) -> bool:
    try:
        with open(path, mode, encoding="latin-1", newline="") as f:
            f.write(text)
    except OSError:
        return False
    return True


# C: board.c finish_note
def finish_note(game, board: int, note: Note) -> None:
    """"Save a note in a given board"."""
    # "The following is done in order to generate unique date_stamps"
    if game.last_note_stamp >= game.current_time:
        game.last_note_stamp += 1
        note.date_stamp = game.last_note_stamp
    else:
        note.date_stamp = game.current_time
        game.last_note_stamp = game.current_time
    game.notes[board].append(note)
    if not _write(_path(game, BOARDS[board].short_name), append_note(note), "a"):  # "append note to note file"
        bug("Could not open one of the note files in append mode", 0)
        game.board_changed[board] = True  # "set it to TRUE hope it will be OK later?"


# C: board.c board_number
def board_number(board: int) -> int:
    """"Find the number of a board": here a board is its number already."""
    return board if 0 <= board < C.MAX_BOARD else -1


# C: board.c board_lookup
def board_lookup(name: str) -> int:
    """"Find a board number based on a string"."""
    for i, b in enumerate(BOARDS):
        if str_cmp(b.short_name, name):
            return i
    return BOARD_NOTFOUND


# C: board.c unlink_note
def unlink_note(game, board: int, note: Note) -> None:
    """"Remove list from the list. Do not free note"."""
    notes = game.notes[board]
    for i, p in enumerate(notes):
        if p is note:
            del notes[i]
            return
    bug("unlink_note: could not find note.", 0)


# C: board.c find_note
def find_note(game, ch, board: int, num: int) -> Note | None:
    """"Find the nth note on a board. Return NULL if ch has no access to that note"."""
    notes = game.notes[board]
    count = 0
    p = None
    for p in notes:
        count += 1
        if count == num:
            break
    else:
        p = None
    if count == num:
        if p is None:  # an empty board and num 0: the C calls is_note_to with NULL
            raise CWouldCrash("board.c find_note: note 0 of an empty board (is_note_to reads a NULL note)")
        if is_note_to(ch, p):
            return p
    return None


# C: board.c save_board
def save_board(game, board: int) -> None:
    """"save a single board"."""
    path = _path(game, BOARDS[board].short_name)
    if not _write(path, "".join(append_note(n) for n in game.notes[board]), "w"):
        bug("Error writing to: %s/%s" % (C.NOTE_DIR, BOARDS[board].short_name), 0)  # bugf: bug() of the text


# C: board.c show_note_to_char
def show_note_to_char(ch, note: Note, num: int) -> None:
    """"Show one not to a character"."""
    # "Ugly colors ?"
    printf_to_char(ch, "[{W%4d{x] {Y%s{x: {g%s{x\n\r{YDate{x:  %s\n\r{YTo{x:    %s\n\r"
                       "{g==========================================================================={x\n\r%s\n\r",
                   num, _s(note.sender), _s(note.subject), _s(note.date), _s(note.to_list), _s(note.text))


# C: board.c save_notes
def save_notes(game) -> None:
    """"Save changed boards"."""
    for i in range(C.MAX_BOARD):
        if game.board_changed[i]:  # "only save changed boards"
            save_board(game, i)


def _fread_string(r) -> str | None:
    """fread_string as the game stores it: each newline becomes "\\n\\r" (the reader keeps plain ones)."""
    s = r.read_string()
    return None if s is None else s.replace("\n", "\n\r")


# C: board.c load_board
def load_board(game, board: int) -> None:
    """"Load a single board"."""
    from charm.world.areafile.reader import Reader

    name = BOARDS[board].short_name
    path = _path(game, name)
    if not path.is_file():
        return  # "Silently return"
    r = Reader(path.read_bytes().decode("latin-1"), str(path))
    while True:
        r.skip_ws()
        if r.at_eof:
            return
        note = Note()
        if not str_cmp(r.read_word(), "sender"):
            break
        note.sender = _fread_string(r)
        if not str_cmp(r.read_word(), "date"):
            break
        note.date = _fread_string(r)
        if not str_cmp(r.read_word(), "stamp"):
            break
        note.date_stamp = r.read_number()
        if not str_cmp(r.read_word(), "expire"):
            break
        note.expire = r.read_number()
        if not str_cmp(r.read_word(), "to"):
            break
        note.to_list = _fread_string(r)
        if not str_cmp(r.read_word(), "subject"):
            break
        note.subject = _fread_string(r)
        if not str_cmp(r.read_word(), "text"):
            break
        note.text = _fread_string(r)
        if note.expire < game.current_time:  # "Should this note be archived right now ?"
            if not _write(_path(game, f"{name}.old"), append_note(note), "a"):
                bug("Could not open archive boards for writing", 0)
            free_note(note)
            game.board_changed[board] = True
            continue
        game.notes[board].append(note)
    bug("Load_notes: bad key word.", 0)


# C: board.c load_boards
def load_boards(game) -> None:
    """"Initialize structures. Load all boards."."""
    game.notes = [[] for _ in BOARDS]
    game.board_changed = [False for _ in BOARDS]
    for i in range(C.MAX_BOARD):
        load_board(game, i)


# The to_list words that reach the immortals and the implementors.
_TO_IMMS = ("imm", "imms", "immortal", "god", "gods", "immortals")
_TO_IMPS = ("imp", "imps", "implementor", "implementors")


# C: board.c is_note_to
def is_note_to(ch, note: Note) -> bool:
    """"Returns TRUE if the specified note is address to ch"."""
    from charm.commands.interp import is_number

    if str_cmp(ch.name, note.sender):
        return True
    if is_full_name("all", note.to_list):
        return True
    if is_immortal(ch) and any(is_full_name(w, note.to_list) for w in _TO_IMMS):
        return True
    if get_trust(ch) == C.MAX_LEVEL and any(is_full_name(w, note.to_list) for w in _TO_IMPS):
        return True
    if is_full_name(ch.name, note.to_list):
        return True
    # "Allow a note to e.g. 40 to send to characters level 40 and above"
    return is_number(note.to_list) and get_trust(ch) >= atoi(note.to_list)


# C: board.c unread_notes
def unread_notes(ch, board: int) -> int:
    """"Return the number of unread notes 'ch' has in 'board'. Returns BOARD_NOACCESS if ch has no access"."""
    if BOARDS[board].read_level > get_trust(ch):
        return BOARD_NOACCESS
    last_read = ch.pcdata.last_note[board_number(board)]
    return sum(1 for n in game_module.current.notes[board] if is_note_to(ch, n) and last_read < n.date_stamp)


# -- the commands ---------------------------------------------------------------------------------------------

# C: board.c do_nwrite
def do_nwrite(ch, argument: str) -> None:
    """"Start writing a note"."""
    from charm.net.act import act

    if ch.is_npc:  # "NPC cannot post notes"
        return
    pc = ch.pcdata
    board = BOARDS[pc.board]
    if get_trust(ch) < board.write_level:
        send_to_char("You cannot post notes on this board.\n\r", ch)
        return
    if pc.in_progress is not None and not pc.in_progress.text:  # "continue previous note, if any text was written"
        send_to_char("Note in progress cancelled because you did not manage to write any text \n\r"
                     "before losing link.\n\r\n\r", ch)
        free_note(pc.in_progress)
        pc.in_progress = None
    if pc.in_progress is None:
        pc.in_progress = new_note()
        pc.in_progress.sender = ch.name
        # "convert to ascii. ctime returns a string which last character is \n, so remove that"
        pc.in_progress.date = log.ctime(game_module.current.current_time)[:-1]
    act("{G$n starts writing a note.{x", ch, None, None, C.TO_ROOM)
    printf_to_char(ch, "You are now %s a new note on the {W%s{x board.\n\r"
                       "If you are using tintin, type #verbose to turn off alias expansion!\n\r\n\r",
                   "continuing" if pc.in_progress.text else "posting", board.short_name)
    printf_to_char(ch, "{YFrom{x:    %s\n\r\n\r", ch.name)
    if not pc.in_progress.text:  # "Are we continuing an old note or not?"
        if board.force_type == C.DEF_NORMAL:
            buf = "If you press Return, default recipient \"{W%s{x\" will be chosen.\n\r" % board.names
        elif board.force_type == C.DEF_INCLUDE:
            buf = ("The recipient list MUST include \"{W%s{x\". If not, it will be added automatically.\n\r"
                   % board.names)
        else:
            buf = "The recipient of this note must NOT include: \"{W%s{x\"." % board.names
        send_to_char(buf, ch)
        send_to_char("\n\r{YTo{x:      ", ch)
        ch.desc.connected = C.CON_NOTE_TO  # "nanny takes over from here"
    else:  # "we are continuing, print out all the fields and the note so far"
        printf_to_char(ch, "{YTo{x:      %s\n\r{YExpires{x: %s\n\r{YSubject{x: %s\n\r", _s(pc.in_progress.to_list),
                       log.ctime(pc.in_progress.expire), _s(pc.in_progress.subject))
        send_to_char("{GYour note so far:{x\n\r", ch)
        send_to_char(pc.in_progress.text, ch)
        send_to_char("\n\rEnter text. Type {W~{x or {WEND{x on an empty line to end note.\n\r"
                     "=======================================================\n\r", ch)
        ch.desc.connected = C.CON_NOTE_TEXT


# C: board.c do_nread
def do_nread(ch, argument: str) -> None:
    """"Read next note in current group. If no more notes, go to next board"."""
    from charm.commands.interp import is_number

    game = game_module.current
    pc = ch.pcdata
    bn = board_number(pc.board)
    if str_cmp(argument, "again"):  # "read last note again"
        pass  # sic: the C's branch is empty, so this says nothing (#64)
    elif is_number(argument):
        number = atoi(argument)
        count = 0
        p = None
        for p in game.notes[pc.board]:
            count += 1
            if count == number:
                break
        else:
            p = None
        if p is None or not is_note_to(ch, p):
            send_to_char("No such note.\n\r", ch)
        else:
            show_note_to_char(ch, p, count)
            pc.last_note[bn] = max(pc.last_note[bn], p.date_stamp)
    else:  # "just next one"
        for count, p in enumerate(game.notes[pc.board], start=1):
            if p.date_stamp > pc.last_note[bn] and is_note_to(ch, p):
                show_note_to_char(ch, p, count)
                # "Advance if new note is newer than the currently newest for that char"
                pc.last_note[bn] = max(pc.last_note[bn], p.date_stamp)
                return
        send_to_char("No new notes in this board.\n\r", ch)
        if next_board(ch):
            buf = "Changed to next board, %s.\n\r" % BOARDS[pc.board].short_name
        else:
            buf = "There are no more boards.\n\r"
        send_to_char(buf, ch)


# C: board.c do_nremove
def do_nremove(ch, argument: str) -> None:
    """"Remove a note"."""
    from charm.commands.interp import is_number

    if not is_number(argument):
        send_to_char("Remove which note?\n\r", ch)
        return
    game = game_module.current
    board = ch.pcdata.board
    p = find_note(game, ch, board, atoi(argument))
    if p is None:
        send_to_char("No such note.\n\r", ch)
        return
    if not str_cmp(ch.name, p.sender) and get_trust(ch) < C.MAX_LEVEL:
        send_to_char("You are not authorized to remove this note.\n\r", ch)
        return
    unlink_note(game, board, p)
    free_note(p)
    send_to_char("Note removed!\n\r", ch)
    save_board(game, board)  # "save the board"


# C: board.c do_nlist
def do_nlist(ch, argument: str) -> None:
    """"List all notes or if argument given, list N of the last notes. Shows REAL note numbers!"."""
    from charm.commands.interp import is_number

    notes = game_module.current.notes[ch.pcdata.board]
    show = count = 0
    if is_number(argument):  # "first, count the number of notes"
        show = atoi(argument)
        count = sum(1 for p in notes if is_note_to(ch, p))
    send_to_char("{WNotes on this board:{x\n\r{rNum> Author        Subject{x\n\r", ch)
    last_note = ch.pcdata.last_note[board_number(ch.pcdata.board)]
    has_shown = 0
    for num, p in enumerate(notes, start=1):
        if is_note_to(ch, p):
            has_shown += 1  # "note that we want to see X VISIBLE note, not just last X"
            if not show or count - show < has_shown:
                send_to_char("{W%3d{x>{B%c{x{Y%-13s{x{y%s{x\n\r"
                             % (num, "*" if last_note < p.date_stamp else " ", _s(p.sender), _s(p.subject)), ch)


# C: board.c do_ncatchup
def do_ncatchup(ch, argument: str) -> None:
    """"catch up with some notes"."""
    notes = game_module.current.notes[ch.pcdata.board]
    if not notes:  # "Find last note"
        send_to_char("Alas, there are no notes in that board.\n\r", ch)
    else:
        ch.pcdata.last_note[board_number(ch.pcdata.board)] = notes[-1].date_stamp
        send_to_char("All mesages skipped.\n\r", ch)  # sic: "mesages" (#64)


# C: board.c do_note
def do_note(ch, argument: str) -> None:
    """"Dispatch function for backwards compatibility"."""
    from charm.commands.info import do_help
    from charm.commands.interp import one_argument

    if ch.is_npc:
        return
    argument, arg = one_argument(argument)
    if arg == "" or str_cmp(arg, "read"):  # "'note' or 'note read X'"
        do_nread(ch, argument)
    elif str_cmp(arg, "list"):
        do_nlist(ch, argument)
    elif str_cmp(arg, "write"):
        do_nwrite(ch, argument)
    elif str_cmp(arg, "remove"):
        do_nremove(ch, argument)
    elif str_cmp(arg, "purge") or str_cmp(arg, "archive"):
        send_to_char("Obsolete.\n\r", ch)
    elif str_cmp(arg, "catchup"):
        do_ncatchup(ch, argument)
    else:
        do_help(ch, "note")


def _changed_to(ch, i: int) -> None:
    ch.pcdata.board = i
    send_to_char("Current board changed to {W%s{x. %s.\n\r"
                 % (BOARDS[i].short_name, "You can only read here" if get_trust(ch) < BOARDS[i].write_level
                    else "You can both read and write here"), ch)


# C: board.c do_board
def do_board(ch, argument: str) -> None:
    """Show the boards with their unread notes, or change board: "board personal" or "board 4"."""
    from charm.commands.interp import is_number

    if ch.is_npc:
        return
    if argument == "":  # "show boards"
        send_to_char("{RNum          Name Unread Description{x\n\r"
                     "{R==== ============ ====== ============================={x\n\r", ch)
        count = 1
        for i, b in enumerate(BOARDS):
            unread = unread_notes(ch, i)  # "how many unread notes?"
            if unread != BOARD_NOACCESS:
                printf_to_char(ch, "({W%2d{x) {g%12s{x [%s%4d{x] {y%s{x\n\r", count, b.short_name,
                               "{G" if unread else "{g", unread, b.long_name)
                count += 1
        board = BOARDS[ch.pcdata.board]
        printf_to_char(ch, "\n\rYou current board is {W%s{x.\n\r", board.short_name)
        if board.read_level > get_trust(ch):  # "Inform of rights"
            send_to_char("You cannot read nor write notes on this board.\n\r", ch)
        elif board.write_level > get_trust(ch):
            send_to_char("You can only read notes from this board.\n\r", ch)
        else:
            send_to_char("You can both read and write on this board.\n\r", ch)
        return
    if ch.pcdata.in_progress is not None:
        send_to_char("Please finish your interrupted note first.\n\r", ch)
        return
    if is_number(argument):  # "Change board based on its number"
        count = 0
        number = atoi(argument)
        i = 0
        for i in range(C.MAX_BOARD):
            if unread_notes(ch, i) != BOARD_NOACCESS:
                count += 1
                if count == number:
                    break
        if count == number:  # "found the board.. change to it"
            _changed_to(ch, i)
        else:
            send_to_char("No such board.\n\r", ch)
        return
    i = board_lookup(argument)  # "Non-number given, find board with that name"
    if i == BOARD_NOTFOUND or unread_notes(ch, i) == BOARD_NOACCESS:  # "Does ch have access to this board?"
        send_to_char("No such board.\n\r", ch)
        return
    _changed_to(ch, i)


# C: board.c next_board
def next_board(ch) -> bool:
    """"tries to change to the next accessible board"."""
    i = board_number(ch.pcdata.board) + 1
    while i < C.MAX_BOARD and unread_notes(ch, i) == BOARD_NOACCESS:
        i += 1
    if i == C.MAX_BOARD:
        return False
    ch.pcdata.board = i
    return True


# -- writing a note: nanny's CON_NOTE_* states -----------------------------------------------------------------

def _no_note(d, state: str) -> bool:
    if d.character.pcdata.in_progress is None:
        d.connected = C.CON_PLAYING
        bug("nanny: In %s, but no note in progress" % state, 0)
        return True
    return False


# C: board.c handle_con_note_to
def handle_con_note_to(d, argument: str) -> None:
    if _no_note(d, "CON_NOTE_TO"):
        return
    ch = d.character
    board = BOARDS[ch.pcdata.board]
    note = ch.pcdata.in_progress
    buf = smash_tilde(argument)  # "change ~ to - as we save this field as a string later"
    if board.force_type == C.DEF_NORMAL:  # "default field"
        if buf == "":
            note.to_list = board.names
            printf_to_desc(d, "Assumed default recipient: {W%s{x\n\r", board.names)
        else:
            note.to_list = buf
    elif board.force_type == C.DEF_INCLUDE:  # "forced default"
        if not is_full_name(board.names, buf):
            buf = buf + " " + board.names
            if len(buf) >= C.MAX_INPUT_LENGTH:
                raise CWouldCrash("board.c handle_con_note_to: the recipients overflow buf[MAX_INPUT_LENGTH]")
            note.to_list = buf
            printf_to_desc(d, "\n\rYou did not specify %s as recipient, so it was automatically added.\n\r"
                              "{YNew To{x :  %s\n\r", board.names, note.to_list)
        else:
            note.to_list = buf
    else:  # "forced exclude"
        if buf == "":
            send_to_desc("You must specify a recipient.\n\r{YTo{x:      ", d)
            return
        if is_full_name(board.names, buf):
            send_to_desc("You are not allowed to send notes to %s on this board. Try again.\n\r{YTo{x:      "
                         % board.names, d)
            return  # "return from nanny, not changing to the next state!"
        note.to_list = buf
    send_to_desc("{Y\n\rSubject{x: ", d)
    d.connected = C.CON_NOTE_SUBJECT


# C: board.c handle_con_note_subject
def handle_con_note_subject(d, argument: str) -> None:
    if _no_note(d, "CON_NOTE_SUBJECT"):
        return
    ch = d.character
    board = BOARDS[ch.pcdata.board]
    buf = smash_tilde(argument)  # "change ~ to - as we save this field as a string later"
    if buf == "":  # "Do not allow empty subjects"
        write_to_buffer(d, "Please find a meaningful subject!\n\r")
        printf_to_desc(d, "{YSubject{x: ")
    elif len(buf) > 60:
        # sic: "You're note", and no prompt again (#64)
        write_to_buffer(d, "No, no. This is just the Subject. You're note writing the note yet. Twit.\n\r")
    else:  # "advance to next stage"
        ch.pcdata.in_progress.subject = buf
        if is_immortal(ch):  # "immortals get to choose number of expire days"
            printf_to_desc(d, "\n\rHow many days do you want this note to expire in?\n\r"
                              "Press Enter for default value for this board, {W%d{x days.\n\r{YExpire{x:  ",
                           board.purge_days)
            d.connected = C.CON_NOTE_EXPIRE
        else:
            note = ch.pcdata.in_progress
            note.expire = game_module.current.current_time + board.purge_days * _DAY
            printf_to_desc(d, "This note will expire %s\r", log.ctime(note.expire))
            send_to_desc("\n\rEnter text. Type {W~{x or {WEND{x on an empty line to end note.\n\r"
                         "=======================================================\n\r", d)
            d.connected = C.CON_NOTE_TEXT


# C: board.c handle_con_note_expire
def handle_con_note_expire(d, argument: str) -> None:
    from charm.commands.interp import is_number

    if _no_note(d, "CON_NOTE_EXPIRE"):
        return
    ch = d.character
    buf = argument  # "Numeric argument. no tilde smashing"
    if buf == "":  # "assume default expire"
        days = BOARDS[ch.pcdata.board].purge_days
    elif not is_number(buf):
        write_to_buffer(d, "Write the number of days!\n\r")
        send_to_desc("{YExpire{x:  ", d)
        return
    else:
        days = atoi(buf)
        if days <= 0:
            write_to_buffer(d, "This is a positive MUD. Use positive numbers only! :)\n\r")
            send_to_desc("{YExpire{x:  ", d)
            return
    ch.pcdata.in_progress.expire = game_module.current.current_time + days * _DAY  # "24 hours, 3600 seconds"
    send_to_desc("\n\rEnter text. Type {W~{x or {WEND{x on an empty line to end note.\n\r"
                 "=======================================================\n\r", d)
    d.connected = C.CON_NOTE_TEXT


# C: board.c handle_con_note_text
def handle_con_note_text(d, argument: str) -> None:
    if _no_note(d, "CON_NOTE_TEXT"):
        return
    ch = d.character
    note = ch.pcdata.in_progress
    buf = argument
    if str_cmp(buf, "~") or str_cmp(buf, "END"):  # "First, check for EndOfNote marker"
        write_to_buffer(d, "\n\r\n\r")
        printf_to_desc(d, "%s", FINISH_PROMPT)
        write_to_buffer(d, "\n\r")
        d.connected = C.CON_NOTE_FINISH
        return
    buf = smash_tilde(buf)  # "smash it now"
    if len(buf) > C.MAX_LINE_LENGTH:  # "Check for too long lines. Do not allow lines longer than 80 chars"
        printf_to_desc(d, "Too long line rejected. Do NOT go over %d characters!\n\r", C.MAX_LINE_LENGTH)
        return
    letter = note.text if note.text else ""
    note.text = None  # "be sure we don't free it twice"
    if len(letter) + len(buf) > C.MAX_NOTE_TEXT:  # "Note too long, take appropriate steps"
        write_to_buffer(d, "Note too long!\n\r")
        free_note(note)
        ch.pcdata.in_progress = None  # "important"
        d.connected = C.CON_PLAYING
        return
    # "Add new line to the buffer": "\r first to make note files better readable"
    note.text = letter + buf + "\r\n"


# C: board.c handle_con_note_finish
def handle_con_note_finish(d, argument: str) -> None:
    from charm.net.act import act

    if _no_note(d, "CON_NOTE_FINISH"):
        return
    ch = d.character
    note = ch.pcdata.in_progress
    answer = lower(argument[:1])  # tolower: ASCII letters only
    if answer == "c":  # "keep writing"
        write_to_buffer(d, "Continuing note...\n\r")
        d.connected = C.CON_NOTE_TEXT
    elif answer == "v":  # "view note so far"
        if note.text:
            send_to_desc("{gText of your note so far:{x\n\r", d)
            write_to_buffer(d, note.text)
        else:
            write_to_buffer(d, "You haven't written a thing!\n\r\n\r")
        printf_to_desc(d, "%s", FINISH_PROMPT)
        write_to_buffer(d, "\n\r")
    elif answer == "p":  # "post note"
        finish_note(game_module.current, ch.pcdata.board, note)
        write_to_buffer(d, "Note posted.\n\r")
        d.connected = C.CON_PLAYING
        ch.pcdata.in_progress = None  # "remove AFK status"
        act("{G$n finishes $s note.{x", ch, None, None, C.TO_ROOM)
    elif answer == "f":
        write_to_buffer(d, "Note cancelled!\n\r")
        free_note(note)
        ch.pcdata.in_progress = None
        d.connected = C.CON_PLAYING  # "remove afk status"
    else:  # "invalid response"
        write_to_buffer(d, "Huh? Valid answers are:\n\r\n\r")
        printf_to_desc(d, "%s", FINISH_PROMPT)
        write_to_buffer(d, "\n\r")
