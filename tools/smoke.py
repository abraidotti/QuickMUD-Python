"""Smoke test for Charm: create a character, lag, save, quit, log back in, clean shutdown, copyover.

Stdlib only. Exit codes follow the Sim convention: 0 passed, 1 a step failed, 2 couldn't run.
This is the refactor plan's R0 smoke test; it moves into the charm_tools package in tools-port T0.

    python tools/smoke.py --docker charm      # throwaway container from an image (recommended)
    python tools/smoke.py --port 4100         # a game that's already running (mortal steps only)

--docker creates a container on a free port, copies the fixtures in before boot (the immortal
tools/fixtures/player/Smokegod and tools/fixtures/qmconfig.rc, which turns the ANSI question off), runs every step
and always removes the container. The clean-shutdown steps (docker stop, then start) need --docker. Against a
running game, copyover runs only if you pass --immortal NAME:PASSWORD for a level-60 character. Either way the test creates a player file, so
don't point it at your real player/.
"""

import argparse
import io
import re
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

IAC = 255
ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
IMMORTAL = ("Smokegod", "smoke123")  # tools/fixtures/player/Smokegod, level 60


class Fail(Exception):
    pass


class Session:
    def __init__(self, host, port, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.timeout = timeout
        self.buf = b""
        self.transcript = []
        self.ansi_question = False  # set by connect(): did the game ask "Do you want ANSI?"

    def _recv(self):
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return False
        if not data:
            raise Fail("connection closed by the game")
        self.buf += data
        return True

    def _clean(self, data):
        out = bytearray()
        i = 0
        while i < len(data):
            if data[i] == IAC and i + 1 < len(data):
                i += 3 if data[i + 1] in (251, 252, 253, 254) else 2  # WILL/WONT/DO/DONT take an option byte
                continue
            out.append(data[i])
            i += 1
        return ANSI.sub(b"", bytes(out)).decode("latin-1")

    def expect(self, pattern, timeout=None):
        """Wait until the cleaned output matches pattern; consume up to the end of the match."""
        deadline = time.monotonic() + (timeout or self.timeout)
        rx = re.compile(pattern)
        while True:
            text = self._clean(self.buf)
            m = rx.search(text)
            if m:
                self.transcript.append(text)
                self.buf = b""
                return text
            if time.monotonic() > deadline:
                self.transcript.append(text)
                raise Fail(f"timed out waiting for {pattern!r}; last output:\n{text[-400:]}")
            self._recv()

    def send(self, line):
        self.sock.sendall(line.encode("latin-1") + b"\n")

    def expect_closed(self, timeout=None, pattern=None):
        """Wait for the game to close the connection; optionally require pattern in what it sent first."""
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            try:
                self._recv()
            except Fail:
                text = self._clean(self.buf)
                self.transcript.append(text)
                if pattern and not re.search(pattern, text):
                    raise Fail(f"connection closed without {pattern!r}; last output:\n{text[-400:]}")
                return
        raise Fail("game didn't close the connection")

    def close(self):
        self.sock.close()


def connect(host, port, timeout, wait):
    deadline = time.monotonic() + wait
    while True:
        try:
            s = Session(host, port, timeout)
            # The game is up only once it greets us: the ANSI question, or the name prompt if qmconfig turns it off.
            s.ansi_question = "ANSI" in s.expect(r"ANSI\? \(Y/n\)|By what name")
            return s
        except (OSError, Fail) as e:
            if time.monotonic() > deadline:
                raise ConnectionError(f"can't connect to {host}:{port}: {e}")
            time.sleep(1)


def send_name(s, name):
    if s.ansi_question:
        s.send("n")
        s.expect(r"By what name")
    s.send(name)


def new_character(s, name, pw):
    send_name(s, name)
    s.expect(r"right, .*\(Y/N\)");        s.send("y")
    s.expect(r"password");                s.send(pw)
    s.expect(r"[Rr]etype password");      s.send(pw)
    s.expect(r"What is your race");       s.send("human")
    s.expect(r"What is your sex");        s.send("m")
    s.expect(r"Select a class");          s.send("mage")
    s.expect(r"Which alignment");         s.send("n")
    s.expect(r"Customize \(Y/N\)");       s.send("n")
    s.expect(r"Your choice\?");           s.send("dagger")
    s.expect(r"continue");                s.send("")
    s.expect(r"Welcome to")


def old_character(s, name, pw):
    send_name(s, name)
    s.expect(r"Password:");               s.send(pw)
    # Immortals see the imotd, then the motd: one [Hit Return to continue] each.
    for _ in range(3):
        text = s.expect(r"continue|Welcome to")
        if "Welcome to" in text:
            return
        s.send("")
    raise Fail("never got past the MOTD")


def half_created(s):
    """Stop a new character at the race prompt: logged in far enough to have a char, not playing yet."""
    send_name(s, "Halfway")
    s.expect(r"right, .*\(Y/N\)");        s.send("y")
    s.expect(r"password");                s.send("halfway1")
    s.expect(r"[Rr]etype password");      s.send("halfway1")
    s.expect(r"What is your race")


def lag_shows_on_prompt(s):
    """save adds WAIT_STATE(4 * PULSE_VIOLENCE): %W should read 48 pulses, then 0 once the lag has passed."""
    s.send("prompt <smoke %W>")
    s.expect(r"<smoke 0>")
    s.send("save")
    text = s.expect(r"<smoke (\d+)>")
    lag = int(re.search(r"<smoke (\d+)>", text).group(1))
    if lag <= 0:
        raise Fail(f"%W read {lag} right after save; expected lag")
    t0 = time.monotonic()
    s.send("")  # queued behind the lag; its prompt prints when the lag is over
    s.expect(r"<smoke 0>", timeout=lag / 4 + 5)
    return lag, time.monotonic() - t0


def run_steps(args, port, immortal, restart=None):
    steps = []
    sessions = []

    def step(label, fn):
        t0 = time.monotonic()
        fn()
        steps.append(label)
        print(f"  ok  {label} ({time.monotonic() - t0:.1f}s)", flush=True)

    def open_session():
        s = connect(args.host, port, args.timeout, args.wait)
        sessions.append(s)
        return s

    try:
        try:
            s = open_session()
        except ConnectionError as e:
            print(f"SKIP {e}")
            return 2
        name, pw = args.name, args.password
        step("create character", lambda: new_character(s, name, pw))
        lag = {}
        step("%W shows save's lag, then 0", lambda: lag.update(zip(("pulses", "secs"), lag_shows_on_prompt(s))))
        print(f"      save lag: {lag['pulses']} pulses, cleared after {lag['secs']:.1f}s")
        step("quit", lambda: (s.send("quit"), s.expect_closed()))
        s = open_session()
        step("log back in", lambda: old_character(s, name, pw))
        step("score shows the character", lambda: (s.send("score"), s.expect(rf"You are {name}")))

        if restart:
            # A change that isn't saved by hand: the new prompt. SIGTERM should save it.
            step("change something without saving", lambda: (s.send("prompt <sigterm %W>"), s.expect(r"<sigterm 0>")))
            pending = open_session()
            step("a second connection stops mid-creation", lambda: half_created(pending))
            status = {}
            step("docker stop: the player is told and disconnected",
                 lambda: (status.update(zip(("code", "log"), restart.stop())),
                          s.expect_closed(pattern=r"The game is shutting down")))
            step("the game shuts itself down and exits 0",
                 lambda: (_check(status["code"] == 0, f"exit status {status['code']}"),
                          _check("Caught signal 15" in status["log"] and "Normal termination" in status["log"],
                                 "game log has no 'Caught signal 15' / 'Normal termination': it was killed")))
            restart.start()
            fresh = open_session()
            # Shutdown used to save the half-created character, taking the name (abraidotti/charm#4).
            step("the half-created name is still free",
                 lambda: (send_name(fresh, "Halfway"), fresh.expect(r"right, .*\(Y/N\)")))
            fresh.close()
            s = open_session()
            step("log back in after restart", lambda: old_character(s, name, pw))
            step("the unsaved change survived", lambda: (s.send("look"), s.expect(r"<sigterm 0>")))
        step("quit again", lambda: (s.send("quit"), s.expect_closed()))

        if immortal:
            iname, ipw = immortal
            god = open_session()
            step(f"immortal {iname} logs in", lambda: old_character(god, iname, ipw))
            half = open_session()
            step("second connection stops mid-creation", lambda: half_created(half))
            step("copyover", lambda: (god.send("copyover"), god.expect(rf"COPYOVER by {iname}")))
            step("half-created connection is dropped",
                 lambda: half.expect_closed(args.timeout, r"Sorry, we are rebooting"))
            step("immortal is restored", lambda: god.expect(r"Copyover recovery complete", args.timeout + 20))
            step("immortal can still play", lambda: (god.send("score"), god.expect(rf"You are {iname}")))
            late = open_session()
            step("new connections are accepted after copyover", lambda: None)
            late.close()
            step("immortal quits", lambda: (god.send("quit"), god.expect_closed()))
    except Fail as e:
        print(f"FAIL after {len(steps)} step(s): {e}")
        if args.verbose:
            for s in sessions:
                print("---- session transcript ----")
                print("".join(s.transcript)[-3000:])
        return 1
    except ConnectionError as e:
        print(f"FAIL after {len(steps)} step(s): {e}")
        return 1
    finally:
        for s in sessions:
            s.close()
    print(f"PASS {len(steps)} steps")
    return 0


def _check(ok, why):
    if not ok:
        raise Fail(why)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def docker(*argv, check=True):
    return subprocess.run(["docker", *argv], capture_output=True, text=True, check=check)


def run_docker(args):
    port = free_port()
    container = f"charm-smoke-{port}"
    try:
        docker("create", "--init", "--name", container, "-p", f"127.0.0.1:{port}:4000", args.docker)
    except FileNotFoundError:
        print("SKIP docker isn't installed")
        return 2
    except subprocess.CalledProcessError as e:
        print(f"SKIP can't create a container from {args.docker}: {e.stderr.strip()}")
        return 2
    class Restart:
        def stop(self):
            """docker stop; returns the exit status and the newest game log (to check the game itself shut down)."""
            docker("stop", container)
            code = int(docker("inspect", "-f", "{{.State.ExitCode}}", container).stdout.strip())
            # The log dir is in the stopped container's filesystem: docker cp streams it out as a tar.
            out = subprocess.run(["docker", "cp", f"{container}:/opt/charm/log/.", "-"], capture_output=True)
            logs = {}
            with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
                for m in tar.getmembers():
                    if m.isfile() and m.name.endswith(".log"):
                        logs[m.name] = tar.extractfile(m).read().decode("latin-1")
            return code, logs[max(logs)] if logs else ""

        def start(self):
            docker("start", container)

    try:
        docker("cp", str(FIXTURES / "player" / IMMORTAL[0]), f"{container}:/opt/charm/player/{IMMORTAL[0]}")
        docker("cp", str(FIXTURES / "qmconfig.rc"), f"{container}:/opt/charm/area/qmconfig.rc")
        docker("start", container)
        print(f"container {container} on 127.0.0.1:{port}", flush=True)
        code = run_steps(args, port, IMMORTAL, Restart())
        if code != 0 or args.verbose:
            log = docker("exec", container, "sh", "-c", "cat /opt/charm/log/*.log", check=False).stdout
            print("---- game log (tail) ----")
            print("\n".join(log.splitlines()[-30:]))
        return code
    finally:
        docker("rm", "-f", container, check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--docker", metavar="IMAGE", help="run against a throwaway container from IMAGE")
    where.add_argument("--port", type=int, help="run against a game already listening on this port")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--name", default="Smokey")
    ap.add_argument("--password", default="smoke123")
    ap.add_argument("--immortal", metavar="NAME:PASSWORD", help="with --port: a level-60 character for copyover")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds per step")
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the game to accept connections")
    ap.add_argument("-v", "--verbose", action="store_true", help="print transcripts and the game log")
    args = ap.parse_args()

    if args.docker:
        return run_docker(args)
    immortal = tuple(args.immortal.split(":", 1)) if args.immortal else None
    return run_steps(args, args.port, immortal)


if __name__ == "__main__":
    sys.exit(main())
