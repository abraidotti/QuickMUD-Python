"""The games a Sim trial runs against: the C game in a container, or the Python game here.

Both start fresh from the same fixtures (tools/fixtures: qmconfig.rc and the player files) and the same CHARM_SEED,
and both can say whether the game is still up, what it logged, and why it stopped. The C game runs as `rom` itself,
not under startup.sh, so a crash ends the container instead of being restarted ten seconds later.
"""

from __future__ import annotations

import subprocess
import sys
import time

from .smoke import Fail, connect, docker, free_port

SEED = "20261117"


class Down(Exception):
    """The game stopped, or stopped answering."""


class CGame:
    """The C game in a throwaway container from IMAGE, run as ./rom with no restart loop."""

    kind = "C"

    def __init__(self, image: str, qmconfig: str | None = "fixture", players: tuple[str, ...] = ()):
        self.image, self.qmconfig, self.players = image, qmconfig, players

    def __enter__(self):
        from ..port.live import fixtures

        self.port = free_port()
        self.name = f"charm-trial-{self.port}"
        docker("create", "--init", "--name", self.name, "-p", f"127.0.0.1:{self.port}:4000",
               "-e", f"CHARM_SEED={SEED}", "--entrypoint", "./rom", self.image, "4000")
        if self.qmconfig == "fixture":
            docker("cp", str(fixtures() / "qmconfig.rc"), f"{self.name}:/opt/charm/area/qmconfig.rc")
        for who in self.players:
            docker("cp", str(fixtures() / "player" / who), f"{self.name}:/opt/charm/player/{who}")
        docker("start", self.name)
        return self

    def alive(self) -> bool:
        return docker("inspect", "-f", "{{.State.Running}}", self.name, check=False).stdout.strip() == "true"

    def log(self) -> str:
        out = subprocess.run(["docker", "logs", self.name], capture_output=True)
        return (out.stdout + out.stderr).decode("latin-1")

    def why_down(self) -> str:
        code = docker("inspect", "-f", "{{.State.ExitCode}}", self.name, check=False).stdout.strip()
        signals = {"134": "SIGABRT", "136": "SIGFPE", "137": "SIGKILL", "139": "SIGSEGV"}
        return f"exit status {code}" + (f" ({signals[code]})" if code in signals else "")

    def restart(self) -> None:
        docker("start", self.name)

    def __exit__(self, *exc):
        docker("rm", "-f", self.name, check=False)


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


def open_game(args, qmconfig: str | None = "fixture", players: tuple[str, ...] = ()):
    """The game args asks for: --docker IMAGE, or --python."""
    if args.docker:
        return CGame(args.docker, qmconfig, players)
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

