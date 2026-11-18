"""db.c's string helpers: comparisons that ignore case the way the C's LOWER does (ASCII only), and the smashers.

The C's str_cmp, str_prefix and str_suffix return TRUE when the strings *differ*. These return what the C's
callers test for, so ``if (!str_prefix (a, b))`` is ``if str_prefix(a, b)`` here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# Python's str.lower and str.upper change letters over 127 too, and some change length ("ß".upper() is "SS"). The
# C's LOWER and UPPER change a-z and A-Z only, so the game uses these (tests/test_guards.py checks it).


def lower(s: str) -> str:
    """LOWER on every character: A-Z only, as the C locale's tolower."""
    return s.translate(_LOWER)


def upper(s: str) -> str:
    """UPPER on every character: a-z only, as the C locale's toupper."""
    return s.translate(_UPPER)


# C: db.c str_cmp
def str_cmp(astr: str, bstr: str) -> bool:
    """``!str_cmp (astr, bstr)``: equal, ignoring case."""
    return lower(astr) == lower(bstr)


# C: db.c str_prefix
def str_prefix(astr: str, bstr: str) -> bool:
    """``!str_prefix (astr, bstr)``: astr is a prefix of bstr, ignoring case. An empty astr always is."""
    return lower(bstr).startswith(lower(astr))


# C: db.c str_suffix
def str_suffix(astr: str, bstr: str) -> bool:
    """``!str_suffix (astr, bstr)``: astr is a suffix of bstr, ignoring case."""
    return len(astr) <= len(bstr) and str_cmp(astr, bstr[len(bstr) - len(astr):])


# C: db.c smash_tilde
def smash_tilde(s: str) -> str:
    return s.replace("~", "-")


# C: db.c smash_dollar
def smash_dollar(s: str) -> str:
    return s.replace("$", "S")


def atoi(s: str) -> int:
    """The C library's atoi: leading whitespace, an optional sign, then digits; 0 if there are none."""
    i, n = 0, len(s)
    while i < n and s[i] in " \t\n\v\f\r":
        i += 1
    sign = 1
    if i < n and s[i] in "+-":
        sign = -1 if s[i] == "-" else 1
        i += 1
    j = i
    while j < n and "0" <= s[j] <= "9":
        j += 1
    return sign * int(s[i:j]) if j > i else 0
