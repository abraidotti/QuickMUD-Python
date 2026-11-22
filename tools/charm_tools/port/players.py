"""charm_tools port players: the player files the C game saved load and save the same in the Python game (#25
decision 6, #30 decision 4).

tools/tests/data/players holds what the C game wrote, captured before cut-over (the c-final tag has the live
round trips): Newbie, a character it made, and Shemp and Smokegod after logging in with the fixtures. Each is
compared with the Python game's save, section by section and key by key, without the two keys that depend on the
clock (LogO, the logoff time, and Plyd, the time played).

The Python side runs in-process (load_char_obj, then save_char_obj) from a throwaway copy of area/, with its
clock set to the file's logoff time, so loading doesn't heal anyone.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..paths import area_dir, use_game
from .live import fixtures

SKIP = {"LogO", "Plyd"}
NAME = "Newbie"
FIXTURE_PASSWORDS = (("Shemp", "psswrd"), ("Smokegod", "smoke123"))


def saved_dir() -> Path:
    """The C game's files, saved before cut-over."""
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


def run() -> int:
    """The C game's saved files, each loaded and saved by the Python game."""
    failed = 0

    def report(label: str, diffs: list[str]) -> None:
        nonlocal failed
        print(f"{'SAME' if not diffs else 'DIFFERENT':9} {label}", flush=True)
        for d in diffs[:8]:
            print(f"    {d}")
        failed += bool(diffs)

    c_file = (saved_dir() / NAME).read_text(encoding="latin-1")
    report("a new character the C game saved, loaded and saved by Python",
           compare(c_file, python_resave(c_file, NAME), "C", "Python"))
    for who, password in FIXTURE_PASSWORDS:
        c_saved = (saved_dir() / f"{who}.after-login").read_text(encoding="latin-1")
        now = int(next(line.split()[1] for line in c_saved.splitlines() if line.startswith("LogO")))
        fixture = (fixtures() / "player" / who).read_text(encoding="latin-1")
        report(f"the {who} fixture: saved after logging in, on each game",
               compare(c_saved, python_resave(fixture, who, now, password), "C", "Python"))
    print("all the same" if not failed else f"{failed} file(s) differ")
    return 1 if failed else 0
