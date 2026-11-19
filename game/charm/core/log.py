"""The game's log: log_string, bug and log_f, and ctime. Every line goes to stderr as "<ctime> :: <text>", as in
the C.

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

clock = time.time  # clock: what a log line's timestamp shows, until the game sets it to its current_time
# The time zone ctime formats in. The C uses the host's; the scenario harness sets this to the oracle's (UTC).
localtime = time.localtime  # clock: converts a time it's given, and reads no clock
to_stderr = True
_sinks: list = []


# C: db.c log_string
def log_string(text: str) -> None:
    for sink in _sinks:
        sink(text)
    if to_stderr:
        print(f"{ctime(clock())[:-1]} :: {text}", file=sys.stderr)


# C: (libc) ctime
def ctime(t: float) -> str:
    """The C library's ctime: "Wed Jun 30 21:49:08 1993\\n", in localtime's zone."""
    return time.asctime(localtime(t)) + "\n"  # clock: formats the time it's given


# C: db.c bug [partial]
def bug(fmt: str, param: object = 0) -> None:
    """``bug(str, param)``: the format takes at most one argument, as in the C. [partial]: the "[*****] FILE: x
    LINE: n" line bug() adds while an area file is open is the area loader's (areafile Diagnostic)."""
    try:
        text = fmt % param if "%" in fmt else fmt  # format: sprintf
    except (TypeError, ValueError):  # bug(word, 0) with a word from a file: sprintf would read garbage, not stop
        text = fmt
    log_string("[*****] BUG: " + text)


# C: comm.c log_f
def log_f(fmt: str, *args: object) -> None:
    log_string(fmt % args if args else fmt)  # format: sprintf


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
