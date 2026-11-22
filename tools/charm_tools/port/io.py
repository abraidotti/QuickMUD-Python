"""charm_tools port io: the C game's input and output code against the Python game's, case by case.

The cases are tools/tests/data/iocases.txt, a small script. Before cut-over, tools/oracle/iocheck.c (at the c-final
tag) ran it through the C game's own comm.c, over a real socketpair, and its results are tools/tests/data/io.txt.
This module runs the cases through the Python game's, over an in-memory pair, so the results don't depend on the
platform's loopback timing, and compares the printed results and the log lines.
"""

from __future__ import annotations

import re
import types
from dataclasses import dataclass
from pathlib import Path

from ..paths import find_root, use_game

@dataclass
class Capture:
    out: list[str]
    log: list[str]


def cases_path(root: Path | None = None) -> Path:
    return (root or find_root()) / "tools" / "tests" / "data" / "iocases.txt"


def fixture_path(root: Path | None = None) -> Path:
    return (root or find_root()) / "tools" / "tests" / "data" / "io.txt"


def unesc(s: str) -> str:
    out, i = [], 0
    simple = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "e": "\x1b", "s": " "}
    while i < len(s):
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        c = s[i] if i < len(s) else ""
        if c == "x":
            out.append(chr(int(s[i + 1:i + 3], 16)))
            i += 3
            continue
        out.append(simple.get(c, c))
        i += 1
    return "".join(out)


def esc(s: str) -> str:
    out = []
    for c in s:
        o = ord(c)
        if c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif 32 <= o < 127:
            out.append(c)
        else:
            out.append(f"\\x{o:02x}")
    return "".join(out)


class Pipe:
    """One end of an in-memory, non-blocking socket pair."""

    def __init__(self):
        self.inbox = bytearray()
        self.other: Pipe | None = None

    def send(self, data: bytes) -> int:
        self.other.inbox += data
        return len(data)

    def recv(self, n: int) -> bytes:
        if n == 0:
            return b""
        if not self.inbox:
            raise BlockingIOError()
        data = bytes(self.inbox[:n])
        del self.inbox[:n]
        return data

    def close(self) -> None:
        pass


def pipe_pair() -> tuple[Pipe, Pipe]:
    a, b = Pipe(), Pipe()
    a.other, b.other = b, a
    return a, b


def python_io(cases: str) -> Capture:
    use_game()
    from charm.core import log
    from charm.data import constants as C
    from charm.entities import game as game_module
    from charm.entities.game import Game
    from charm.entities.handler import char_to_room
    from charm.entities.things import Obj, new_char
    from charm.net import output, prompt
    from charm.net.act import act_new
    from charm.net.descriptor import new_descriptor
    from charm.net.input import read_from_buffer, read_from_descriptor
    from charm.world.index import Area, Index, Room

    game = Game(Index([], {}, {}, {}), 0)
    game_module.current = game
    area = Area(0, "t.are", "Test", "", 0, 0)
    room = Room(1, "A Test Room", "", area, 0, 0)
    mob_index = types.SimpleNamespace(vnum=1, mprog_flags=0)
    obj_index = types.SimpleNamespace(vnum=1)
    descs, peers, chars, objs = [], [], [], []
    cur = {"d": None, "peer": None, "ch": None}
    out: list[str] = []
    numbers = {"hit", "max_hit", "mana", "max_mana", "move", "max_move", "exp", "gold", "silver", "alignment",
               "level", "wait", "sex", "act", "comm", "affected_by", "trust", "invis_level", "lines", "position"}
    kinds = {"TO_ROOM": C.TO_ROOM, "TO_NOTVICT": C.TO_NOTVICT, "TO_VICT": C.TO_VICT, "TO_CHAR": C.TO_CHAR}

    def recv_all() -> str:
        data = bytes(cur["peer"].inbox)
        cur["peer"].inbox.clear()
        return " recv=" + esc(data.decode("latin-1"))

    def char_arg(t):
        return None if t == "-" else chars[int(t)]

    def obj_arg(t):
        return None if t == "-" else objs[int(t)]

    with log.capture() as lines:
        for raw in cases.splitlines():
            if not raw or raw.startswith("#"):
                continue
            cmd, _, rest = raw.partition(" ")
            d, ch = cur["d"], cur["ch"]
            line = cmd
            if cmd == "new":
                d = new_descriptor()
                ours, theirs = pipe_pair()
                d.sock, d.game, d.connected, d.host = ours, game, int(rest), "test"
                game.descriptor_list.insert(0, d)
                descs.append(d)
                peers.append(theirs)
                cur["d"], cur["peer"] = d, theirs
                line += f" {len(descs) - 1}"
            elif cmd == "ansi":
                d.ansi = bool(int(rest))
            elif cmd == "fcommand":
                d.fcommand = bool(int(rest))
            elif cmd == "inbuf":
                d.inbuf = unesc(rest)
            elif cmd == "send":
                cur["peer"].send(unesc(rest).encode("latin-1"))
            elif cmd == "read":
                line += f" {int(read_from_descriptor(d))} inbuf={esc(d.inbuf)}" + recv_all()
            elif cmd == "buffer":
                read_from_buffer(d)
                line += (f" incomm={esc(d.incomm)} inlast={esc(d.inlast)} repeat={d.repeat} inbuf={esc(d.inbuf)}"
                         + recv_all())
                d.incomm = ""
            elif cmd == "out":
                n, _, s = rest.partition(" ")
                output.write_to_buffer(d, unesc(s), int(n))
                line += f" outtop={d.outtop} outsize={d.outsize}"
            elif cmd == "desc":
                output.send_to_desc(unesc(rest), d)
            elif cmd == "flush":
                line += f" {int(output.process_output(d, bool(int(rest))))}" + recv_all()
            elif cmd == "recv":
                line += recv_all()
            elif cmd == "show":
                output.show_string(d, unesc(rest))
                line += f" more={int(d.showstr_point is not None)}"
            elif cmd in ("pc", "npc"):
                ch = new_char(0)
                if cmd == "pc":
                    ch.name, ch.desc = "Tester", d
                    d.character, d.connected = ch, C.CON_PLAYING
                else:
                    ch.act, ch.index, ch.short_descr, ch.name = C.ACT_IS_NPC, mob_index, unesc(rest), "mob"
                char_to_room(ch, room)
                chars.append(ch)
                cur["ch"] = ch
                line += f" {len(chars) - 1}"
            elif cmd == "use":
                ch = cur["ch"] = chars[int(rest)]
                if ch.desc is not None:
                    i = descs.index(ch.desc)
                    cur["d"], cur["peer"] = descs[i], peers[i]
            elif cmd == "set":
                field, value = rest.split()
                if field == "connected":
                    ch.desc.connected = int(value)
                elif field in numbers:
                    setattr(ch, field, int(value))
                else:
                    raise ValueError(f"iocases: no field {field}")
            elif cmd == "str":
                field, _, s = rest.partition(" ")
                setattr(ch, {"name": "name", "short": "short_descr", "prompt": "prompt", "prefix": "prefix"}[field],
                        unesc(s))
            elif cmd == "room":
                flags, sector, light = (int(x) for x in rest.split())
                room.room_flags, room.sector_type, room.light = flags, sector, light
            elif cmd == "roomname":
                room.name = unesc(rest)
            elif cmd == "sun":
                game.weather_info.sunlight = int(rest)
            elif cmd == "obj":
                n, _, s = rest.partition(" ")
                objs.append(Obj(index=obj_index, extra_flags=int(n), item_type=C.ITEM_TRASH, short_descr=unesc(s)))
                line += f" {len(objs) - 1}"
            elif cmd == "char":
                output.send_to_char(unesc(rest), ch)
            elif cmd == "page":
                output.page_to_char(unesc(rest), ch)
                line += f" more={int(d.showstr_point is not None)}"
            elif cmd == "prompt":
                prompt.bust_a_prompt(ch)
            elif cmd == "colour":
                who, codes = rest.split()
                line += "".join(f" {c}={esc(output.colour(c, char_arg(who)))}" for c in codes)
            elif cmd in ("act", "actt"):
                m = re.match(r"(\S+) (\S+) (\S+) (\S+) (.*)$", rest)
                kind, a, b, c, fmt = m.groups()
                if cmd == "act":
                    act_new(unesc(fmt), char_arg(a), obj_arg(b), char_arg(c), kinds[kind], C.POS_RESTING)
                else:
                    t1 = None if b == "-" else unesc(b)
                    t2 = None if c == "-" else unesc(c)
                    act_new(unesc(fmt), char_arg(a), t1, t2, kinds[kind], C.POS_RESTING)
            else:
                raise ValueError(f"iocases: unknown command {cmd}")
            out.append(line)
    return Capture(out, list(lines))


def load(path: Path) -> Capture:
    out, _, log = path.read_text(encoding="latin-1").partition("\n=== log\n")
    return Capture(out.split("\n"), [x for x in log.split("\n") if x])


def compare(c: Capture, py: Capture, limit: int = 10) -> list[str]:
    diffs = []
    for i, (a, b) in enumerate(zip(c.out, py.out)):
        if a != b:
            diffs.append(f"result {i + 1}:\n    C:      {a[:300]}\n    Python: {b[:300]}")
            if len(diffs) >= limit:
                break
    if len(c.out) != len(py.out):
        diffs.append(f"results: C {len(c.out)}, Python {len(py.out)}")
    if c.log != py.log:
        diffs.append(f"log differs:\n    C:      {c.log}\n    Python: {py.log}")
    return diffs


def run() -> int:
    cases = cases_path().read_text(encoding="latin-1")
    if not fixture_path().exists():
        print(f"no saved capture at {fixture_path()}")
        return 2
    c = load(fixture_path())
    py = python_io(cases)
    print(f"{len(c.out)} results and {len(c.log)} log lines from C, {len(py.out)} and {len(py.log)} from Python")
    diffs = compare(c, py)
    for d in diffs:
        print(f"  differs  {d}")
    print("SAME" if not diffs else f"{len(diffs)} difference(s)")
    return 1 if diffs else 0
