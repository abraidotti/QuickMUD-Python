"""act_wiz.c's copyover: the game saves who's playing, re-executes itself with every connection still open, and the
new process picks them up again (copyover_recover), so nobody is disconnected.

Copyover works on Linux only, as the C's does (#91, decision 3). The re-exec is game.exec_game: by default
exec_game below, which marks the sockets inheritable (Python's aren't, unlike the C's descriptors) and calls
os.execv; anywhere else it fails as the C's execl would, and do_copyover says so. The scenario player puts a stub
in its place, as the C driver wraps execl, so a scenario checks everything up to the exec.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_wiz.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import os
import socket
import sys

from charm.core.log import log_f
from charm.data import constants as C
from charm.net.output import send_to_char, write_to_descriptor

COPYOVER_FILE = "copyover.data"  # act_wiz.c, in the directory the game runs in (area/)


def _game():
    from charm.entities import game as game_module

    return game_module.current


def descriptor_number(d) -> int:
    """d->descriptor: the scenario player's number for a connection (it matches the C driver's), else the socket's."""
    return d.fd if d.fd is not None else d.sock.fileno()


def is_in_game(d) -> bool:
    """IS_IN_GAME: playing, or writing a note."""
    return d.connected == C.CON_PLAYING or C.CON_NOTE_TO <= d.connected <= C.CON_NOTE_FINISH


def exec_game(game, port: int, control) -> bool:
    """execl (EXE_FILE, "rom", port, "copyover", control): this program again, with the C's arguments, and every
    connection inherited. Returns only if it failed, with the reason on stderr (as perror)."""
    if os.name != "posix":
        print(f"do_copyover: execl: copyover needs Linux (os.execv can't pass sockets on to a new process on "
              f"{sys.platform})", file=sys.stderr)
        return False
    try:
        control.set_inheritable(True)
        for d in game.descriptor_list:
            if d.sock is not None:
                d.sock.set_inheritable(True)
        root = str(game.area_dir.parent) if game.area_dir is not None else "."
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, "-m", "charm", "--port", str(port), "--root", root, "copyover",
                                  str(control.fileno())])
    except OSError as e:
        print(f"do_copyover: execl: {e.strerror}", file=sys.stderr)
    return False


# C: act_wiz.c do_copyover
def do_copyover(ch, argument: str) -> None:
    """Save everyone playing and re-execute the game; drop those still logging in. Only a failed exec returns."""
    from charm.entities.game import c_path
    from charm.net.descriptor import ch_of
    from charm.net.server import close_socket
    from charm.persist.player import save_char_obj

    game = _game()
    try:
        fp = open(c_path(game, COPYOVER_FILE), "w", encoding="latin-1", newline="")
    except OSError as e:
        send_to_char("Copyover file not writeable, aborted.\n\r", ch)
        log_f("Could not write to copyover file: %s", COPYOVER_FILE)
        print(f"do_copyover:fopen: {e.strerror}", file=sys.stderr)
        return
    # "Consider changing all saved areas here, if you use OLC" (the C doesn't)
    buf = "\n\r *** COPYOVER by %s - please remain seated!\n\r" % ch.name
    with fp:
        for d in list(game.descriptor_list):  # "For each playing descriptor, save its state"
            och = ch_of(d)
            # "Drop those logging on, including new characters at the MOTD ... (#5). -- Charm"
            if d.character is None or not is_in_game(d):
                write_to_descriptor(d.sock, "\n\rSorry, we are rebooting. Come back in a few minutes.\n\r", 0)
                close_socket(d)  # "throw'em out"
            else:
                fp.write("%d %s %s\n" % (descriptor_number(d), och.name, d.host))
                save_char_obj(game, och)
                write_to_descriptor(d.sock, buf, 0)
        fp.write("-1\n")
    # "exec - descriptors are inherited"
    exec_ = game.exec_game if game.exec_game is not None else exec_game
    exec_(game, game.port, game.control)
    send_to_char("Copyover FAILED!\n\r", ch)  # "Failed - sucessful exec will not return"


def _fscanf_entries(text: str):
    """copyover.data as fscanf ("%d %s %s\\n") reads it: a number, a name and a host, until -1 or the end."""
    words = text.split()
    k = 0
    while k + 2 < len(words) or (k < len(words) and words[k] == "-1"):
        try:
            desc = int(words[k])
        except ValueError:
            return
        if desc == -1:
            return
        yield desc, words[k + 1], words[k + 2]
        k += 3


# C: act_wiz.c copyover_recover
def copyover_recover(game) -> None:
    """Pick up the connections the old process left in copyover.data: each player is loaded from their file and put
    back where they were. The file is removed first, in case something crashes."""
    from charm.commands.info import do_look
    from charm.entities.game import c_path
    from charm.entities.handler import char_to_room
    from charm.net.act import act
    from charm.net.descriptor import new_descriptor
    from charm.net.server import close_socket
    from charm.persist.player import load_char_obj

    log_f("Copyover recovery initiated")
    path = c_path(game, COPYOVER_FILE)
    try:
        text = path.read_bytes().decode("latin-1")
    except OSError as e:  # "there are some descriptors open which will hang forever then ?"
        print(f"copyover_recover:fopen: {e.strerror}", file=sys.stderr)
        log_f("Copyover file not found. Exitting.\n\r")
        raise SystemExit(1) from None
    path.unlink()  # "In case something crashes - doesn't prevent reading"
    for desc, name, host in _fscanf_entries(text):
        try:
            sock = socket.socket(fileno=desc)
        except OSError:
            continue  # (the C's write to a descriptor that isn't open fails, and it closes it)
        # "Write something, and check if it goes error-free"
        if not write_to_descriptor(sock, "\n\rRestoring from copyover...\n\r", 0):
            sock.close()  # "nope"
            continue
        sock.setblocking(False)
        d = new_descriptor()
        d.sock, d.game, d.host = sock, game, host
        d.outsize = 2000
        game.descriptor_list.insert(0, d)
        d.connected = C.CON_COPYOVER_RECOVER  # "so close_socket frees the char"
        if not load_char_obj(game, d, name):  # "Player file not found?!"
            write_to_descriptor(sock, "\n\rSomehow, your character was lost in the copyover. Sorry.\n\r", 0)
            close_socket(d)
            continue
        write_to_descriptor(sock, "\n\rCopyover recovery complete.\n\r", 0)  # "ok!"
        ch = d.character
        if ch.in_room is None:  # "Just In Case"
            ch.in_room = game.index.get_room_index(C.ROOM_VNUM_TEMPLE)
        game.char_list.insert(0, ch)  # "Insert in the char_list"
        char_to_room(ch, ch.in_room)
        do_look(ch, "auto")
        act("$n materializes!", ch, None, None, C.TO_ROOM)
        d.connected = C.CON_PLAYING
        if ch.pet is not None:
            char_to_room(ch.pet, ch.in_room)
            act("$n materializes!.", ch.pet, None, None, C.TO_ROOM)
