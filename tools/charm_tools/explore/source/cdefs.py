"""#define values from merc.h (and friends), evaluated the way the C compiler would for simple constants.

Handles integer literals, the flag letters (``#define A 1`` ... ``#define ee 1073741824``), other defines, ``|``,
``+``, ``-``, ``*``, ``<<`` and parentheses. Anything else raises SourceError when it's asked for, not when the
file is read, so one odd macro elsewhere doesn't stop the rest.
"""

from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path


class SourceError(Exception):
    pass


_DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?![\w(])[ \t]*(.*?)\s*$")
_COMMENT = re.compile(r"/\*.*?\*/|//.*$")
_TOKEN = re.compile(r"\s*(?:(0[xX][0-9a-fA-F]+|\d+)[uUlL]*|([A-Za-z_]\w*)|(<<|[|+\-*()]))")


class Defines:
    def __init__(self, *paths: Path):
        self.paths = paths
        self.raw: dict[str, str] = {}
        for path in paths:
            # merc.h has platform branches with different values for the same name; the unix branch is last and
            # wins, matching what the Linux build sees for the names we use (PLAYER_DIR etc. aren't numbers anyway).
            text = path.read_text(encoding="latin-1")
            text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
            for line in text.splitlines():
                m = _DEFINE.match(_COMMENT.sub("", line))
                if m and m.group(2):
                    self.raw[m.group(1)] = m.group(2)

    def __contains__(self, name: str) -> bool:
        return name in self.raw

    def __getitem__(self, name: str) -> int:
        return self.value(name)

    def value(self, name: str, _seen: tuple[str, ...] = ()) -> int:
        if name in _seen:
            raise SourceError(f"#define {name} refers to itself")
        if name not in self.raw:
            raise SourceError(f"no #define {name} in {', '.join(p.name for p in self.paths)}")
        return self._eval(self.raw[name], (*_seen, name))

    def _eval(self, expr: str, seen: tuple[str, ...]) -> int:
        tokens: list[str | int] = []
        pos = 0
        while pos < len(expr):
            m = _TOKEN.match(expr, pos)
            if not m or m.end() == pos:
                if expr[pos:].strip() == "":
                    break
                raise SourceError(f"can't evaluate #define {seen[-1]} {expr!r}")
            num, name, op = m.groups()
            if num is not None:
                tokens.append(int(num, 0))
            elif name is not None:
                tokens.append(self.value(name, seen))
            else:
                tokens.append(op)
            pos = m.end()
        value, rest = _parse_or(tokens)
        if rest:
            raise SourceError(f"can't evaluate #define {seen[-1]} {expr!r}")
        return value

    @cached_property
    def names(self) -> list[str]:
        return list(self.raw)

    def with_prefix(self, prefix: str) -> dict[str, int]:
        """Every define starting with prefix that evaluates to a number, e.g. with_prefix("OBJ_VNUM_")."""
        out = {}
        for name in self.raw:
            if name.startswith(prefix):
                try:
                    out[name] = self.value(name)
                except SourceError:
                    pass
        return out


# A tiny precedence-climbing parser: | lowest, then + -, then << , then *, then unary - and parentheses.
def _parse_or(t):
    v, t = _parse_add(t)
    while t and t[0] == "|":
        r, t = _parse_add(t[1:])
        v |= r
    return v, t


def _parse_add(t):
    v, t = _parse_shift(t)
    while t and t[0] in ("+", "-"):
        op = t[0]
        r, t = _parse_shift(t[1:])
        v = v + r if op == "+" else v - r
    return v, t


def _parse_shift(t):
    v, t = _parse_mul(t)
    while t and t[0] == "<<":
        r, t = _parse_mul(t[1:])
        v <<= r
    return v, t


def _parse_mul(t):
    v, t = _parse_unary(t)
    while t and t[0] == "*":
        r, t = _parse_unary(t[1:])
        v *= r
    return v, t


def _parse_unary(t):
    if not t:
        raise SourceError("expression ends early")
    if t[0] == "-":
        v, t = _parse_unary(t[1:])
        return -v, t
    if t[0] == "(":
        v, t = _parse_or(t[1:])
        if not t or t[0] != ")":
            raise SourceError("unbalanced parentheses")
        return v, t[1:]
    if isinstance(t[0], int):
        return t[0], t[1:]
    raise SourceError(f"unexpected {t[0]!r}")
