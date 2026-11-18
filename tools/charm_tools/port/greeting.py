"""charm_tools port greeting: connect to the C game and the Python game, and compare the first bytes they send.

The live check of #28: real sockets and the real loop on both sides. It runs twice, with area/qmconfig.rc (the
"Do you want ANSI?" question) and with tools/fixtures/qmconfig.rc (no question: the greeting help). The C game runs
in a container from a runtime image; the Python game runs here, from a throwaway copy of area/, and is stopped the
way #25 decision 5 says: politely first, then the whole process tree.
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
CONFIGS = {"stock qmconfig.rc (the ANSI question)": None, "tools/fixtures/qmconfig.rc (no question)": "fixture"}


def read_first(port: int, wait: float = 30.0, idle: float = 1.5) -> bytes:
    """Connect (retrying while the game boots) and read until it has said nothing for `idle` seconds."""
    deadline = time.monotonic() + wait
    while True:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=idle)
            first = sock.recv(65536)
            if first:
                break
            sock.close()
        except OSError:
            pass
        if time.monotonic() > deadline:
            raise ConnectionError(f"nothing from 127.0.0.1:{port} in {wait:.0f}s")
        time.sleep(0.5)
    data = first
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    sock.close()
    return data


def c_greeting(image: str, qmconfig: Path | None) -> bytes:
    port = free_port()
    name = f"charm-greeting-{port}"
    docker("create", "--init", "--name", name, "-p", f"127.0.0.1:{port}:4000", "-e", f"CHARM_SEED={SEED}", image)
    try:
        if qmconfig is not None:
            docker("cp", str(qmconfig), f"{name}:/opt/charm/area/qmconfig.rc")
        docker("start", name)
        return read_first(port)
    finally:
        docker("rm", "-f", name, check=False)


def python_greeting(qmconfig: Path | None) -> bytes:
    root = Path(tempfile.mkdtemp(prefix="charm-greeting-"))
    proc = None
    try:
        shutil.copytree(area_dir(), root / "area")
        if qmconfig is not None:
            shutil.copy(qmconfig, root / "area" / "qmconfig.rc")
        port = free_port()
        env = dict(os.environ, CHARM_SEED=SEED, PYTHONPATH=str(game_dir()))
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        proc = subprocess.Popen([sys.executable, "-m", "charm", "--port", str(port), "--root", str(root)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags,
                                start_new_session=os.name != "nt")
        return read_first(port)
    finally:
        if proc is not None:
            stop(proc)
        shutil.rmtree(root, ignore_errors=True)


def stop(proc: subprocess.Popen) -> None:
    """Ask the game to stop as a signal would (SIGTERM; CTRL_BREAK on Windows), then kill the process tree."""
    try:
        proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        proc.wait(timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)


def run(image: str) -> int:
    fixture = find_root() / "tools" / "fixtures" / "qmconfig.rc"
    failed = 0
    for label, which in CONFIGS.items():
        qm = fixture if which == "fixture" else None
        try:
            c = c_greeting(image, qm)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"couldn't run the C game from {image}: {e}")
            return 2
        py = python_greeting(qm)
        same = c == py
        failed += not same
        print(f"{label}: C sent {len(c)} bytes, Python {len(py)}: {'SAME' if same else 'DIFFERENT'}")
        if not same:
            at = next((i for i, (a, b) in enumerate(zip(c, py)) if a != b), min(len(c), len(py)))
            print(f"    first difference at byte {at}:\n    C:      {c[max(0, at - 40):at + 60]!r}\n"
                  f"    Python: {py[max(0, at - 40):at + 60]!r}")
    return 1 if failed else 0
