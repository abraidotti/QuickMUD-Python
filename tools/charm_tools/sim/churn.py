"""charm_tools sim churn: bots create characters and quit as fast as the lobby allows (#112, decision 1).

    python -m charm_tools sim churn --python --quick              # preflight: 2 bots for 1 minute
    python -m charm_tools sim churn --docker charm:c --minutes 15
    python -m charm_tools sim churn --compare charm:c            # both, 15 minutes each, then compared

It looks for crashes that need a quit to land on something periodic, such as a tick (Xania's churn found a quit on
the same pulse as a tick reading freed memory). Each bot loops: connect, create a character (the classes in turn),
quit, and wait for the game to close the connection. The run stops when the time is up or the game goes down, and
with --fail-fast at a bot's first error. A heartbeat line prints every 30 seconds.

"Compared" means: neither game went down, and the Python game's [*****] lines are the C's, or fewer. The games
run at their own speeds, so the two runs can't match step for step.
Exit codes follow the Sim convention: 0 clean, 1 a finding, 2 couldn't run.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from .games import Down, bug_lines, open_game, run_wsl, wait_up
from .smoke import Fail, Session

CLASSES = ("mage", "cleric", "thief", "warrior")
WEAPONS = {"mage": "dagger", "cleric": "mace", "thief": "dagger", "warrior": "sword"}
PASSWORD = "churnpass1"


def new_and_quit(s: Session, name: str, cls: str) -> None:
    s.expect(r"By what name")
    s.send(name)
    s.expect(r"right, .*\(Y/N\)");   s.send("y")
    s.expect(r"password");           s.send(PASSWORD)
    s.expect(r"[Rr]etype password"); s.send(PASSWORD)
    s.expect(r"What is your race");  s.send("human")
    s.expect(r"What is your sex");   s.send("f")
    s.expect(r"Select a class");     s.send(cls)
    s.expect(r"Which alignment");    s.send("n")
    s.expect(r"Customize \(Y/N\)");  s.send("n")
    s.expect(r"Your choice\?");      s.send(WEAPONS[cls])
    s.expect(r"continue");           s.send("")
    s.expect(r"<\d+hp")
    s.send("quit")
    s.expect_closed()


class Bot(threading.Thread):
    def __init__(self, n: int, port: int, args, stop: threading.Event, errors: list):
        super().__init__(daemon=True)
        self.n, self.port, self.args, self.stop, self.errors = n, port, args, stop, errors
        self.quits = 0

    def name(self, k: int) -> str:
        """Churn, then the bot's letter, then k in base 26: letters only, so check_parse_name takes it."""
        letters = "abcdefghijklmnopqrstuvwxyz"
        tail = ""
        for _ in range(4):
            k, r = divmod(k, 26)
            tail = letters[r] + tail
        return "Churn" + letters[self.n % 26] + tail

    def run(self) -> None:
        k = 0
        while not self.stop.is_set():
            try:
                s = Session("127.0.0.1", self.port, self.args.timeout)
            except OSError as e:
                self.errors.append(f"bot {self.n}: can't connect: {e}")
                return
            try:
                new_and_quit(s, self.name(k), CLASSES[(self.n + k) % len(CLASSES)])
                self.quits += 1
            except (Fail, OSError) as e:
                self.errors.append(f"bot {self.n}, {self.name(k)}: {str(e).splitlines()[0][:160]}")
                if self.args.fail_fast:
                    self.stop.set()
            finally:
                s.close()
            k += 1


def run_game(args, image) -> dict:
    args.docker = image
    seconds = 60.0 if args.quick else args.minutes * 60
    count = 2 if args.quick else args.bots
    with open_game(args) as game:
        wait_up(game)
        print(f"{game.kind} game on 127.0.0.1:{game.port}: {count} bots for {seconds:.0f}s", flush=True)
        stop, errors = threading.Event(), []
        bots = [Bot(n, game.port, args, stop, errors) for n in range(count)]
        for b in bots:
            b.start()
        start = time.monotonic()
        next_beat = start + 30
        down = None
        while time.monotonic() - start < seconds and not stop.is_set():
            time.sleep(0.5)
            if not game.alive():
                down = game.why_down()
                stop.set()
            if time.monotonic() >= next_beat:
                print(f"  {time.monotonic() - start:.0f}s: {sum(b.quits for b in bots)} quits, {len(errors)} errors",
                      flush=True)
                next_beat += 30
        stop.set()
        for b in bots:
            b.join(timeout=args.timeout * 12 + 5)
        if down is None and not game.alive():
            down = game.why_down()
        log = game.log()
        rec = {"game": game.kind, "quits": sum(b.quits for b in bots), "seconds": time.monotonic() - start,
               "errors": errors, "down": down, "bugs": bug_lines(log), "tail": log.splitlines()[-15:]}
    print(f"  {rec['game']}: {rec['quits']} quits in {rec['seconds']:.0f}s, {len(errors)} errors"
          + (f", DOWN ({down})" if down else ""), flush=True)
    return rec


def report(rec) -> int:
    findings = 0
    if rec["down"]:
        findings += 1
        print(f"FINDING {rec['game']}: the game went down after {rec['quits']} quits: {rec['down']}")
        for line in rec["tail"][-8:]:
            print(f"      {line}")
    for e in rec["errors"][:5]:
        print(f"  error: {e}")
    if rec["errors"]:
        findings += 1
        print(f"FINDING {rec['game']}: {len(rec['errors'])} bot error(s)")
    print(f"{'PASS' if not findings else 'FAIL'} {rec['game']}: {rec['quits']} quits, {len(rec['bugs'])} bug line(s)")
    return 1 if findings else 0


def compare(c, py) -> int:
    """The Python game's bug lines must be the C's, or fewer: a line only Python logs is a difference."""
    c_bugs = set(c["bugs"])
    extra = sorted(set(py["bugs"]) - c_bugs)
    for b in extra:
        print(f"DIFF only the Python game logged: {b}")
    for b in sorted(c_bugs - set(py["bugs"])):
        print(f"  only the C game logged: {b}")
    print(f"{'SAME' if not extra else 'DIFFERENT'}: C {c['quits']} quits, Python {py['quits']} quits; "
          f"{len(extra)} bug line(s) only on Python")
    return 1 if extra else 0


def main(argv=None, prog=None) -> int:
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--docker", metavar="IMAGE", help="the C game, in a throwaway container from IMAGE")
    where.add_argument("--python", action="store_true", help="the Python game, from a throwaway copy")
    where.add_argument("--compare", metavar="IMAGE", help="the C game from IMAGE, then the Python game; compare them")
    where.add_argument("--wsl", nargs="?", const="", metavar="DISTRO", help="from Windows: --python inside WSL")
    ap.add_argument("--bots", type=int, default=6, help="how many bots (default 6)")
    ap.add_argument("--minutes", type=float, default=15.0, help="how long on each game (default 15)")
    ap.add_argument("--quick", action="store_true", help="preflight: 2 bots for 1 minute")
    ap.add_argument("--fail-fast", action="store_true", help="stop at a bot's first error")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for each prompt")
    args = ap.parse_args(argv)
    if args.wsl is not None:
        return run_wsl("churn", [a for a in (argv or sys.argv[1:]) if not a.startswith("--wsl")
                                 and a != args.wsl], args.wsl)
    try:
        if args.compare:
            c, py = run_game(args, args.compare), run_game(args, None)
            return max(report(c), report(py), compare(c, py))
        return report(run_game(args, args.docker))
    except Down as e:
        print(f"SKIP {e}")
        return 2
    except FileNotFoundError:
        print("SKIP docker isn't installed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
