"""charm_tools sim bots: connected bots playing while the game measures its pulses (#25 decision 7; #32 decision 5).

    python -m charm_tools sim bots --python --quick              # preflight: 1 bot for 20 seconds
    python -m charm_tools sim bots --python --count 10 --minutes 5

The Python game runs from a throwaway copy with --pulse-stats, the fixtures and CHARM_SEED. Each bot creates a
character, then sends one command every 2 seconds, starting at a different moment: look, score, and a step along a
loop from the mud school down to the temple and through Midgaard's streets and back. Each command waits for the
prompt; one that doesn't come within --timeout stops the run (fail fast). A heartbeat line prints every 30 seconds.

When the time is up the game is stopped, and its log's "Pulse work over the run" line gives the median, 95th
percentile and maximum work per pulse (the sleep not counted). The go/no-go's pass mark is the 95th percentile
under 25 ms, a tenth of the 250 ms pulse. Only area_update runs in the Python game so far (#28): the cost of the
other updates is unknown, not zero.

Exit codes follow the Sim convention: 0 passed, 1 failed (a bot, or the pass mark), 2 couldn't run.
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time

from .smoke import Fail, Session, connect, new_character

ROUTE = ["d", "s", "s", "w", "e", "n", "n", "u"]  # mud school, temple, square, market, main street, and back
PROMPT = r"<\d+hp \d+m \d+mv>"
PASS_MS = 25.0
RUN_LINE = re.compile(r"Pulse work over the run: median ([\d.]+) ms, p95 ([\d.]+) ms, max ([\d.]+) ms, "
                      r"mean ([\d.]+) ms over (\d+) pulses")


class Bot(threading.Thread):
    def __init__(self, n: int, port: int, args, stop: threading.Event, failures: list):
        super().__init__(daemon=True)
        self.n, self.port, self.args, self.stop, self.failures = n, port, args, stop, failures
        self.name = "Bot" + "abcdefghijklmnopqrstuvwxyz"[n // 26] + "abcdefghijklmnopqrstuvwxyz"[n % 26]
        self.commands = 0

    def run(self) -> None:
        try:
            s = connect("127.0.0.1", self.port, self.args.timeout, 30.0)
            new_character(s, self.name, "botpass1")  # (its expect empties the buffer, prompt and all)
            # Start at different moments, so the bots don't all send in the same pulse.
            if self.stop.wait(self.args.every * self.n / max(1, self.args.count)):
                return
            step = 0
            while not self.stop.is_set():
                kind = step % 3
                line = "look" if kind == 0 else "score" if kind == 1 else ROUTE[(step // 3) % len(ROUTE)]
                s.send(line)
                s.expect(PROMPT, timeout=self.args.timeout)
                self.commands += 1
                step += 1
                self.stop.wait(self.args.every)
            s.send("quit")
        except (Fail, OSError) as e:
            self.failures.append(f"{self.name}: {e}")
            self.stop.set()


def run(args) -> int:
    from ..port.live import PyGame

    seconds = 20.0 if args.quick else args.minutes * 60
    count = 1 if args.quick else args.count
    args.count = count
    game = PyGame("fixture", (), ("--pulse-stats",))
    with game:
        print(f"python game on 127.0.0.1:{game.port}: {count} bot(s) for {seconds:.0f}s", flush=True)
        stop, failures = threading.Event(), []
        bots = [Bot(n, game.port, args, stop, failures) for n in range(count)]
        for b in bots:
            b.start()
        start = time.monotonic()
        next_beat = start + 30
        while time.monotonic() - start < seconds and not stop.is_set():
            time.sleep(0.5)
            if time.monotonic() >= next_beat:
                print(f"  {time.monotonic() - start:.0f}s: {sum(b.commands for b in bots)} commands, "
                      f"{sum(b.is_alive() for b in bots)} bots running", flush=True)
                next_beat += 30
            if game.proc.poll() is not None:
                failures.append(f"the game stopped (exit status {game.proc.returncode})")
                stop.set()
        stop.set()
        for b in bots:
            b.join(timeout=args.timeout + 5)
        game.stop()
        log = game.game_log()
    commands = sum(b.commands for b in bots)
    if failures:
        print("FAIL " + "; ".join(failures[:3]))
        print("---- game log (tail) ----")
        print("\n".join(log.splitlines()[-30:]))
        return 1
    m = RUN_LINE.search(log)
    if m is None:
        print("SKIP no 'Pulse work over the run' line in the game log")
        return 2
    median, p95, top, mean, pulses = (float(x) for x in m.groups())
    print(f"{count} bot(s), {commands} commands, {int(pulses)} pulses: median {median:.2f} ms, "
          f"p95 {p95:.2f} ms, max {top:.2f} ms, mean {mean:.2f} ms")
    for line in log.splitlines():
        if "Pulse work:" in line:
            print("  " + line.split(":: ", 1)[-1])
    ok = p95 < PASS_MS
    print(f"{'PASS' if ok else 'FAIL'} the 95th percentile is {'under' if ok else 'not under'} {PASS_MS:.0f} ms")
    return 0 if ok else 1


def main(argv=None, prog=None) -> int:
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    ap.add_argument("--python", action="store_true", required=True, help="run against the Python game")
    ap.add_argument("--count", type=int, default=10, help="how many bots (default 10)")
    ap.add_argument("--minutes", type=float, default=5.0, help="how long to run (default 5)")
    ap.add_argument("--quick", action="store_true", help="preflight: 1 bot for 20 seconds")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between a bot's commands (default 2)")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for a prompt")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
