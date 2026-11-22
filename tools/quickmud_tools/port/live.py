"""Running the Python game for the tools: PyGame runs it here, from a throwaway copy of area/.

A game starts fresh for each use, from the fixtures (tools/fixtures: qmconfig.rc, the player files) and a fixed
QUICKMUD_SEED. (Until cut-over, a CGame ran the C game beside it in a container; it's at the c-final tag.)
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
from ..sim.smoke import free_port

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


class PyGame:
    """The Python game, run as python -m quickmud from a throwaway root."""

    # The signal stop sends, as the game logs it ("Caught signal N"): Windows has no SIGTERM to send a console
    # program, so CTRL_BREAK arrives as SIGBREAK.
    STOP_SIGNAL = int(getattr(signal, "SIGBREAK", 21)) if os.name == "nt" else int(signal.SIGTERM)

    def __init__(self, qmconfig: str | None = "fixture", players: tuple[str, ...] = ("Shemp",),
                 args: tuple[str, ...] = (), area_updates_only: bool = False):
        self.qmconfig, self.players, self.args = qmconfig, players, args
        # QUICKMUD_UPDATES=area, as CGame's: every update runs in the Python game too now (#74, P4 PR 6)
        self.updates = {"QUICKMUD_UPDATES": "area"} if area_updates_only else {}

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp(prefix="quickmud-port-"))
        shutil.copytree(area_dir(), self.root / "area")
        for d in ("player", "gods", "notes", "log"):
            (self.root / d).mkdir()
        if self.qmconfig == "fixture":
            shutil.copy(fixtures() / "qmconfig.rc", self.root / "area" / "qmconfig.rc")
        for who in self.players:
            shutil.copy(fixtures() / "player" / who, self.root / "player" / who)
        self.port = free_port()
        self.start()
        return self

    def start(self) -> None:
        """Start the game, or start it again after stop: the same root and port, the log appended to."""
        env = dict(os.environ, QUICKMUD_SEED=SEED, PYTHONPATH=str(game_dir()), **self.updates)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.log = open(self.root / "log" / "python.log", "ab")
        argv = [sys.executable, "-m", "quickmud", "--port", str(self.port), "--root", str(self.root), *self.args]
        self.proc = subprocess.Popen(argv, env=env, stdout=self.log, stderr=subprocess.STDOUT, creationflags=flags,
                                     start_new_session=os.name != "nt")

    def session(self) -> Session:
        return Session(self.port)

    def game_log(self) -> str:
        if not self.log.closed:
            self.log.flush()
        return (self.root / "log" / "python.log").read_text(encoding="latin-1")

    def stop(self) -> None:
        """Ask the game to stop (SIGTERM, or CTRL_BREAK on Windows); kill the whole process tree if it won't."""
        if self.log.closed:
            return
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

    def __exit__(self, *exc):
        self.stop()
        shutil.rmtree(self.root, ignore_errors=True)
