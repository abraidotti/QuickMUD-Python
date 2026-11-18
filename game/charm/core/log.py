"""The game's log: log_string, bug and log_f. Every line goes to stderr as "<ctime> :: <text>", as in the C.

Tests and tools can add a sink to collect the lines (``capture()``), and set the clock the timestamps read
(``clock``; the C prints current_time, the game's own clock).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import contextlib
import sys
import time

clock = time.time  # what the timestamp shows; the game sets it to its current_time
to_stderr = True
_sinks: list = []


# C: db.c log_string
def log_string(text: str) -> None:
    for sink in _sinks:
        sink(text)
    if to_stderr:
        print(f"{time.ctime(clock())} :: {text}", file=sys.stderr)


# C: db.c bug [partial]
def bug(fmt: str, param: object = 0) -> None:
    """``bug(str, param)``: the format takes at most one argument, as in the C. [partial]: the "[*****] FILE: x
    LINE: n" line bug() adds while an area file is open is the area loader's (areafile Diagnostic)."""
    log_string("[*****] BUG: " + (fmt % param if "%" in fmt else fmt))


# C: comm.c log_f
def log_f(fmt: str, *args: object) -> None:
    log_string(fmt % args if args else fmt)


@contextlib.contextmanager
def capture(quiet: bool = True):
    """Collect every log line (without timestamps) in a list while the block runs; quiet keeps stderr clear."""
    global to_stderr
    lines: list[str] = []
    saved = to_stderr
    _sinks.append(lines.append)
    to_stderr = not quiet and saved
    try:
        yield lines
    finally:
        _sinks.remove(lines.append)
        to_stderr = saved
