"""python -m charm: there's no game to run yet (phase P0 of plans/python-port.md).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import sys

from charm import __version__


def main(argv=None):
    print(f"charm {__version__}: the Python port is at P0 (plans/python-port.md); nothing to run yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
