"""Narrow readers for the C tables the area loader looks names up in.

``read_array(path, name)`` finds ``name[...] = { {...}, {...}, ... };`` in a C file and returns each entry's
top-level fields as strings, with string literals unquoted and marked. The tables used by T1:

    item_table   const.c    {ITEM_LIGHT, "light"}            item_lookup: word -> item type
    weapon_table const.c    {"sword", ..., WEAPON_SWORD, ..}  weapon_type
    liq_table    const.c    {"water", ...}                    liq_lookup (CHECK_POS)
    race_table   const.c    {"unique", ...}                   race_lookup (no error: 0 if not found)
    size_table   tables.c   {"tiny"}                          size_lookup (CHECK_POS)
    mprog_flags  tables.c   {"act", TRIG_ACT, TRUE}           flag_lookup (NO_FLAG is fatal)
    clan_table   tables.c   {"", "", ROOM_VNUM_ALTAR, TRUE}   clan_lookup
    spec_table   special.c  {"spec_breath_any", ...}          spec_lookup (0 is fatal)

T2 adds the full readers (class, race, skill tables) on the same footing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .cdefs import Defines, SourceError


@dataclass(frozen=True)
class Str:
    """A C string literal's value."""

    value: str


Field = str | Str


def _strip_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _split_top(body: str) -> list[str]:
    """Split on commas not inside braces, parentheses or strings."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(body):
        c = body[i]
        if c == '"':
            i += 1
            while i < len(body) and body[i] != '"':
                i += 2 if body[i] == "\\" else 1
        elif c in "{(":
            depth += 1
        elif c in "})":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    parts.append(body[start:])
    return [p.strip() for p in parts if p.strip()]


def _field(text: str) -> Field:
    if text.startswith('"') and text.endswith('"'):
        return Str(bytes(text[1:-1], "latin-1").decode("unicode_escape"))
    return text


def read_array(path: Path, name: str) -> list[list[Field]]:
    text = _strip_comments(path.read_text(encoding="latin-1"))
    m = re.search(rf"\b{re.escape(name)}\s*\[[^\]]*\]\s*=\s*\{{", text)
    if not m:
        raise SourceError(f"no '{name}[] = {{' in {path.name}")
    i, depth, start = m.end(), 1, m.end()
    while i < len(text) and depth:
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    if depth:
        raise SourceError(f"unbalanced braces in {name} ({path.name})")
    entries = []
    for entry in _split_top(text[start:i - 1]):
        if not (entry.startswith("{") and entry.endswith("}")):
            raise SourceError(f"{name} ({path.name}): entry isn't a {{...}}: {entry[:40]!r}")
        entries.append([_field(f) for f in _split_top(entry[1:-1])])
    return entries


def _names(entries: list[list[Field]], index: int, table: str) -> list[str]:
    """The string at position ``index`` of each entry, up to the NULL terminator."""
    out = []
    for e in entries:
        f = e[index] if index < len(e) else None
        if f == "NULL" or f is None:
            break
        if not isinstance(f, Str):
            raise SourceError(f"{table}: expected a string at field {index}, got {f!r}")
        out.append(f.value)
    return out


@dataclass
class LookupTables:
    """The tables boot_db's loaders look names up in, read from the source."""

    item_types: list[tuple[str, int]]  # (name, ITEM_ value), in item_table order
    weapon_types: list[tuple[str, int]]
    liquids: list[str]
    races: list[str]
    sizes: list[str]
    mprog_triggers: list[tuple[str, int]]
    clans: list[str]
    specials: list[str]
    defines: Defines

    @classmethod
    def from_source(cls, src: Path) -> "LookupTables":
        d = Defines(src / "merc.h")
        const, tables, special = src / "const.c", src / "tables.c", src / "special.c"
        items = [(f[1].value, d[f[0]]) for f in read_array(const, "item_table") if f[1] != "NULL"]
        weapons = [(f[0].value, d[f[2]]) for f in read_array(const, "weapon_table") if f[0] != "NULL"]
        trig = [(f[0].value, d[f[1]]) for f in read_array(tables, "mprog_flags") if f[0] != "NULL"]
        return cls(
            item_types=items,
            weapon_types=weapons,
            liquids=_names(read_array(const, "liq_table"), 0, "liq_table"),
            races=_names(read_array(const, "race_table"), 0, "race_table"),
            sizes=_names(read_array(tables, "size_table"), 0, "size_table"),
            mprog_triggers=trig,
            clans=[f[0].value for f in read_array(tables, "clan_table")],
            specials=_names(read_array(special, "spec_table"), 0, "spec_table"),
            defines=d,
        )


def prefix_lookup(name: str, names: list[str]) -> int:
    """The ROM lookup idiom: first letters equal (case-insensitively) and name a prefix of the entry
    (``!str_prefix(name, entry)``). Index of the first match, or -1. An empty name never matches."""
    if not name:
        return -1
    low = name.lower()
    for i, entry in enumerate(names):
        if entry and entry[0].lower() == low[0] and entry.lower().startswith(low):
            return i
    return -1


def str_prefix_matches(astr: str, bstr: str) -> bool:
    """``!str_prefix(astr, bstr)``: astr is a case-insensitive prefix of bstr (an empty astr always is)."""
    return bstr.lower().startswith(astr.lower())
