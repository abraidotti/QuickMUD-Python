"""python -m quickmud --port N --root DIR: run the Python game, as the C game's main does (#25, decision 5).

DIR holds area/ (and later player/), like the C's run directory; the C runs from area/ and reads ../area/qmconfig.rc.
QUICKMUD_SEED seeds the random numbers, as in the C. --pulse-stats logs each pulse's work every 60 seconds (#28).

While the port is partial, NotPorted stops the game: it logs the branch, prints the traceback and exits 1, as the C
does with exit(1) (#28, decision 3).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

from quickmud import __version__


# C: comm.c main
def main(argv: list[str] | None = None) -> int:
    """Boot and run the game. After a copyover the old process runs this again with "copyover <control>" as
    the C's main gets them: the listening socket is inherited, not opened, and copyover_recover picks the players up."""
    import socket

    from quickmud.commands.copyover import copyover_recover
    from quickmud.core import log
    from quickmud.core.errors import CWouldCrash, NotPorted
    from quickmud.entities.boot import boot_db
    from quickmud.net.config import qmconfig_read
    from quickmud.net.server import PulseStats, game_loop, init_socket
    from quickmud.systems.update import NOT_RUNNING, updates_named

    ap = argparse.ArgumentParser(prog="python -m quickmud", description=f"QuickMUD-Python {__version__}, the Python port")
    ap.add_argument("--port", default="4000", help="the port to listen on (default 4000)")
    ap.add_argument("--root", default=".", help="the directory that holds area/ (default: here)")
    ap.add_argument("--pulse-stats", action="store_true", help="log each pulse's work every 60 seconds")
    ap.add_argument("copyover", nargs="?", default="", help=argparse.SUPPRESS)  # "copyover", from do_copyover
    ap.add_argument("control", nargs="?", default="0", help=argparse.SUPPRESS)  # the listening socket's descriptor
    args = ap.parse_args(argv)
    copyover = args.copyover != ""  # "Are we recovering from a copyover?"

    if not args.port.isdigit():
        print(f"Usage: {ap.prog} [--port #]", file=sys.stderr)
        return 1
    port = int(args.port)
    if port <= 1024:
        print("Port number must be above 1024.", file=sys.stderr)
        return 1
    area = Path(args.root) / "area"

    now = int(time.time())  # clock: the boot time, as the C's main reads it before boot_db
    log.clock = lambda: now
    config = qmconfig_read(area / "qmconfig.rc")
    if copyover:
        control = socket.socket(fileno=int(args.control))
        control.setblocking(False)
    else:
        control = init_socket(port, config.ipaddress)
    try:
        game = boot_db(area, now)
        game.config = config
        game.port, game.control = port, control
        game.str_boot_time = log.ctime(now)
        log.clock = lambda: game.current_time
        named = os.environ.get("QUICKMUD_UPDATES")
        game.updates = updates_named(named)
        if named is not None:
            log.log_f("QUICKMUD_UPDATES=%s: only those updates run", named)
        if NOT_RUNNING:
            log.log_f("Not ported, not running: %s (#28).", ", ".join(NOT_RUNNING))
        log.log_f("QuickMUD-Python is ready to rock on port %d (%s).", port, config.ipaddress)
        if copyover:
            copyover_recover(game)
        game_loop(game, control, PulseStats() if args.pulse_stats else None)
    except (NotPorted, CWouldCrash) as e:
        log.log_string(f"[*****] {'NOT PORTED' if isinstance(e, NotPorted) else 'THE C WOULD CRASH'}: {e}")
        traceback.print_exc()
        return 1
    finally:
        control.close()
    log.log_string("Normal termination of game.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
