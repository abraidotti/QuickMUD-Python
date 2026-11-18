"""Running the C game and the Python game side by side, for port login and port players.

A game starts fresh for each use, from the same fixtures (tools/fixtures: qmconfig.rc, the player files) and the
same CHARM_SEED:
- CGame runs the C game in a container from a runtime image
- PyGame runs the Python game here, from a throwaway copy of area/
Sessions read until the game has been quiet for a moment, so each step's output is everything one line of input
produced. Stopping follows the Xania gotchas: SIGTERM (CTRL_BREAK on Windows) first, then the whole process tree.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..paths import area_dir, find_root, game_dir
from ..sim.smoke import docker, free_port

SEED = "20261117"
CLOSED = b"<closed>"


def fixtures() -> Path:
    return find_root() / "tools" / "fixtures"


class Session:
    def __init__(self, port: int, wait: float = 30.0, idle: float = 0.8):
        self.idle = idle
        deadline = time.monotonic() + wait
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=idle)
                self.first = self.read()
                # Docker's port proxy accepts before the game listens, then drops the connection: try again.
                if self.first and self.first != CLOSED:
                    return
                self.sock.close()
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise ConnectionError(f"no game on 127.0.0.1:{port} after {wait:.0f}s")
            time.sleep(0.5)

    def read(self, limit: float = 10.0) -> bytes:
        """Everything until the game says nothing for `idle` seconds (or closes: then CLOSED is added)."""
        data, deadline = b"", time.monotonic() + limit
        self.sock.settimeout(self.idle)
        while time.monotonic() < deadline:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                break
            except OSError:
                return data + CLOSED
            if not chunk:
                return data + CLOSED
            data += chunk
        return data

    def send(self, line: str) -> bytes:
        try:
            self.sock.sendall(line.encode("latin-1") + b"\n")
        except OSError:
            return CLOSED
        return self.read()

    def close(self) -> None:
        self.sock.close()


class CGame:
    """The C game in a container. Use as a context manager; player files can be copied in and out."""

    def __init__(self, image: str, qmconfig: str | None = "fixture", players: tuple[str, ...] = ("Shemp",)):
        self.image, self.qmconfig, self.players = image, qmconfig, players

    def __enter__(self):
        self.port = free_port()
        self.name = f"charm-port-{self.port}"
        docker("create", "--init", "--name", self.name, "-p", f"127.0.0.1:{self.port}:4000", "-e",
               f"CHARM_SEED={SEED}", self.image)
        if self.qmconfig == "fixture":
            docker("cp", str(fixtures() / "qmconfig.rc"), f"{self.name}:/opt/charm/area/qmconfig.rc")
        for who in self.players:
            docker("cp", str(fixtures() / "player" / who), f"{self.name}:/opt/charm/player/{who}")
        docker("start", self.name)
        return self

    def put_player(self, path: Path) -> None:
        docker("cp", str(path), f"{self.name}:/opt/charm/player/{path.name}")

    def player_file(self, name: str) -> str:
        return docker("exec", self.name, "cat", f"/opt/charm/player/{name}").stdout

    def session(self) -> Session:
        return Session(self.port)

    def __exit__(self, *exc):
        docker("rm", "-f", self.name, check=False)


class PyGame:
    """The Python game, run as python -m charm from a throwaway root."""

    def __init__(self, qmconfig: str | None = "fixture", players: tuple[str, ...] = ("Shemp",)):
        self.qmconfig, self.players = qmconfig, players

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp(prefix="charm-port-"))
        shutil.copytree(area_dir(), self.root / "area")
        for d in ("player", "gods", "notes", "log"):
            (self.root / d).mkdir()
        if self.qmconfig == "fixture":
            shutil.copy(fixtures() / "qmconfig.rc", self.root / "area" / "qmconfig.rc")
        for who in self.players:
            shutil.copy(fixtures() / "player" / who, self.root / "player" / who)
        self.port = free_port()
        env = dict(os.environ, CHARM_SEED=SEED, PYTHONPATH=str(game_dir()))
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.log = open(self.root / "log" / "python.log", "wb")
        self.proc = subprocess.Popen([sys.executable, "-m", "charm", "--port", str(self.port), "--root",
                                      str(self.root)], env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     creationflags=flags, start_new_session=os.name != "nt")
        return self

    def session(self) -> Session:
        return Session(self.port)

    def game_log(self) -> str:
        self.log.flush()
        return (self.root / "log" / "python.log").read_text(encoding="latin-1")

    def __exit__(self, *exc):
        try:
            if self.proc.poll() is None:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
            self.proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=10)
        self.log.close()
        shutil.rmtree(self.root, ignore_errors=True)
