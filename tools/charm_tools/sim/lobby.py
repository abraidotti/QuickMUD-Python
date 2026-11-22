"""charm_tools sim lobby: awkward replies at every login prompt, on one game or on both, compared (#112, decision 1).

    python -m charm_tools sim lobby --python --quick         # preflight: two prompts, two replies
    python -m charm_tools sim lobby --docker charm:c        # the C game
    python -m charm_tools sim lobby --compare charm:c       # both, then the differences

For each of nanny.c's prompts, walk the lobby to it, send one awkward reply, and record what the game answered,
whether it closed the connection, and whether it's still up and greeting. The replies are an empty line, a space,
a lone ~, !, a 300-character line and a non-ASCII letter. The C reads argument[0] as '\\0' on an empty line and
carries on. In Python the same index raises IndexError on an empty string, which is the divergence class this
looks for. A game that goes down is restarted before the next case.

Each case uses its own character name, the same on both games, so --compare can match the answers line for line.
Exit codes follow the Sim convention: 0 clean (and, with --compare, the same), 1 a finding, 2 couldn't run.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time

from .games import Down, answering, bug_lines, open_game, run_wsl, wait_up
from .smoke import Fail, Session

PASSWORD = "lobbypass1"
GOD = ("Smokegod", "smoke123")  # tools/fixtures/player/Smokegod, level 60

# The walks: (step, the prompt that starts it, the usual answer). A case stops at one step and sends its reply there.
NEW = [
    ("name", r"By what name", "{name}"),
    ("confirm_new", r"right, .*\(Y/N\)", "y"),
    ("new_password", r"Give me a password", PASSWORD),
    ("confirm_password", r"[Rr]etype password", PASSWORD),
    ("race", r"What is your race", "human"),
    ("sex", r"What is your sex", "m"),
    ("class", r"Select a class", "mage"),
    ("alignment", r"Which alignment", "n"),
    ("customize", r"Customize \(Y/N\)", "n"),
    ("weapon", r"Your choice\?", "dagger"),
    ("motd", r"continue", ""),
]
GROUPS = NEW[:8] + [("customize", r"Customize \(Y/N\)", "y"), ("gen_groups", r"Choice \(add,drop,list,help\)\?", "")]
OLD = [("name", r"By what name", GOD[0]), ("old_password", r"Password:", GOD[1]), ("imotd", r"continue", "")]
BREAK = OLD[:2] + [("break_connect", r"connect anyway \(Y/N\)\?", "n")]
ANSI = [("ansi", r"ANSI\? \(Y/n\)", "n")]

# (the case's label, the walk, the step it stops at)
TARGETS = ([(step, NEW, step) for step, _, _ in NEW]
           + [("gen_groups", GROUPS, "gen_groups"), ("old_password", OLD, "old_password"), ("imotd", OLD, "imotd"),
              ("break_connect", BREAK, "break_connect")])
# Each case's nanny state (net/nanny.py, nanny.c); a test checks every state the nanny handles has a case
STATES = {"ansi": "CON_ANSI", "name": "CON_GET_NAME", "old_password": "CON_GET_OLD_PASSWORD",
          "break_connect": "CON_BREAK_CONNECT", "confirm_new": "CON_CONFIRM_NEW_NAME",
          "new_password": "CON_GET_NEW_PASSWORD", "confirm_password": "CON_CONFIRM_NEW_PASSWORD",
          "race": "CON_GET_NEW_RACE", "sex": "CON_GET_NEW_SEX", "class": "CON_GET_NEW_CLASS",
          "alignment": "CON_GET_ALIGNMENT", "customize": "CON_DEFAULT_CHOICE", "weapon": "CON_PICK_WEAPON",
          "gen_groups": "CON_GEN_GROUPS", "imotd": "CON_READ_IMOTD", "motd": "CON_READ_MOTD"}
REPLIES = {"empty": "", "space": " ", "tilde": "~", "bang": "!", "long": "x" * 300, "latin1": "\xe9"}
QUICK = (["sex", "break_connect"], ["empty", "tilde"])


def drain(s: Session, quiet: float = 0.8, limit: float = 5.0) -> tuple[str, bool]:
    """Everything the game sends until it's been quiet for a moment: (the text, whether it closed)."""
    deadline = time.monotonic() + limit
    s.sock.settimeout(quiet)
    closed = False
    while time.monotonic() < deadline:
        try:
            data = s.sock.recv(4096)
        except socket.timeout:
            break
        except OSError:
            closed = True
            break
        if not data:
            closed = True
            break
        s.buf += data
    text = s._clean(s.buf)
    s.buf = b""
    return text, closed


def walk(s: Session, steps, stop: str, name: str, first: str) -> None:
    """Answer the walk's prompts until `stop`'s prompt has been seen. `first` is the greeting connect() consumed."""
    seen = first
    for step, prompt, answer in steps:
        if not re.search(prompt, seen):
            seen = s.expect(prompt)
        if step == stop:
            return
        s.send(answer.format(name=name))
        seen = ""


def play_god(s: Session) -> None:
    """Log the god all the way in. An earlier case may have left it link-dead, so it may reconnect instead."""
    s.expect(r"By what name")
    s.send(GOD[0])
    s.expect(r"Password:")
    s.send(GOD[1])
    for _ in range(4):
        text = s.expect(r"continue|Reconnecting|<\d+hp")
        if "continue" not in text:
            return
        s.send("")
    raise Fail("the god never got past the MOTD")


def names():
    """Lobbyaa, Lobbyab, ...: letters only, so check_parse_name takes them."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    n = 0
    while True:
        yield "Lobby" + letters[n // 26 % 26] + letters[n % 26]
        n += 1


def run_game(args, targets, replies, ansi: bool) -> list[dict]:
    """Every case on one game. Returns one record per case."""
    out = []
    qmconfig = None if ansi else "fixture"
    with open_game(args, qmconfig, (GOD[0],)) as game:
        wait_up(game)
        print(f"{game.kind} game on 127.0.0.1:{game.port}" + (" (stock qmconfig: the ANSI question)" if ansi else ""),
              flush=True)
        gen = names()
        cases = [(t, r) for t in targets for r in replies]
        for i, ((label, steps, stop), reply) in enumerate(cases):
            name = next(gen)
            rec = {"case": f"{label}/{reply}", "game": game.kind}
            first_playing = None
            s = None
            try:
                if stop == "break_connect":  # someone has to be playing as the god already
                    first_playing = Session("127.0.0.1", game.port, args.timeout)
                    play_god(first_playing)
                s = Session("127.0.0.1", game.port, args.timeout)
                greeting = s.expect(r"ANSI\? \(Y/n\)|By what name")
                walk(s, ANSI + steps if ansi and stop != "ansi" else steps, stop, name, greeting)
                s.send(REPLIES[reply])
                text, closed = drain(s)
                rec.update(reply=text, closed=closed)
            except (Fail, OSError) as e:
                rec.update(error=str(e).splitlines()[0][:200])
            finally:
                for c in (s, first_playing):
                    if c is not None:
                        c.close()
            rec["up"] = answering(game, args.timeout)
            if not rec["up"]:
                rec["why"] = game.why_down()
                rec["log"] = game.log().splitlines()[-15:]
                print(f"  DOWN {rec['case']}: {rec['why']}", flush=True)
                if args.fail_fast:
                    out.append(rec)
                    break
                game.restart()
                wait_up(game)
            elif "error" in rec:
                print(f"  ??  {rec['case']}: {rec['error']}", flush=True)
                if args.fail_fast:
                    out.append(rec)
                    break
            out.append(rec)
            if args.verbose:
                print(f"  {rec['case']}: closed={rec.get('closed')} {rec.get('reply', '')[-160:]!r}", flush=True)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(cases)} cases", flush=True)
        log = game.log()
    for rec in out:
        rec["bugs"] = None
    out.append({"case": "(log)", "game": game.kind, "bugs": bug_lines(log), "up": True})
    return out


def report(records) -> int:
    findings = [r for r in records if not r["up"] or "error" in r]
    for r in findings:
        print(f"FINDING {r['game']} {r['case']}: " + (f"went down, {r['why']}" if not r["up"] else r["error"]))
        for line in r.get("log", [])[-6:]:
            print(f"      {line}")
    bugs = next(r["bugs"] for r in records if r["case"] == "(log)")
    for b in bugs:
        print(f"  log: {b}")
    cases = sum(1 for r in records if r["case"] != "(log)")
    print(f"{'PASS' if not findings else 'FAIL'} {cases} cases, {len(findings)} finding(s), {len(bugs)} bug line(s)")
    return 1 if findings else 0


def compare(c, py) -> int:
    """The two games' records, case by case."""
    diffs = 0
    pyd = {r["case"]: r for r in py}
    for rc in c:
        rp = pyd.get(rc["case"])
        if rp is None:
            print(f"DIFF {rc['case']}: only the C game ran it")
            diffs += 1
            continue
        for key in ("up", "closed", "error", "reply", "bugs"):
            if rc.get(key) != rp.get(key):
                diffs += 1
                print(f"DIFF {rc['case']} {key}:\n   C:      {str(rc.get(key))[-300:]!r}\n   Python: "
                      f"{str(rp.get(key))[-300:]!r}")
                break
    print(f"{'SAME' if not diffs else 'DIFFERENT'}: {len(c)} records, {diffs} difference(s)")
    return 1 if diffs else 0


def main(argv=None, prog=None) -> int:
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--docker", metavar="IMAGE", help="the C game, in a throwaway container from IMAGE")
    where.add_argument("--python", action="store_true", help="the Python game, from a throwaway copy")
    where.add_argument("--compare", metavar="IMAGE", help="the C game from IMAGE, then the Python game; compare them")
    where.add_argument("--wsl", nargs="?", const="", metavar="DISTRO", help="from Windows: --python inside WSL")
    ap.add_argument("--quick", action="store_true", help="preflight: two prompts, two replies")
    ap.add_argument("--fail-fast", action="store_true", help="stop at the first finding")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for each prompt")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each case's answer")
    args = ap.parse_args(argv)
    if args.wsl is not None:
        return run_wsl("lobby", [a for a in (argv or sys.argv[1:]) if not a.startswith("--wsl")
                                 and a != args.wsl], args.wsl)
    labels, replies = QUICK if args.quick else ([t[0] for t in TARGETS], list(REPLIES))
    targets = [t for t in TARGETS if t[0] in labels]

    def one(docker_image):
        args.docker = docker_image
        recs = run_game(args, targets, replies, ansi=False)
        recs += [dict(r, case="ansi:" + r["case"]) for r in run_game(args, [("ansi", ANSI, "ansi")], replies, True)]
        return recs

    try:
        if args.compare:
            c, py = one(args.compare), one(None)
            code = max(report(c), report(py))
            return max(code, compare(c, py))
        return report(one(args.docker))
    except Down as e:
        print(f"SKIP {e}")
        return 2
    except FileNotFoundError:
        print("SKIP docker isn't installed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
