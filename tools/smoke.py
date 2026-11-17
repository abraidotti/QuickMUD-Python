"""Smoke test for a running Charm: create a character, save, quit, log back in.

Stdlib only. Exit codes follow the Sim convention: 0 passed, 1 a step failed, 2 couldn't run (no connection).
This is the refactor plan's R0 smoke test; it moves into the charm_tools package in tools-port T0.

    python tools/smoke.py --port 4000 [--name Smokey] [--wait 30]

Run it against a throwaway container, not the compose service: it creates a player file.
"""

import argparse
import re
import socket
import sys
import time

IAC = 255
ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


class Fail(Exception):
    pass


class Session:
    def __init__(self, host, port, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.timeout = timeout
        self.buf = b""
        self.transcript = []

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
        """Wait until the cleaned output matches pattern; consume up to the match."""
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

    def expect_closed(self, timeout=None):
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            try:
                self._recv()
            except Fail:
                return
        raise Fail("game didn't close the connection after quit")

    def close(self):
        self.sock.close()


def connect(args):
    deadline = time.monotonic() + args.wait
    while True:
        try:
            return Session(args.host, args.port, args.timeout)
        except OSError as e:
            if time.monotonic() > deadline:
                raise ConnectionError(f"can't connect to {args.host}:{args.port}: {e}")
            time.sleep(1)


def new_character(s, name, pw):
    s.expect(r"ANSI\? \(Y/n\)");          s.send("n")
    s.expect(r"[Nn]ame");                 s.send(name)
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
    s.expect(r"ANSI\? \(Y/n\)");          s.send("n")
    s.expect(r"[Nn]ame");                 s.send(name)
    s.expect(r"Password:");               s.send(pw)
    s.expect(r"continue");                s.send("")
    s.expect(r"Welcome to")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4000)
    ap.add_argument("--name", default="Smokey")
    ap.add_argument("--password", default="smoke123")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds per step")
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the game to accept connections")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the transcript on failure")
    args = ap.parse_args()

    steps = []

    def step(label, fn):
        t0 = time.monotonic()
        fn()
        steps.append(label)
        print(f"  ok  {label} ({time.monotonic() - t0:.1f}s)")

    s = None
    try:
        s = connect(args)
    except ConnectionError as e:
        print(f"SKIP {e}")
        return 2
    try:
        step("create character", lambda: new_character(s, args.name, args.password))
        step("save", lambda: (s.send("save"), s.expect(r"Saving")))
        # do_save adds WAIT_STATE(4 * PULSE_VIOLENCE) = 12s of lag, so quit waits behind it. The prompt can't show
        # lag yet (refactor R1 adds a wait-state token), so allow for it here.
        step("quit (after save's 12s lag)", lambda: (s.send("quit"), s.expect_closed(args.timeout + 12)))
        s.close()
        s = connect(args)
        step("log back in", lambda: old_character(s, args.name, args.password))
        step("score shows the character", lambda: (s.send("score"), s.expect(rf"You are {args.name}")))
        step("quit again", lambda: (s.send("quit"), s.expect_closed()))
    except Fail as e:
        print(f"FAIL after {len(steps)} step(s): {e}")
        if args.verbose and s:
            print("".join(s.transcript)[-3000:])
        return 1
    finally:
        if s:
            s.close()
    print(f"PASS {len(steps)} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
