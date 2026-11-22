"""Play a scenario file through the Python game: the same steps, and the same output, as the C driver did.

The C driver (tools/oracle/scenario.c, at the c-final tag) and this one do the same thing (#35, decision 1):
- boot with a fixed seed and clock; a pulse is a call, and the clock moves a second every 4 pulses
- connections are one end of a socketpair: what the game writes arrives at the other end, which is read after
  each step
- a pulse is game_loop_unix's input, update and output steps, calling the game's own nanny, substitute_alias,
  update_handler and process_output
- every random() is counted and hashed (FNV-1a over each value's 4 low bytes)

The format and the output lines are described in tools/oracle/scenario.c at c-final, and play() below reads
the same format. play() returns the output lines; a NotPorted or CWouldCrash ends the scenario with a "stopped"
line, so it shows as a difference from the golden.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from charm.core import log, rng
from charm.core.errors import CWouldCrash, NotPorted
from charm.data import constants as C

DEFAULT_SEED, DEFAULT_CLOCK = "20261117", 1763400000

def esc(data: bytes) -> str:
    """Bytes on one line: \\\\, \\", \\n, \\r, and \\xNN for anything outside printable ASCII."""
    out = ['"']
    for b in data:
        if b == 0x5C:
            out.append("\\\\")
        elif b == 0x22:
            out.append('\\"')
        elif b == 0x0A:
            out.append("\\n")
        elif b == 0x0D:
            out.append("\\r")
        elif b < 32 or b > 126:
            out.append("\\x%02x" % b)
        else:
            out.append(chr(b))
    out.append('"')
    return "".join(out)


@dataclass(eq=False)
class Conn:

    def __repr__(self) -> str:  # short: the dataclass default never ends (tests/test_reprs.py)
        return f"<Conn {self.name!r}>"

    name: str
    d: object
    peer: socket.socket
    closed: bool = False
    got: bytes = b""  # read from peer during this step, not printed yet


class Player:
    def __init__(self, area: Path):
        self.area = area
        self.out: list[str] = []
        self.conns: list[Conn] = []
        self.current: Conn | None = None
        self.game = None
        self.pulses = 0
        self.start = 0
        self.draws, self.hash = 0, 2166136261

    # -- random(), counted ---------------------------------------------------------------------------------------

    def _wrap_random(self, real):
        def counted():
            v = real()
            self.draws += 1
            for i in range(4):
                self.hash ^= (v >> (8 * i)) & 0xFF
                self.hash = (self.hash * 16777619) & 0xFFFFFFFF
            return v
        return counted

    # -- connections ---------------------------------------------------------------------------------------------

    def _listed(self, c: Conn) -> bool:
        return c.d in self.game.descriptor_list and not c.d.closed

    def connect(self, name: str) -> None:
        from charm.net.descriptor import new_descriptor
        from charm.net.output import send_to_desc

        game_end, peer = socket.socketpair()
        peer.setblocking(False)
        d = new_descriptor()
        d.sock, d.game = game_end, self.game
        d.fd = 100 + len(self.conns)  # the number the C driver dup2s the game's end to, so do_sockets agrees
        d.connected = C.CON_ANSI if self.game.config.ansiprompt else C.CON_GET_NAME
        d.ansi = bool(self.game.config.ansicolor)
        d.host = "scenario"
        self.game.descriptor_list.insert(0, d)
        c = Conn(name, d, peer)
        self.conns.append(c)
        self.current = c
        if not self.game.config.ansiprompt:  # the greeting, as init_descriptor sends it
            greeting = self.game.index.help_greeting
            send_to_desc(greeting[1:] if greeting.startswith(".") else greeting, d)

    def find(self, name: str) -> Conn:
        for c in self.conns:
            if c.name == name:
                return c
        raise SystemExit(f"scenario: no connection called {name}")

    # -- the pulse -----------------------------------------------------------------------------------------------

    def pulse(self) -> None:
        from charm.commands.interp import run_olc_editor, substitute_alias
        from charm.olc.strings import string_add
        from charm.net.input import read_from_buffer
        from charm.net.nanny import nanny
        from charm.net.output import process_output, show_string
        from charm.net.server import close_socket, stop_idling
        from charm.persist.player import save_char_obj
        from charm.systems.update import update_handler

        game = self.game
        for d in list(game.descriptor_list):
            if d.closed:
                continue
            d.fcommand = False
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
        update_handler(game)
        for d in list(game.descriptor_list):
            if d.closed:
                continue
            if d.fcommand or d.outtop > 0:
                if not process_output(d, True):
                    if d.character is not None and d.connected == C.CON_PLAYING:
                        save_char_obj(game, d.character)
                    d.outbuf = ""
                    close_socket(d)
        self.pulses += 1
        game.current_time = self.start + self.pulses // C.PULSE_PER_SECOND  # non-negative: a count

    # -- output --------------------------------------------------------------------------------------------------

    def drain(self) -> None:
        """Read what the game has sent each open connection so far this step."""
        for c in self.conns:
            if c.closed:
                continue
            while len(c.got) < 65536:
                try:
                    chunk = c.peer.recv(65536 - len(c.got))
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                if not chunk:
                    break
                c.got += chunk

    def sent(self, text: bytes) -> bool:
        """Has an open connection been sent text this step?"""
        return any(not c.closed and text in c.got for c in self.conns)

    def collect(self) -> None:
        self.drain()
        for c in self.conns:
            if c.closed:
                continue
            if c.got:
                self.out.append(f"out {c.name} {esc(c.got)}")
                c.got = b""
            if not self._listed(c):
                self.out.append(f"closed {c.name}")
                c.closed = True
                c.peer.close()
        self.out.append("rng %d %08x" % (self.draws, self.hash))

    def _dump_obj(self, where: str, obj, depth: int) -> None:
        v = obj.value
        self.out.append("state %sobj %s %d wear %d timer %d cost %d values %d %d %d %d %d"
                        % ("  " * depth, where, obj.index.vnum, obj.wear_loc, obj.timer, obj.cost, v[0], v[1], v[2],
                           v[3], v[4]))
        for inner in obj.contains:
            self._dump_obj("in", inner, depth + 1)

    def state(self) -> None:
        seen = []
        for c in self.conns:
            ch = c.d.character
            if c.closed or not self._listed(c) or ch is None or ch.in_room is None:
                continue
            room = ch.in_room
            if room in seen:
                continue
            seen.append(room)
            self.out.append(f"state room {room.vnum} light {room.light} people"
                            + "".join(" mob" if p.is_npc else " player" for p in room.people))
            for door, ex in enumerate(room.exit):
                if ex is not None:
                    self.out.append("state exit %d to %d info %d key %d"
                                    % (door, ex.to_room.vnum if ex.to_room else 0, ex.exit_info, ex.key))
            for p in room.people:
                self.out.append(
                    "state char %s %d pos %d hit %d/%d mana %d/%d move %d/%d wait %d daze %d exp %d gold %d silver %d "
                    "act %d affected_by %d train %d on %d stats %d %d %d %d %d"
                    % ("mob" if p.is_npc else p.name, p.index.vnum if p.is_npc else p.level, p.position, p.hit,
                       p.max_hit, p.mana, p.max_mana, p.move, p.max_move, p.wait, p.daze, p.exp, p.gold, p.silver,
                       p.act, p.affected_by, p.train, p.on.index.vnum if p.on else 0, *p.perm_stat))
                for af in p.affected:
                    self.out.append("state   affect %d level %d duration %d location %d modifier %d bitvector %d"
                                    % (af.type, af.level, af.duration, af.location, af.modifier, af.bitvector))
                for obj in p.carrying:
                    self._dump_obj("carried", obj, 1)
            for obj in room.contents:
                self._dump_obj("floor", obj, 0)

    # -- the script ----------------------------------------------------------------------------------------------

    def _exec_game(self, game, port: int, control) -> bool:
        """The re-exec, stubbed: what the C driver's __wrap_execl prints for do_copyover's execl, which then fails."""
        self.out.append("exec ../area/rom rom %d copyover %d" % (port, control.fileno() if control else 0))
        return False

    def boot(self, seed: str, clock: int, updates: str) -> None:
        from charm.entities import game as game_module
        from charm.entities.boot import boot_db
        from charm.net.config import qmconfig_read

        from charm.systems.update import PORTED, updates_named

        on = updates_named(None if updates == "all" else updates)
        if on - PORTED:
            raise NotPorted(f"update_handler: {', '.join(sorted(on - PORTED))} (@updates {updates})")
        rng.random = self._wrap_random(rng.random)
        config = qmconfig_read(self.area / "qmconfig.rc")
        self.game = game = boot_db(self.area, clock, {"CHARM_SEED": seed})
        game.config = config
        game.updates = on
        game.exec_game = self._exec_game  # copyover's re-exec, stubbed as the C driver wraps execl
        game_module.current = game
        log.clock = lambda: game.current_time
        log.localtime = time.gmtime  # clock: the oracle's container has no time zone, so its ctime is UTC
        self.start = clock
        self.out.append(f"boot seed {seed} clock {clock} updates {updates}")
        self.collect()

    def step(self, n: int, line: str) -> None:
        from charm.entities.create import create_mobile, create_object
        from charm.entities.handler import char_to_room, obj_to_room
        from charm.net.descriptor import INBUF_SIZE

        ix = self.game.index
        self.out.append(f"step {n} {esc(line.encode('latin-1'))}")
        if not line.startswith("@") or line == "@return":
            if line == "@return":
                line = ""  # an empty line of input
            c = self.current
            if c is None or c.closed or not self._listed(c):
                raise SystemExit(f"scenario: step {n}: no open connection to send to")
            if len(c.d.inbuf) + len(line) + 2 >= INBUF_SIZE:
                raise SystemExit(f"scenario: step {n}: the input buffer is full")
            c.d.inbuf += line + "\n"
            self.pulse()
        elif m := re.fullmatch(r"@connect (\S+)", line):
            self.connect(m.group(1))
        elif m := re.fullmatch(r"@as (\S+)", line):
            self.current = self.find(m.group(1))
        elif m := re.fullmatch(r"@pulse until (\d+) (\S.*)", line):
            cap, text = int(m.group(1)), m.group(2).encode("latin-1")
            k = 0
            while k < cap and not self.sent(text):
                self.pulse()
                self.drain()
                k += 1
            self.out.append("pulses %d%s" % (k, "" if self.sent(text) else ", not seen"))
        elif m := re.fullmatch(r"@pulse (\d+)", line):
            for _ in range(int(m.group(1))):
                self.pulse()
        elif m := re.fullmatch(r"@mob (-?\d+) (-?\d+)", line):
            mob = create_mobile(self.game, ix.get_mob_index(int(m.group(1))))
            char_to_room(mob, ix.get_room_index(int(m.group(2))))
            self.last_mob = mob
        elif line in ("@charm", "@charm pet"):
            from charm.commands.comm import add_follower

            c, mob = self.current, getattr(self, "last_mob", None)
            if mob is None or c is None or c.closed or not self._listed(c) or c.d.character is None:
                raise SystemExit(f"scenario: step {n}: @charm needs a @mob and a character")
            ch = c.d.character
            if line == "@charm pet":
                mob.act |= C.ACT_PET
            mob.affected_by |= C.AFF_CHARM
            add_follower(self.game, mob, ch)
            mob.leader = ch
            if line == "@charm pet":
                ch.pet = mob
        elif m := re.fullmatch(r"@obj (-?\d+) (-?\d+)((?: -?\d+){5})?", line):
            obj = create_object(self.game, ix.get_obj_index(int(m.group(1))), 0)
            if m.group(3):
                obj.value = [int(x) for x in m.group(3).split()]
            obj_to_room(obj, ix.get_room_index(int(m.group(2))))
            self.last_obj = obj
        elif m := re.fullmatch(r"@owner (\S+)", line):
            obj = getattr(self, "last_obj", None)
            if obj is None:
                raise SystemExit(f"scenario: step {n}: @owner needs an @obj")
            obj.owner = m.group(1)[:31]  # the C reads it with %31s
        elif m := re.fullmatch(r"@spec(?: (-?\d+))?", line):
            from charm.systems.specials import SPECIALS

            mob = getattr(self, "last_mob", None)
            if mob is None or mob.spec_fun is None:
                raise SystemExit(f"scenario: step {n}: @spec needs a @mob with a special")
            results = ["spec"]
            for _ in range(int(m.group(1)) if m.group(1) else 1):
                if mob not in self.game.char_list:
                    results.append("gone")  # extracted: its memory may be reused, so stop
                    break
                fn = SPECIALS.get(mob.spec_fun)
                if fn is None:
                    raise NotPorted(f"special.c {mob.spec_fun}")
                results.append("1" if fn(mob) else "0")
            self.out.append(" ".join(results))
        elif line == "@state":
            self.state()
        elif line.startswith("@file "):
            path = self.area / line[6:]
            if path.is_file():
                self.out.append(f"file {line[6:]} {esc(path.read_bytes()[:262144])}")
            else:
                self.out.append(f"file {line[6:]} missing")
        else:
            raise SystemExit(f"scenario: step {n}: unknown line {line}")
        self.collect()


EXPECT_STOP = "# expect: stopped NotPorted"
# Differences kept on purpose, which a comparison sets aside: memory's Perms line counts the C's alloc_perm blocks,
# and Python's objects (#91, decision 6).
KEPT = (re.compile(r"Perms +\d+ blocks  of +\d+ bytes\."),)


def _kept(line: str) -> str:
    for rx in KEPT:
        line = rx.sub("Perms (kept different)", line)
    return line


def difference(c_lines: list[str], py_lines: list[str], text: str) -> str | None:
    """Where the Python's output first differs from the C's, or None.

    A scenario with the comment line "# expect: stopped NotPorted" must make the Python game stop with NotPorted:
    its last line is then the "stopped" line, and only what comes before it is compared, since the C carries on.
    """
    want = c_lines
    got = py_lines
    if EXPECT_STOP in text.splitlines():
        if not got or not got[-1].startswith("stopped NotPorted"):
            return "the Python game was to stop with NotPorted, and didn't"
        got = got[:-1]
        want = want[:len(got)]
    # Otherwise a "stopped" line has no match in the C's output, so it shows as the difference below.
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b and _kept(a) != _kept(b):
            step = next((want[j] for j in range(i, -1, -1) if want[j].startswith("step ")), "(before any step)")
            return f"line {i + 1}, at {step}:\n    C:      {a[:300]}\n    Python: {b[:300]}"
    if len(want) != len(got):
        more = (want if len(want) > len(got) else got)[min(len(want), len(got))]
        return f"{len(want)} lines from C, {len(got)} from Python; the longer goes on with: {more[:300]}"
    return None


# A golden's first line says where it came from (#112, decision 4): "c-final", the C game through
# tools/oracle/scenario.c at the c-final tag, or "python", saved again from the Python game after a deliberate change
# (charm_tools port scenarios --save), whose PR shows the diff.
GOLDEN_SOURCES = ("c-final", "python")


def play_fresh(text: str, repo: Path) -> list[str]:
    """play() from a throwaway copy of the repo's area/, with the fixture players (tools/fixtures/player) and
    qmconfig.rc, as the C driver runs: a scenario that saves writes player files there, not in the repo."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="charm-scenario-"))
    try:
        shutil.copytree(repo / "area", tmp / "area")
        for d in ("player", "gods", "notes", "log", "files"):
            (tmp / d).mkdir()
        fixtures = repo / "tools" / "fixtures"
        for f in (fixtures / "player").iterdir():
            shutil.copy(f, tmp / "player" / f.name)
        shutil.copy(fixtures / "qmconfig.rc", tmp / "area" / "qmconfig.rc")
        for f in (fixtures / "files").iterdir():
            shutil.copy(f, tmp / "files" / f.name)
        return play(text, tmp / "area")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def play(text: str, area: Path) -> list[str]:
    """Play a scenario (its text) in the area directory `area`; the output lines, as scenario.c prints them."""
    p = Player(area)
    seed, clock, updates = DEFAULT_SEED, DEFAULT_CLOCK, "area"
    real_random = rng.random
    n = 0
    try:
        with log.capture():
            for line in text.splitlines():
                line = line.rstrip("\r\n")
                if line.startswith("#") or line == "":
                    continue
                if p.game is None:
                    if m := re.fullmatch(r"@seed (\S+)", line):
                        seed = m.group(1)
                        continue
                    if m := re.fullmatch(r"@clock (\d+)", line):
                        clock = int(m.group(1))
                        continue
                    if m := re.fullmatch(r"@updates (\S+)", line):
                        updates = m.group(1)
                        continue
                    if m := re.fullmatch(r"@place (\S+) (\S+)", line):  # a fixture file, before boot reads it
                        src, dest = area / ".." / "files" / m.group(1)[:63], area / m.group(2)[:127]
                        if not src.is_file():
                            raise SystemExit(f"scenario: @place {m.group(1)} {m.group(2)}: can't copy it")
                        dest.write_bytes(src.read_bytes())
                        continue
                    p.boot(seed, clock, updates)
                n += 1
                p.step(n, line)
    except (NotPorted, CWouldCrash) as e:
        p.out.append(f"stopped {type(e).__name__}: {e}")
    finally:
        rng.random = real_random
        for c in p.conns:
            c.peer.close()
            try:
                c.d.sock.close()
            except OSError:
                pass
    return p.out
