"""charm_tools port commands: the same sessions in the game, against the C game and the Python game (#32).

Like port login, each scenario starts a fresh game on each side and compares, byte for byte, what comes back
after every line. Both games run with CHARM_UPDATES=area, so only area_update runs, and the two worlds stay the
same: no mob wanders, no weather message arrives, and the random numbers stay in step.

The scenarios stay in Midgaard's temple and city rooms, which are never dark, so the game hour (from the clock,
which differs by a few seconds between the two games) doesn't change what they see.

The fixture players (tools/fixtures/player):
- Shemp, the stock file
- Rambler, in the temple, with autoexit on and two aliases (gs = score, gl = look)
- Weary, in the temple, with no movement points left
"""

from __future__ import annotations

from .live import CGame, PyGame
from .login import Scenario, compare, run_scenario

PLAYERS = ("Shemp", "Rambler", "Weary")


def _login(who: int, name: str, password: str = "psswrd") -> list[tuple[int, str]]:
    return [(who, name), (who, password), (who, "")]


def _one(name: str, lines: list[str]) -> list[tuple[int, str]]:
    return _login(0, name) + [(0, x) for x in lines]


SCENARIOS = [
    Scenario("looking around the temple", _one("Rambler", [
        "look", "look hassan", "look self", "look plaque", "look 2.plaque", "look nothing", "look n", "look w",
        "look up", "look in", "look in nothing", "exits", "exits auto", "gl", "gs", "sco", "l"])),  # sc is scan
    Scenario("walking a loop through Midgaard", _one("Rambler", [
        "s", "look in fountain", "s", "look statue", "look 2.statue", "w", "w", "e", "east", "north", "n",
        "n", "look in pit", "look statue", "look 2.statue", "look 3.statue", "s", "w", "u", "d"])),
    Scenario("walking with no movement points, and into walls", _one("Weary", [
        "s", "w", "e", "north", "score"])),
    Scenario("two players in the temple: socials, looking at each other", _login(0, "Rambler") + _login(1, "Weary")
             + [(0, "look"), (1, "smile"), (1, "smile rambler"), (0, "bow weary"), (0, "bow self"),
                (0, "smile nobody"), (0, "smile hassan"), (0, "grin hassan"), (0, "wave hassan"), (1, "xyzzy"),
                (1, "look rambler"), (0, "look weary"), (0, "s"), (1, "look"), (0, "n"), (1, "look"),
                (0, "quit"), (1, "look")]),
    Scenario("score, title and prompt", _one("Shemp", [
        "score", "title", "title {", "title x", "title the Brave{", "title the Brave{{", "title the Brave",
        "title " + "a" * 60, "score", "prompt", "prompt", "prompt all", "prompt <%h %W>", "prompt <%c",
        "prompt " + "b" * 60, "prompt <%W> ", "quit"])),
    Scenario("save, its lag on the prompt, then quit", _one("Shemp", [
        "prompt <%W> ", "save", "look", "quit"])),
]


def run(image: str, only: str | None = None) -> int:
    failed = 0
    for sc in SCENARIOS:
        if only and only.lower() not in sc.name.lower():
            continue
        c = run_scenario(CGame(image, sc.qmconfig, PLAYERS, area_updates_only=True), sc)
        py = run_scenario(PyGame(sc.qmconfig, PLAYERS, area_updates_only=True), sc)
        diffs = compare(c, py, sc)
        size = sum(len(x) for x in c.steps)
        print(f"{'SAME' if not diffs else 'DIFFERENT':9} {sc.name} ({len(sc.steps)} lines, {size} bytes)",
              flush=True)
        for d in diffs[:3]:
            print(f"    {d}")
        failed += bool(diffs)
    print("all the same" if not failed else f"{failed} scenario(s) differ")
    return 1 if failed else 0
