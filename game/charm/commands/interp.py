"""The interpreter's helpers. So far one_argument, which show_string and act() use; interpret comes in spike PR 5.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/interp.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

SPACE = " \t\n\v\f\r"  # isspace in the C locale


def _lower(c: str) -> str:
    return chr(ord(c) + 32) if "A" <= c <= "Z" else c


# C: interp.c one_argument
def one_argument(argument: str) -> tuple[str, str]:
    """(the rest, the first argument lower-cased). A quote (' or ") at the start groups words up to the matching
    quote."""
    i, n = 0, len(argument)
    while i < n and argument[i] in SPACE:
        i += 1
    end = " "
    if i < n and argument[i] in "'\"":
        end = argument[i]
        i += 1
    out = []
    while i < n:
        if argument[i] == end:
            i += 1
            break
        out.append(_lower(argument[i]))
        i += 1
    while i < n and argument[i] in SPACE:
        i += 1
    return argument[i:], "".join(out)
