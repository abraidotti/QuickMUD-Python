"""charm_tools port players: player files saved by each game load in the other (#25 decision 6, #30 decision 4).

Three round trips, each compared section by section and key by key, without the two keys that depend on the
clock (LogO, the logoff time, and Plyd, the time played):
1. C to Python: the C game (a container) creates a character, enters the game, saves and quits. The Python game
   loads that file and saves it.
2. Python to C: the C game logs in with the Python game's file, saves and quits.
3. The fixtures (tools/fixtures/player): each game logs in with them and saves, and the two are compared. The
   C enters the game first; the Python, until spike PR 5, stops at the MOTD.

The Python side runs in-process (load_char_obj, then save_char_obj) from a throwaway copy of area/, with its
clock set to the file's logoff time, so loading doesn't heal anyone. Until spike PR 5 it can't enter the game.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..paths import area_dir, use_game
from .live import CGame, fixtures
from .login import NEW

SKIP = {"LogO", "Plyd"}
NAME = "Newbie"
FIXTURE_PASSWORDS = (("Shemp", "psswrd"), ("Smokegod", "smoke123"))


def saved_dir() -> Path:
    """Where --save keeps the C game's files, for tools/tests/test_players.py."""
    from ..paths import find_root
    return find_root() / "tools" / "tests" / "data" / "players"


def sections(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(section, [(key, rest of the line), ...]), ...] in file order."""
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            out.append((line.strip(), []))
            continue
        key, _, rest = line.partition(" ")
        if out and key not in SKIP:
            out[-1][1].append((key, rest))  # exactly as written: "Titl  the Recruit~" has two spaces
    return out


def compare(a: str, b: str, a_name: str, b_name: str) -> list[str]:
    sa, sb = sections(a), sections(b)
    diffs = []
    if [s for s, _ in sa] != [s for s, _ in sb]:
        diffs.append(f"sections: {a_name} {[s for s, _ in sa]}, {b_name} {[s for s, _ in sb]}")
    for i, ((name, ka), (_, kb)) in enumerate(zip(sa, sb)):
        if ka != kb:
            for x, y in zip(ka, kb):
                if x != y:
                    diffs.append(f"section {i} ({name}): {a_name} {x[0]} {x[1]!r}, {b_name} {y[0]} {y[1]!r}")
                    break
            if len(ka) != len(kb):
                diffs.append(f"section {i} ({name}): {len(ka)} keys in {a_name}, {len(kb)} in {b_name}")
    return diffs


def python_resave(text: str, name: str, now: int | None = None, password: str | None = None) -> str:
    """Load a player file in the Python game and save it again; the saved text. The clock is the file's logoff
    time (so loading heals nobody), or `now`. With a password, the file is loaded the way logging in loads it:
    the real nanny takes the name and the password (which sets or clears PLR_COLOUR for the connection)."""
    use_game()
    from charm.core import log
    from charm.entities.boot import boot_db
    from charm.net.config import Config
    from charm.net.descriptor import new_descriptor
    from charm.net.nanny import nanny
    from charm.persist.player import load_char_obj, save_char_obj

    from .io import pipe_pair

    root = Path(tempfile.mkdtemp(prefix="charm-players-"))
    try:
        shutil.copytree(area_dir(), root / "area")
        for d in ("player", "gods"):
            (root / d).mkdir()
        (root / "player" / name).write_text(text, encoding="latin-1", newline="\n")
        logoff = int(next(line.split()[1] for line in text.splitlines() if line.startswith("LogO")))
        with log.capture():
            game = boot_db(root / "area", logoff if now is None else now, {"CHARM_SEED": "1"})
            game.config = Config()  # tools/fixtures/qmconfig.rc: ANSI off
            d = new_descriptor()
            d.game, d.sock, d.host = game, pipe_pair()[0], "localhost"
            game.descriptor_list.insert(0, d)
            if password is None:
                if not load_char_obj(game, d, name):
                    raise RuntimeError(f"the Python game found no file for {name}")
            else:
                nanny(game, d, name)
                nanny(game, d, password)
                if d.connected not in (game_const().CON_READ_MOTD, game_const().CON_READ_IMOTD):
                    raise RuntimeError(f"logging in as {name} on the Python game didn't reach the MOTD")
            save_char_obj(game, d.character)
        return (root / "player" / name).read_text(encoding="latin-1")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def game_const():
    from charm.data import constants
    return constants


def c_login_save(c: CGame, name: str, password: str, new: bool = False) -> str:
    """Log in on the C game, enter the game, save, quit; the file it wrote."""
    s = c.session()
    if new:
        for line in NEW:
            s.send(line)
    else:
        s.send(name)
        s.send(password)
    for _ in range(3):  # past the MOTD (an immortal gets the IMOTD first): entering ends with the board list
        if b"You current board is" in s.send(""):
            break
    s.send("save")
    s.send("quit")
    s.close()
    return c.player_file(name)


def run(image: str, save: bool = False) -> int:
    failed = 0
    kept: dict[str, str] = {}

    def report(label: str, diffs: list[str]) -> None:
        nonlocal failed
        print(f"{'SAME' if not diffs else 'DIFFERENT':9} {label}", flush=True)
        for d in diffs[:8]:
            print(f"    {d}")
        failed += bool(diffs)

    with CGame(image) as c:
        c_file = c_login_save(c, NAME, "secret1", new=True)
    kept[NAME] = c_file
    py_file = python_resave(c_file, NAME)
    report("C to Python: a new character the C game saved, loaded and saved by Python",
           compare(c_file, py_file, "C", "Python"))

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / NAME
        path.write_text(py_file, encoding="latin-1", newline="\n")
        with CGame(image, players=()) as c:
            c.put_player(path)
            back = c_login_save(c, NAME, "secret1")
    report("Python to C: that file as the Python game saved it, logged in on the C game and saved",
           compare(py_file, back, "Python", "C"))

    for who, password in FIXTURE_PASSWORDS:
        fixture = (fixtures() / "player" / who).read_text(encoding="latin-1")
        with CGame(image, players=(who,)) as c:
            c_saved = c_login_save(c, who, password)
            now = int(next(line.split()[1] for line in c_saved.splitlines() if line.startswith("LogO")))
        kept[f"{who}.after-login"] = c_saved
        # The C logged in long after the fixture's logoff and healed it; the Python loads at the same moment.
        report(f"the {who} fixture: saved after logging in, on each game",
               compare(c_saved, python_resave(fixture, who, now, password), "C", "Python"))
    if save:
        saved_dir().mkdir(parents=True, exist_ok=True)
        for name, text in kept.items():
            (saved_dir() / name).write_text(text, encoding="latin-1", newline="\n")
        print(f"saved the C game's files to {saved_dir()}")
    print("all the same" if not failed else f"{failed} round trip(s) differ")
    return 1 if failed else 0
