"""The game loop, on a stdlib selectors loop shaped like comm.c's game_loop_unix (#19, decision 4).

One pulse, as in the C:
1. poll every connection without waiting
2. accept a new connection
3. read input, and run one command line per connection
4. run update_handler
5. flush output
6. sleep to the next quarter second

All game code is synchronous; the loop is the only part that touches sockets.

One known difference, accepted in #29: the C also polls for exceptional conditions, and closes a connection that
has some, such as a telnet client's urgent (out-of-band) data. selectors has no such set, so that step isn't
copied, and such a connection stays open.

A line of input from a player goes to the command interpreter. A command that isn't ported yet raises
NotPorted, which stops the game (#28, decision 3; #32, decision 3).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c, src/ban.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import selectors
import signal
import socket
import sys
import time

from quickmud.commands.interp import run_olc_editor, substitute_alias
from quickmud.core.errors import CWouldCrash, NotPorted
from quickmud.core.log import bug, log_f, log_string
from quickmud.data import constants as C
from quickmud.net.act import act
from quickmud.net.descriptor import Descriptor, ch_of, new_descriptor
from quickmud.net.input import read_from_buffer, read_from_descriptor
from quickmud.net.output import process_output, send_to_desc, show_string, write_to_buffer, write_to_descriptor
from quickmud.net.wiznet import wiznet
from quickmud.olc.strings import string_add
from quickmud.persist.player import save_char_obj

PULSE_SECONDS = 1 / C.PULSE_PER_SECOND


# C: comm.c init_socket
def init_socket(port: int, ipaddress: str) -> socket.socket:
    fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    fd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    log_f("Set IP address to %s", ipaddress)
    try:
        fd.bind((ipaddress, port))
    except OSError as e:
        print(f"Init socket: bind: {e.strerror}", file=sys.stderr)
        fd.close()
        raise SystemExit(1)
    fd.listen(3)
    fd.setblocking(False)
    return fd


def check_ban(game, site: str, kind: int) -> bool:
    """ban.c's check_ban (quickmud.persist.bans), which nanny imports from here."""
    from quickmud.persist.bans import check_ban as ban_check

    return ban_check(game, site, kind)


# C: comm.c init_descriptor
def init_descriptor(game, control: socket.socket) -> None:
    try:
        sock, (addr, _) = control.accept()
    except OSError as e:
        print(f"New_descriptor: accept: {e.strerror}", file=sys.stderr)
        return
    sock.setblocking(False)
    d = new_descriptor()
    d.sock, d.game = sock, game
    config = game.config
    d.connected = C.CON_ANSI if config.ansiprompt else C.CON_GET_NAME
    d.ansi = bool(config.ansicolor)
    d.outsize = 2000
    log_string(f"Sock.sinaddr:  {addr}")
    try:
        d.host = socket.gethostbyaddr(addr)[0]
    except OSError:
        d.host = addr
    if check_ban(game, d.host, C.BAN_ALL):
        write_to_descriptor(sock, "Your site has been banned from this mud.\n\r")
        sock.close()
        return
    game.descriptor_list.insert(0, d)
    if game.selector is not None:
        game.selector.register(sock, selectors.EVENT_READ | selectors.EVENT_WRITE, d)
    # "First Contact!"
    if not config.ansiprompt:
        greeting = game.index.help_greeting
        if greeting is None:
            raise CWouldCrash("comm.c init_descriptor: no 'greeting' help (help_greeting is NULL)")
        send_to_desc(greeting[1:] if greeting.startswith(".") else greeting, d)
    else:
        send_to_desc("Do you want ANSI? (Y/n) ", d)


# C: comm.c close_socket
def close_socket(dclose: Descriptor) -> None:
    from quickmud.entities.create import free_char

    game = dclose.game
    if dclose.closed:
        return
    if dclose.outtop > 0:
        process_output(dclose, False)
    if dclose.snoop_by is not None:
        write_to_buffer(dclose.snoop_by, "Your victim has left the game.\n\r")
    for d in game.descriptor_list:
        if d.snoop_by is dclose:
            d.snoop_by = None
    ch = dclose.character
    if ch is not None:
        log_string(f"Closing link to {ch.name}.")
        if (dclose.connected == C.CON_PLAYING and not game.merc_down) or (
                C.CON_NOTE_TO <= dclose.connected <= C.CON_NOTE_FINISH):
            act("$n has lost $s link.", ch, None, None, C.TO_ROOM)
            wiznet(game, "Net death has claimed $N.", ch, None, C.WIZ_LINKS, 0, 0)
            ch.desc = None
        else:
            free_char(game, dclose.original if dclose.original is not None else dclose.character)
    if dclose in game.descriptor_list:
        game.descriptor_list.remove(dclose)
    else:
        bug("Close_socket: dclose not found.", 0)
    if game.selector is not None:
        try:
            game.selector.unregister(dclose.sock)
        except (KeyError, ValueError):
            pass
    dclose.sock.close()
    dclose.closed = True


# C: comm.c shutdown_all
def shutdown_all(game, message: str | None) -> None:
    game.merc_down = True
    for d in list(game.descriptor_list):
        if message is not None:
            write_to_descriptor(d.sock, message)
        vch = ch_of(d)
        if vch is not None and d.connected == C.CON_PLAYING:  # IS_IN_GAME
            save_char_obj(game, vch)
        close_socket(d)


# C: comm.c stop_idling
def stop_idling(ch) -> None:
    from quickmud.entities.handler import char_from_room, char_to_room

    if (ch is None or ch.desc is None or ch.desc.connected != C.CON_PLAYING or ch.was_in_room is None
            or ch.in_room is not ch.desc.game.index.get_room_index(C.ROOM_VNUM_LIMBO)):
        return
    ch.timer = 0
    char_from_room(ch)
    char_to_room(ch, ch.was_in_room)
    ch.was_in_room = None
    act("$n has returned from the void.", ch, None, None, C.TO_ROOM)


def _drop(d: Descriptor) -> None:
    """The C's save-then-close when a connection fails."""
    if d.character is not None and d.connected == C.CON_PLAYING:
        save_char_obj(d.game, d.character)
    d.outbuf = ""
    close_socket(d)


class PulseStats:
    """--pulse-stats (#28, decision 4): each pulse's work (not its sleep), logged every 60 seconds, and for the
    whole run when the game stops (#32, decision 5: quickmud_tools sim bots reads that line)."""

    def __init__(self, every: float = 60.0):
        self.every, self.times, self.since, self.run = every, [], time.monotonic(), []  # clock: measures, not game time

    @staticmethod
    def summary(t: list[float]) -> str:
        s = sorted(t)
        p95 = s[int(0.95 * (len(s) - 1))]  # nearest rank
        return ("median %.2f ms, p95 %.2f ms, max %.2f ms, mean %.2f ms over %d pulses"
                % (1000 * s[len(s) // 2], 1000 * p95, 1000 * s[-1], 1000 * sum(s) / len(s), len(s)))  # non-negative: a length

    def add(self, seconds: float) -> None:
        self.times.append(seconds)
        self.run.append(seconds)
        if time.monotonic() - self.since >= self.every:  # clock: measures, not game time
            log_f("Pulse work: %s", self.summary(self.times))
            self.times, self.since = [], time.monotonic()  # clock: measures, not game time

    def finish(self) -> None:
        if self.run:
            log_f("Pulse work over the run: %s", self.summary(self.run))


# C: comm.c handle_shutdown_signal
def handle_shutdown_signal(game, sig: int) -> None:
    game.shutdown_signal = sig


# C: comm.c game_loop_unix
def game_loop(game, control: socket.socket, stats: PulseStats | None = None) -> None:
    sel = game.selector = selectors.DefaultSelector()
    sel.register(control, selectors.EVENT_READ, None)
    for d in game.descriptor_list:  # the connections copyover_recover picked up
        if d.sock is not None:
            sel.register(d.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, d)
    saved = {}
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):  # SIGBREAK: Windows' way to ask a console program to stop
        if hasattr(signal, name):
            sig = getattr(signal, name)
            saved[sig] = signal.signal(sig, lambda s, frame: handle_shutdown_signal(game, s))
    try:
        _loop(game, control, sel, stats)
    finally:
        if stats is not None:
            stats.finish()
        for sig, handler in saved.items():  # put them back, for a caller that carries on (the tests)
            signal.signal(sig, handler)
        sel.close()
        game.selector = None


def _loop(game, control: socket.socket, sel, stats: PulseStats | None) -> None:
    from quickmud.net.nanny import nanny
    from quickmud.systems.update import update_handler

    last = time.time()  # clock: the loop's, as game_loop_unix's gettimeofday
    game.current_time = int(last)

    while not game.merc_down:
        if game.shutdown_signal:
            log_f("Caught signal %d, shutting down.", int(game.shutdown_signal))
            shutdown_all(game, "\n\rThe game is shutting down.\n\r")
            break
        work = time.perf_counter()  # clock: measures, not game time

        # Poll all active descriptors.
        readable, writable, new_connection = set(), set(), False
        for key, events in sel.select(timeout=0):
            if key.data is None:
                new_connection = True
                continue
            if events & selectors.EVENT_READ:
                readable.add(key.data)
            if events & selectors.EVENT_WRITE:
                writable.add(key.data)
        if new_connection:
            init_descriptor(game, control)

        # Process input.
        for d in list(game.descriptor_list):
            if d.closed:
                continue
            d.fcommand = False
            if d in readable:
                if d.character is not None:
                    d.character.timer = 0
                if not read_from_descriptor(d):
                    writable.discard(d)
                    _drop(d)
                    continue
            ch = d.character
            if ch is not None and ch.daze > 0:
                ch.daze -= 1
            if ch is not None and ch.wait > 0:
                ch.wait -= 1
                continue
            read_from_buffer(d)
            if d.incomm != "":
                d.fcommand = True
                stop_idling(d.character)
                if d.showstr_point is not None:
                    show_string(d, d.incomm)
                elif d.pString is not None:
                    string_add(d.character, d.incomm)
                elif d.connected == C.CON_PLAYING:
                    if not run_olc_editor(d):
                        substitute_alias(d, d.incomm)
                else:
                    nanny(game, d, d.incomm)
                d.incomm = ""

        # Autonomous game motion.
        update_handler(game)

        # Output.
        for d in list(game.descriptor_list):
            if d.closed:
                continue
            if (d.fcommand or d.outtop > 0) and d in writable:
                if not process_output(d, True):
                    _drop(d)

        if stats is not None:
            stats.add(time.perf_counter() - work)  # clock: measures, not game time

        # Synchronize to a clock: sleep(last_time + 1/PULSE_PER_SECOND - now).
        stall = last + PULSE_SECONDS - time.time()  # clock: the loop's pulse
        if stall > 0:
            time.sleep(stall)  # clock: the loop's pulse
        last = time.time()  # clock: the loop's pulse
        game.current_time = int(last)
