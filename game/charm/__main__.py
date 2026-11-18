"""python -m charm --port N --root DIR: run the Python game, as the C game's main does (#25, decision 5).

DIR holds area/ (and later player/), like the C's run directory; the C runs from area/ and reads ../area/qmconfig.rc.
CHARM_SEED seeds the random numbers, as in the C. --pulse-stats logs each pulse's work every 60 seconds (#28).

While the port is partial, NotPorted stops the game: it logs the branch, prints the traceback and exits 1, as the C
does with exit(1) (#28, decision 3).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from charm import __version__


# C: comm.c main [partial]
def main(argv: list[str] | None = None) -> int:
    """[partial]: copyover recovery isn't ported (it's not in the spike)."""
    from charm.core import log
    from charm.core.errors import CWouldCrash, NotPorted
    from charm.entities.boot import boot_db
    from charm.net.config import qmconfig_read
    from charm.net.server import PulseStats, game_loop, init_socket
    from charm.systems.update import NOT_RUNNING

    ap = argparse.ArgumentParser(prog="python -m charm", description=f"Charm {__version__}, the Python port")
    ap.add_argument("--port", default="4000", help="the port to listen on (default 4000)")
    ap.add_argument("--root", default=".", help="the directory that holds area/ (default: here)")
    ap.add_argument("--pulse-stats", action="store_true", help="log each pulse's work every 60 seconds")
    args = ap.parse_args(argv)

    if not args.port.isdigit():
        print(f"Usage: {ap.prog} [--port #]", file=sys.stderr)
        return 1
    port = int(args.port)
    if port <= 1024:
        print("Port number must be above 1024.", file=sys.stderr)
        return 1
    area = Path(args.root) / "area"

    now = int(time.time())
    log.clock = lambda: now
    config = qmconfig_read(area / "qmconfig.rc")
    control = init_socket(port, config.ipaddress)
    try:
        game = boot_db(area, now)
        game.config = config
        log.clock = lambda: game.current_time
        log.log_f("Not ported, not running: %s (#28).", ", ".join(NOT_RUNNING))
        log.log_f("ROM is ready to rock on port %d (%s).", port, config.ipaddress)
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
