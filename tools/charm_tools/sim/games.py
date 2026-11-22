"""The game a Sim trial runs against: the Python game here, from a throwaway root.

It starts fresh from the fixtures (tools/fixtures: qmconfig.rc and the player files) and a fixed CHARM_SEED, and
can say whether it's still up, what it logged, and why it stopped. (Until cut-over the trials ran the C game too,
and compared the two; that's at the c-final tag.)
"""

from __future__ import annotations

import subprocess
import sys
import time

from .smoke import connect


class Down(Exception):
    """The game stopped, or stopped answering."""


class PyGame:
    """The Python game, from a throwaway root (port.live.PyGame)."""

    kind = "Python"

    def __init__(self, qmconfig: str | None = "fixture", players: tuple[str, ...] = ()):
        from ..port.live import PyGame as Live

        self.live = Live(qmconfig, players)

    def __enter__(self):
        self.live.__enter__()
        self.port = self.live.port
        return self

    def alive(self) -> bool:
        return self.live.proc.poll() is None

    def log(self) -> str:
        return self.live.game_log()

    def why_down(self) -> str:
        code = self.live.proc.poll()
        tail = [line for line in self.log().splitlines() if line.strip()][-1:]
        return f"exit status {code}" + (f": {tail[0].strip()[:200]}" if tail else "")

    def restart(self) -> None:
        self.live.log.close()
        self.live.start()

    def __exit__(self, *exc):
        self.live.__exit__(*exc)


def open_game(qmconfig: str | None = "fixture", players: tuple[str, ...] = ()):
    return PyGame(qmconfig, players)


def answering(game, timeout: float = 10.0) -> bool:
    """Is the game up and greeting new connections? (A process can be alive and stuck.)"""
    if not game.alive():
        return False
    try:
        s = connect("127.0.0.1", game.port, timeout, timeout)
    except ConnectionError:
        return False
    s.close()
    return True


def bug_lines(log: str) -> list[str]:
    """The log's [*****] lines, without their timestamps."""
    return [line.split("[*****]", 1)[1].strip() for line in log.splitlines() if "[*****]" in line]


def wait_up(game, wait: float = 60.0) -> None:
    deadline = time.monotonic() + wait
    while not answering(game, 5.0):
        if not game.alive() or time.monotonic() > deadline:
            raise Down(f"the {game.kind} game didn't come up ({game.why_down()})")
        time.sleep(0.5)


def run_wsl(trial: str, argv: list[str], distro: str) -> int:
    """`sim TRIAL --python ARGS` inside WSL: this checkout through /mnt. The script goes to wsl.exe on stdin, as
    bytes (a Xania gotcha), and wsl.exe's exit code is the trial's."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    win = str(root / "tools").replace("\\", "/")
    script = (f'set -e\ncd "$(wslpath -a \'{win}\')"\n'
              f"exec python3 -m charm_tools sim {trial} --python {' '.join(argv)}\n")
    try:
        return subprocess.run(["wsl.exe", *(["-d", distro] if distro else []), "--", "bash", "-s"],
                              input=script.encode(), timeout=7200).returncode
    except FileNotFoundError:
        print("wsl.exe not found: --wsl needs Windows with WSL", file=sys.stderr)
        return 2

