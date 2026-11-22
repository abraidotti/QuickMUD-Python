"""Tests for the Python game. Run from game/: python -m unittest discover -s tests

Every test runs under quickmud.testing.watchdog: one that hangs stops the run with every thread's traceback.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

from quickmud.testing import watchdog

watchdog.install()
