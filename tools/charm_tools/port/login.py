"""charm_tools port login: the same login sessions against the C game and the Python game, byte for byte (#30).

Each scenario starts a fresh game on each side and sends the same lines; what comes back after each line is
compared. One difference is expected and substituted before comparing: the MOTD's last line says "Welcome to
Charm." in Python where the C says "Welcome to ROM 2.4." (#30, decision 5).

Until spike PR 5 the Python game stops at do_look on entering the game, so the scenarios end before that, at the
MOTD's "[Hit Return to continue]".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .live import CGame, PyGame, Session

WELCOME_C = b"Welcome to ROM 2.4."
WELCOME_PY = b"Welcome to Charm."
NEW = ["Newbie", "y", "secret1", "secret1", "human", "m", "mage", "n", "n", "dagger"]


@dataclass
class Scenario:
    name: str
    steps: list[tuple[int, str]]  # (session number, line); a session opens on its first step
    qmconfig: str | None = "fixture"
    notes: str = ""


def _one(lines: list[str]) -> list[tuple[int, str]]:
    return [(0, x) for x in lines]


SCENARIOS = [
    Scenario("a new character to the MOTD", _one(NEW)),
    Scenario("every wrong answer on the way", _one([
        "Newbie", "x", "y", "abc", "secret1", "secret2", "secret1", "secret1", "help", "help elf", "orc", "elf",
        "q", "f", "bard", "thief", "x", "e", "x", "n", "sword"])),  # ("help elf" pages: a line goes to it)
    Scenario("customising: list, add, drop, learned, info, help, done", _one([
        "Newbie", "y", "secret1", "secret1", "dwarf", "m", "warrior", "g", "y", "list", "add axe", "add axe",
        "add bash", "learned", "drop axe", "drop nothing", "info weaponsmaster", "help add", "bogus", "done",
        "add weaponsmaster", "add enhanced damage", "learned", "done", "x", "sword"])),
    Scenario("the stock qmconfig: the ANSI question", _one(["maybe", "y", "Newbie", "y", "secret1", "secret1"]),
             qmconfig=None),
    Scenario("ANSI no", _one(["n", "Newbie"]), qmconfig=None),
    Scenario("an old character, the right password", _one(["Shemp", "psswrd"])),
    Scenario("an old character, a wrong password", _one(["Shemp", "nope"])),
    Scenario("names that aren't allowed", _one([
        "x", "someone", "Alan", "IllIll", "ABc", "Thisnameistoolong", "R2d2", "hassan", "the", "Newbie", "n",
        "Other", "y"])),
    # The name check closes the other connection's half-logged-in Shemp ("Double newbie alert"), so "already
    # playing" (check_playing) needs someone in the game: spike PR 5.
    Scenario("a second connection's name closes the first one's half-login", [
        (0, "Shemp"), (0, "psswrd"), (1, "Shemp"), (1, "psswrd"), (1, "x"), (1, "n"), (1, "Shemp"),
        (1, "psswrd")]),
    Scenario("two half-made newbies with one name", [(0, "Twin"), (0, "y"), (1, "Twin"), (1, "Twin"), (1, "y")]),
    Scenario("an empty name closes the connection", _one([""])),
]


@dataclass
class Transcript:
    steps: list[bytes] = field(default_factory=list)  # the greeting(s), then one entry per line sent


def run_scenario(game, sc: Scenario) -> Transcript:
    sessions: dict[int, Session] = {}
    t = Transcript()
    with game:
        for who, line in sc.steps:
            if who not in sessions:
                sessions[who] = game.session()
                t.steps.append(sessions[who].first)
            t.steps.append(sessions[who].send(line))
        for s in sessions.values():
            s.close()
    return t


def compare(c: Transcript, py: Transcript, sc: Scenario) -> list[str]:
    diffs = []
    labels = []
    seen = set()
    for who, line in sc.steps:
        if who not in seen:
            seen.add(who)
            labels.append(f"session {who} connects")
        labels.append(f"session {who} sends {line!r}")
    for label, a, b in zip(labels, c.steps, py.steps):
        a = a.replace(WELCOME_C, WELCOME_PY)
        if a != b:
            at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            diffs.append(f"after '{label}', at byte {at}:\n    C:      {a[max(0, at - 60):at + 100]!r}\n"
                         f"    Python: {b[max(0, at - 60):at + 100]!r}")
    if len(c.steps) != len(py.steps):
        diffs.append(f"{len(c.steps)} steps from C, {len(py.steps)} from Python")
    return diffs


def run(image: str, only: str | None = None) -> int:
    failed = 0
    for sc in SCENARIOS:
        if only and only.lower() not in sc.name.lower():
            continue
        c = run_scenario(CGame(image, sc.qmconfig), sc)
        py = run_scenario(PyGame(sc.qmconfig), sc)
        diffs = compare(c, py, sc)
        size = sum(len(x) for x in c.steps)
        print(f"{'SAME' if not diffs else 'DIFFERENT':9} {sc.name} ({len(sc.steps)} lines, {size} bytes)",
              flush=True)
        for d in diffs[:3]:
            print(f"    {d}")
        failed += bool(diffs)
    print("all the same" if not failed else f"{failed} scenario(s) differ")
    return 1 if failed else 0
