"""string.c: OLC's string helpers. This PR has the three the area editor's builder list uses; the string editor
(string_append, string_add, format_string and the line functions) comes with the room editor, the first to use it.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/string.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import CWouldCrash
from charm.core.strings import upper
from charm.data import constants as C


def _fits(s: str, what: str) -> str:
    if len(s) >= C.MAX_STRING_LENGTH:
        raise CWouldCrash(f"string.c {what}: {len(s)} characters overflow its {C.MAX_STRING_LENGTH}-byte buffer")
    return s


# C: string.c string_replace
def string_replace(orig: str, old: str, new: str) -> str:
    """orig with its first old (a plain substring, as strstr finds it) replaced by new."""
    _fits(orig, "string_replace")
    i = orig.find(old)
    if i < 0:
        return orig
    return _fits(orig[:i] + new + orig[i + len(old):], "string_replace")


# C: string.c string_unpad
def string_unpad(argument: str) -> str:
    """Without leading and trailing spaces (only ' ', not other blanks)."""
    return _fits(argument.lstrip(" "), "string_unpad").rstrip(" ")


# C: string.c string_proper
def string_proper(argument: str) -> str:
    """Each word's first letter upper-cased (words split on ' ' only)."""
    out, start = [], True
    for c in argument:
        if c == " ":
            start = True
            out.append(c)
        else:
            out.append(upper(c) if start else c)
            start = False
    return "".join(out)
