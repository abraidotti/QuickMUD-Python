"""A watchdog for the test suites: a test that runs past its time limit stops the run, with every thread's
traceback, instead of hanging it.

install() wraps unittest.TestCase.run so each test arms faulthandler's timer (dump_traceback_later, exit=True) and
disarms it when it ends. The limit is LIMIT seconds; a long test says how long it may take with @allow(seconds),
and a test that loops over many cases can call arm() again for each, so the limit is per case. CHARM_TEST_TIMEOUT
sets the limit in seconds, and 0 turns the watchdog off (for a debugger).

A timeout ends the process at once (faulthandler's exit), so the run reports nothing more after the traceback:
the traceback is the report.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import faulthandler
import os
import unittest

LIMIT = 60  # seconds for one test (the slowest single case takes about 10)


def _limit() -> float:
    try:
        return float(os.environ.get("CHARM_TEST_TIMEOUT", LIMIT))
    except ValueError:
        return LIMIT


def arm(seconds: float | None = None) -> None:
    """Start (or restart) the timer: past `seconds` (the limit by default), dump every traceback and exit."""
    if _limit() <= 0:
        return
    faulthandler.dump_traceback_later(seconds if seconds is not None else _limit(), exit=True)


def disarm() -> None:
    faulthandler.cancel_dump_traceback_later()


def allow(seconds: float):
    """A test that may take longer than the limit: @allow(600)."""
    def mark(test):
        test.watchdog_seconds = seconds
        return test
    return mark


def install() -> None:
    """Wrap every TestCase's run in the watchdog (once)."""
    if getattr(unittest.TestCase.run, "watchdog", False):
        return
    real = unittest.TestCase.run

    def run(self, result=None):
        method = getattr(self, self._testMethodName, None)
        seconds = getattr(method, "watchdog_seconds", None)
        arm(max(seconds, _limit()) if seconds is not None else None)
        try:
            return real(self, result)
        finally:
            disarm()

    run.watchdog = True
    unittest.TestCase.run = run
