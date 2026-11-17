"""charm_tools port status: how much of the C game the Python game has ported, function by function.

The Python game is organised by topic, not by C file (plans/python-port.md), so the map from C to Python comes from
marker comments: a line "# C: <file>.c <function>" directly above the Python def that ports it. This reads every C
function in src/ and every marker in game/charm/, and reports per C file what's ported and where it went, plus
Python lines per C line for the ported functions. A marker that names no C function is an error.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import find_root, game_dir, src_dir

MARKER = re.compile(r"^\s*# C: (\S+\.c) (\w+)\s*$")
# A definition starts in column 0 with a return type, the name and "(". Its body opens with "{" at the end of the
# parameter list or in column 0 on a following line (ROM's style throughout), and closes with "}" in column 0.
DEF_START = re.compile(r"^(?!typedef\b|#|/|\s)[A-Za-z_][\w\s*]*?\b([A-Za-z_]\w*)\s*\(")
NOT_NAMES = {"if", "while", "for", "switch", "return", "sizeof", "args"}
# OLC defines its editor functions through macros: "REDIT( redit_show )" is bool redit_show(CHAR_DATA *, char *).
MACRO_DEF = re.compile(r"^[A-Z][A-Z_]*\s*\(\s*([a-z_]\w*)\s*\)\s*$")
COMMENT = re.compile(r"/\*.*?\*/", re.S)


@dataclass
class CFunction:
    file: str
    name: str
    start: int  # 1-based line of the definition
    end: int  # 1-based line of the closing brace

    @property
    def lines(self) -> int:
        return self.end - self.start + 1


@dataclass
class Port:
    c_file: str
    c_name: str
    module: str  # path under game/, e.g. charm/core/rng.py
    def_name: str | None
    lines: int  # lines of the Python def (0 if the marker isn't above a def)
    line: int


@dataclass
class Status:
    functions: list[CFunction]
    c_lines: dict[str, int]
    ports: list[Port]
    bad_markers: list[str] = field(default_factory=list)


def c_functions(path: Path) -> list[CFunction]:
    """Every function defined in a C file, going by ROM's layout (see DEF_START)."""
    # Blank out comments, keeping their newlines, so commented-out code isn't counted and line numbers hold.
    text = COMMENT.sub(lambda c: re.sub(r"[^\n]", " ", c.group()), path.read_bytes().decode("latin-1"))
    lines = text.splitlines()
    found = []
    i = 0
    while i < len(lines):
        m = MACRO_DEF.match(lines[i]) or DEF_START.match(lines[i])
        if m and m.group(1) not in NOT_NAMES:
            # Join lines until the parameter list closes. What follows it says what this is: ";" a prototype,
            # "{" (here or on a later line) a definition.
            j, text = i, lines[i]
            while text.count("(") > text.count(")") and j + 1 < len(lines):
                j += 1
                text += " " + lines[j]
            after = text[text.rfind(")") + 1:].strip()
            body = None
            if after.startswith("{"):
                body = j
            elif after == "":
                k = j + 1
                while k < len(lines) and lines[k].strip() == "":
                    k += 1
                if k < len(lines) and lines[k].startswith("{"):
                    body = k
            if body is not None:
                end = next((k for k in range(body, len(lines)) if lines[k].startswith("}")), None)
                if end is not None:
                    found.append(CFunction(path.name, m.group(1), i + 1, end + 1))
                    i = end + 1
                    continue
        i += 1
    return found


def markers(root: Path) -> list[Port]:
    ports = []
    pkg = game_dir(root)
    for py in sorted((pkg / "charm").rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        tree = ast.parse(text)
        defs = {n.lineno: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        lines = text.splitlines()
        for n, line in enumerate(lines, 1):
            m = MARKER.match(line)
            if not m:
                continue
            k = n + 1
            while k <= len(lines) and MARKER.match(lines[k - 1]):  # several markers can sit above one def
                k += 1
            node = defs.get(k)
            ports.append(Port(m.group(1), m.group(2), py.relative_to(pkg).as_posix(),
                              node.name if node else None,
                              (node.end_lineno - node.lineno + 1) if node else 0, n))
    return ports


def status(root: Path | None = None) -> Status:
    root = root or find_root()
    functions, c_lines = [], {}
    for c in sorted(src_dir(root).glob("*.c")):
        functions += c_functions(c)
        c_lines[c.name] = len(c.read_bytes().splitlines())
    known = {(f.file, f.name) for f in functions}
    ports = markers(root)
    bad = [f"game/{p.module}:{p.line}: '# C: {p.c_file} {p.c_name}' names no C function"
           for p in ports if (p.c_file, p.c_name) not in known]
    bad += [f"game/{p.module}:{p.line}: '# C: {p.c_file} {p.c_name}' isn't directly above a def"
            for p in ports if p.def_name is None]
    return Status(functions, c_lines, ports, bad)


def report(st: Status) -> str:
    ported = {(p.c_file, p.c_name) for p in st.ports}
    by_file: dict[str, list[CFunction]] = {}
    for f in st.functions:
        by_file.setdefault(f.file, []).append(f)
    out = [f"{'C file':<14} {'lines':>6}  {'ported':>9}  Python modules"]
    for name in sorted(st.c_lines):
        fns = by_file.get(name, [])
        done = [f for f in fns if (f.file, f.name) in ported]
        mods = sorted({p.module for p in st.ports if p.c_file == name})
        out.append(f"{name:<14} {st.c_lines[name]:>6}  {len(done):>4}/{len(fns):<4}  {', '.join(mods)}")
    total = len(st.functions)
    done = [f for f in st.functions if (f.file, f.name) in ported]
    c_done = sum(f.lines for f in done)
    py_done = sum({(p.module, p.def_name): p.lines for p in st.ports if p.def_name}.values())
    out.append("")
    out.append(f"{len(done)} of {total} C functions ported ({100 * len(done) / total:.1f}%): "
               f"{c_done} of {sum(f.lines for f in st.functions)} lines of C functions")
    if c_done:
        out.append(f"Python lines per C line, for the ported functions: {py_done / c_done:.2f} "
                   f"({py_done} / {c_done})")
    out += [f"error: {b}" for b in st.bad_markers]
    return "\n".join(out)


def run() -> int:
    st = status()
    print(report(st))
    return 1 if st.bad_markers else 0
