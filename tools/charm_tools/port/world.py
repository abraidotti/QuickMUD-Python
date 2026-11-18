"""charm_tools port world: boot the C game's world and the Python game's, and compare them line by line.

The C side is tools/oracle/worldcheck.c, built in the game's build-stage image against the game's own object files
(like port rng). Both sides boot with the same CHARM_SEED and clock, run more area_update passes, and print the
same plain-text dump:
- the prototypes after loading
- every room's light, people, contents and exits
- every mob and object in list order, with its numbers and affects
- the next three random numbers, which shows that both sides drew as many
The game's log lines (bug() and log_f) are compared too, without timestamps.

A saved capture (tools/tests/data/world-SEED.txt.xz, with its log) lets the tests compare without Docker.
"""

from __future__ import annotations

import lzma
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..paths import area_dir, find_root, use_game

SEED = "20261117"
TIME = "1763400000"  # 14:00 on day 20 of month 1 of the game year: daylight, and the 1-80 weather draw
UPDATES = 3
MAX_VNUM = 32768

BUILD = r"""
set -e
cd /opt/charm/src
gcc -O -g3 -Wall -std=gnu17 -fcommon -Dmain=game_main -c -o /tmp/comm_nomain.o comm.c 2>/dev/null
gcc -O -g3 -Wall -std=gnu17 -fcommon -I. -o /tmp/worldcheck /oracle/worldcheck.c \
    $(ls obj/*.o | grep -v '^obj/comm\.o$') /tmp/comm_nomain.o -lcrypt
mkdir -p /opt/charm/notes /opt/charm/log /opt/charm/player /opt/charm/gods
cd /opt/charm/area
/tmp/worldcheck "$@"
"""


@dataclass
class Capture:
    dump: list[str]
    log: list[str]


def fixture_path(seed: str = SEED, root: Path | None = None) -> Path:
    return (root or find_root()) / "tools" / "tests" / "data" / f"world-{seed}.txt.xz"


def _strip_time(line: str) -> str:
    return line.split(" :: ", 1)[1] if " :: " in line else line


def comparable_log(lines: list[str]) -> list[str]:
    """The log lines both sides print: "Loading area" lines are left out (the Python loader doesn't log them)."""
    return [x for x in lines if not x.startswith("Loading area ")]


# -- the Python side -------------------------------------------------------------------------------------------

def _s(text: str | None) -> str:
    text = text or ""
    return '"' + text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace('"', '\\"') + '"'


def _affects(out: list[str], affs) -> None:
    for a in affs:
        out.append(f"  aff where={a.where} type={a.type} level={a.level} duration={a.duration} "
                   f"location={a.location} modifier={a.modifier} bits={a.bitvector}")


def prototypes(game) -> list[str]:
    ix = game.index
    out = [f"area {i} min={a.min_vnum} max={a.max_vnum} {_s(a.name)}" for i, a in enumerate(ix.areas)]
    for vnum in sorted(ix.mobs):
        m = ix.mobs[vnum]
        out.append(
            f"mobindex {vnum} act={m.act} aff={m.affected_by} off={m.off_flags} imm={m.imm_flags} "
            f"res={m.res_flags} vuln={m.vuln_flags} form={m.form} parts={m.parts} race={m.race} size={m.size} "
            f"sex={m.sex} pos={m.start_pos},{m.default_pos} dam_type={m.dam_type} wealth={m.wealth} "
            f"level={m.level} hitroll={m.hitroll} align={m.alignment} group={m.group} "
            f"hit={','.join(map(str, m.hit))} mana={','.join(map(str, m.mana))} "
            f"damage={','.join(map(str, m.damage))} ac={','.join(map(str, m.ac))} mprog_flags={m.mprog_flags} "
            f"new={int(m.new_format)} shop={int(m.shop is not None)} spec={m.spec_fun or '-'} "
            f"{_s(m.material)} {_s(m.player_name)} {_s(m.short_descr)} {_s(m.long_descr)} {_s(m.description)}")
        for mp in m.mprogs:
            out.append(f"  mprog trig={mp.trig_type} vnum={mp.vnum} {_s(mp.trig_phrase)}")
    for vnum in sorted(ix.objs):
        o = ix.objs[vnum]
        out.append(
            f"objindex {vnum} type={o.item_type} extra={o.extra_flags} wear={o.wear_flags} "
            f"values={','.join(map(str, o.value))} level={o.level} weight={o.weight} cost={o.cost} "
            f"condition={o.condition} new={int(o.new_format)} {_s(o.material)} {_s(o.name)} "
            f"{_s(o.short_descr)} {_s(o.description)}")
        _affects(out, o.affected)
        for ed in o.extra_descr:
            out.append(f"  ed {_s(ed.keyword)}")
    return out


def state(game, n: int) -> list[str]:
    from charm.core.rng import number_mm

    ix = game.index
    ci = {id(c): i for i, c in enumerate(game.char_list)}
    oi = {id(o): i for i, o in enumerate(game.object_list)}

    def objs(objs) -> str:
        return ",".join(str(oi.get(id(o), -1)) for o in objs)

    t, w = game.time_info, game.weather_info
    out = [f"dump {n}", f"time hour={t.hour} day={t.day} month={t.month} year={t.year}",
           f"weather mmhg={w.mmhg} change={w.change} sky={w.sky} sunlight={w.sunlight}"]
    out += [f"areastate {i} age={a.age} nplayer={a.nplayer} empty={int(a.empty)}" for i, a in enumerate(ix.areas)]
    for vnum in sorted(ix.rooms):
        r = ix.rooms[vnum]
        people = ",".join(str(ci.get(id(c), -1)) for c in r.people)
        out.append(f"room {vnum} light={r.light} flags={r.room_flags} people={people} contents={objs(r.contents)}")
        for d, e in enumerate(r.exit):
            if e is not None:
                to = e.to_room.vnum if e.to_room is not None else -1
                out.append(f"  exit {d} to={to} info={e.exit_info} rs={e.rs_flags} key={e.key} orig={e.orig_door}")
    for vnum in range(MAX_VNUM):
        if vnum in ix.mobs:
            out.append(f"mobcount {vnum} {ix.mobs[vnum].count}")
        if vnum in ix.objs:
            out.append(f"objcount {vnum} {ix.objs[vnum].count}")
    for i, c in enumerate(game.char_list):
        out.append(
            f"char {i} vnum={c.index.vnum if c.index else -1} id={c.id} "
            f"room={c.in_room.vnum if c.in_room else -1} level={c.level} hit={c.hit}/{c.max_hit} "
            f"mana={c.mana}/{c.max_mana} move={c.move}/{c.max_move} gold={c.gold} silver={c.silver} sex={c.sex} "
            f"race={c.race} size={c.size} dam_type={c.dam_type} act={c.act} comm={c.comm} aff={c.affected_by} "
            f"off={c.off_flags} imm={c.imm_flags} res={c.res_flags} vuln={c.vuln_flags} form={c.form} "
            f"parts={c.parts} pos={c.position},{c.start_pos},{c.default_pos} align={c.alignment} "
            f"hitroll={c.hitroll} damroll={c.damroll} saves={c.saving_throw} group={c.group} "
            f"armor={','.join(map(str, c.armor))} damage={','.join(map(str, c.damage))} "
            f"perm={','.join(map(str, c.perm_stat))} mod={','.join(map(str, c.mod_stat))} "
            f"carry={c.carry_number},{c.carry_weight} {_s(c.material)} {_s(c.name)} carrying={objs(c.carrying)}")
        _affects(out, c.affected)
    for i, o in enumerate(game.object_list):
        if o.in_room is not None:
            where = f"room:{o.in_room.vnum}"
        elif o.carried_by is not None:
            where = f"char:{ci.get(id(o.carried_by), -1)}"
        elif o.in_obj is not None:
            where = f"obj:{oi.get(id(o.in_obj), -1)}"
        else:
            where = "-"
        out.append(
            f"obj {i} vnum={o.index.vnum} in={where} wear={o.wear_loc} type={o.item_type} level={o.level} "
            f"cost={o.cost} timer={o.timer} values={','.join(map(str, o.value))} extra={o.extra_flags} "
            f"wearflags={o.wear_flags} weight={o.weight} condition={o.condition} enchanted={int(o.enchanted)} "
            f"{_s(o.material)} {_s(o.name)} contains={objs(o.contains)}")
        _affects(out, o.affected)
    out.append(f"count mobiles={game.mobile_count}")
    a, b, c = number_mm(), number_mm(), number_mm()
    out.append(f"rng {a} {b} {c}")
    return out


def python_world(seed: str = SEED, now: str = TIME, updates: int = UPDATES, root: Path | None = None) -> Capture:
    """Boot the Python game the way worldcheck boots the C one, and dump it the same way."""
    use_game(root)
    from charm.core import log
    from charm.entities.boot import boot_db
    from charm.entities.resets import area_update

    with log.capture() as lines:
        game = boot_db(area_dir(root), int(now), {"CHARM_SEED": seed})
        dump = prototypes(game) + state(game, 0)
        for n in range(1, updates + 1):
            area_update(game)
            dump += state(game, n)
    return Capture(dump, comparable_log(list(lines)))


# -- the C side ------------------------------------------------------------------------------------------------

def c_world(image: str, seed: str = SEED, now: str = TIME, updates: int = UPDATES,
            root: Path | None = None) -> Capture:
    root = root or find_root()
    oracle = root / "tools" / "oracle"
    cmd = ["docker", "run", "--rm", "-v", f"{oracle}:/oracle:ro", image, "sh", "-c", BUILD, "worldcheck", seed,
           now, str(updates)]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="latin-1")
    if out.returncode != 0:
        raise RuntimeError(f"worldcheck failed in {image}:\n{out.stderr.strip()[-2000:]}")
    log = [_strip_time(x) for x in out.stderr.splitlines() if " :: " in x]
    return Capture(out.stdout.splitlines(), comparable_log(log))


def save(capture: Capture, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(capture.dump) + "\n=== log\n" + "\n".join(capture.log) + "\n"
    path.write_bytes(lzma.compress(text.encode("latin-1"), preset=9 | lzma.PRESET_EXTREME))


def load(path: Path) -> Capture:
    text = lzma.decompress(path.read_bytes()).decode("latin-1")
    dump, _, log = text.partition("\n=== log\n")
    return Capture(dump.split("\n"), [x for x in log.split("\n") if x])


# -- comparing -------------------------------------------------------------------------------------------------

def compare(c: Capture, py: Capture, limit: int = 10) -> list[str]:
    """Readable differences, C first then Python: the first `limit` differing dump lines (with what they belong
    to), and the first differing log line."""
    diffs = []
    head = ""
    for i, (a, b) in enumerate(zip(c.dump, py.dump)):
        if not a.startswith(" "):
            head = a.split(" ", 2)[0] + " " + (a.split(" ", 2)[1] if " " in a else "")
        if a != b:
            at = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            lo = max(0, at - 60)
            diffs.append(f"dump line {i + 1} ({head.strip()}), from column {at + 1}:\n"
                         f"    C:      ...{a[lo:at + 120]}\n    Python: ...{b[lo:at + 120]}")
            if len(diffs) >= limit:
                break
    if len(c.dump) != len(py.dump):
        diffs.append(f"dump length: C {len(c.dump)} lines, Python {len(py.dump)}")
    for i, (a, b) in enumerate(zip(c.log, py.log)):
        if a != b:
            diffs.append(f"log line {i + 1}:\n    C:      {a}\n    Python: {b}")
            break
    if len(c.log) != len(py.log):
        diffs.append(f"log length: C {len(c.log)} lines, Python {len(py.log)}")
    return diffs


def summary(cap: Capture) -> str:
    dumps = [x for x in cap.dump if x.startswith("dump ")]
    chars = sum(1 for x in cap.dump if x.startswith("char "))
    objs = sum(1 for x in cap.dump if x.startswith("obj "))
    return (f"{len(cap.dump)} dump lines ({len(dumps)} dumps, {chars} mob and {objs} object lines in all), "
            f"{len(cap.log)} log lines")


def run(image: str | None, seeds: list[str], now: str, updates: int, save_fixture: bool) -> int:
    failed = 0
    for seed in seeds:
        print(f"seed {seed}, clock {now}, {updates} more area_update passes", flush=True)
        if image:
            try:
                c = c_world(image, seed, now, updates)
            except (OSError, RuntimeError) as e:
                print(f"  couldn't run the C side: {e}")
                return 2
            if save_fixture:
                save(c, fixture_path(seed))
                print(f"  saved the C capture to {fixture_path(seed)}")
        else:
            path = fixture_path(seed)
            if not path.exists():
                print(f"  no saved capture at {path}; run with --docker IMAGE")
                return 2
            c = load(path)
        print(f"  C:      {summary(c)}")
        py = python_world(seed, now, updates)
        print(f"  Python: {summary(py)}")
        diffs = compare(c, py)
        for d in diffs:
            print(f"  differs  {d}")
        print("  SAME" if not diffs else f"  {len(diffs)} difference(s)")
        failed += bool(diffs)
    return 1 if failed else 0
