"""quickmud_tools port status: how much of the C game the Python game has ported, function by function.

The Python game is organised by topic, not by C file (plans/python-port.md), so the map from C to Python comes from
marker comments: a line "# C: <file>.c <function>" directly above the Python def that ports it, with " [partial]"
after it when only part of the function is ported so far (#25, decision 3). This reads the C game's functions
(c_functions.txt, frozen at the c-final tag when src/ was removed, #112) and every marker in game/quickmud/, and reports per C file what's ported, what's partial and where it went, plus
Python lines per C line for the fully ported functions. A marker that names no C function is an error.

It also lists the improvements noted for later: "# LATER: <what>" comments, put where a refactor or a faster
structure would go once the port matches the C (plans/python-port.md, Improvements for later). One with nothing
after the colon is an error.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import find_root, game_dir

MARKER = re.compile(r"^\s*# C: (\S+\.c) (\w+)( \[partial\])?\s*$")
LATER = re.compile(r"#\s*LATER:(.*)$")
CONTINUED = re.compile(r"^\s*#\s(.*)$")
ISSUE = re.compile(r"#\d+")


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
    module: str  # path under game/, e.g. quickmud/core/rng.py
    def_name: str | None
    lines: int  # lines of the Python def (0 if the marker isn't above a def)
    line: int
    partial: bool = False


@dataclass
class Later:
    module: str  # path under game/
    line: int
    text: str


@dataclass
class Status:
    functions: list[CFunction]
    c_lines: dict[str, int]
    ports: list[Port]
    bad_markers: list[str] = field(default_factory=list)
    python_lines: int = 0  # every line of game/quickmud/**/*.py outside data/
    no_counterpart: dict = field(default_factory=dict)  # (C file, function): reason (quickmud/core/no_counterpart.py)
    kept: dict = field(default_factory=dict)  # (C file, function): the difference (quickmud/core/kept_differences.py)
    later: list[Later] = field(default_factory=list)


C_FUNCTIONS = Path(__file__).with_name("c_functions.txt")


def c_functions(path: Path = C_FUNCTIONS) -> tuple[list[CFunction], dict[str, int]]:
    """The C game's functions and each C file's length, as frozen at c-final."""
    functions, c_lines = [], {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        f, name, a, *b = line.split()
        if name == "lines":
            c_lines[f] = int(a)
        else:
            functions.append(CFunction(f, name, int(a), int(b[0])))
    return functions, c_lines


def markers(root: Path) -> list[Port]:
    ports = []
    pkg = game_dir(root)
    for py in sorted((pkg / "quickmud").rglob("*.py")):
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
                              (node.end_lineno - node.lineno + 1) if node else 0, n, bool(m.group(3))))
    return ports


def later_notes(root: Path) -> list[Later]:
    pkg = game_dir(root)
    out = []
    for py in sorted((pkg / "quickmud").rglob("*.py")):
        lines = py.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            m = LATER.search(line)
            if not m:
                continue
            text = m.group(1).strip()
            k = n
            while k < len(lines) and CONTINUED.match(lines[k]) and not LATER.search(lines[k]) \
                    and not MARKER.match(lines[k]):  # a note can run on over the comment lines below it
                text += " " + CONTINUED.match(lines[k]).group(1).strip()
                k += 1
            out.append(Later(py.relative_to(pkg).as_posix(), n, text))
    return out


def status(root: Path | None = None) -> Status:
    root = root or find_root()
    functions, c_lines = c_functions()
    known = {(f.file, f.name) for f in functions}
    ports = markers(root)
    bad = [f"game/{p.module}:{p.line}: '# C: {p.c_file} {p.c_name}' names no C function"
           for p in ports if (p.c_file, p.c_name) not in known]
    bad += [f"game/{p.module}:{p.line}: '# C: {p.c_file} {p.c_name}' isn't directly above a def"
            for p in ports if p.def_name is None]
    pkg = game_dir(root) / "quickmud"
    # Not data/ (generated) or testing/ (the scenario player, #35): neither is ported game code.
    python_lines = sum(len(py.read_text(encoding="utf-8").splitlines()) for py in pkg.rglob("*.py")
                       if py.relative_to(pkg).parts[0] not in ("data", "testing"))
    later = later_notes(root)
    bad += [f"game/{n.module}:{n.line}: '# LATER:' says nothing" for n in later if not n.text]
    none = no_counterpart(root)
    marked = {(p.c_file, p.c_name) for p in ports}
    bad += [f"quickmud/core/no_counterpart.py: {f} {n} names no C function" for f, n in none if (f, n) not in known]
    bad += [f"quickmud/core/no_counterpart.py: {f} {n} has a '# C:' marker too" for f, n in none if (f, n) in marked]
    kept = kept_differences(root)
    whole = {(p.c_file, p.c_name) for p in ports if not p.partial}
    part = {(p.c_file, p.c_name) for p in ports if p.partial}
    for (f, n), why in sorted(kept.items()):
        where = f"quickmud/core/kept_differences.py: {f} {n}"
        if (f, n) not in known:
            bad.append(f"{where} names no C function")
        elif (f, n) in part:
            bad.append(f"{where} still has a [partial] marker")
        elif (f, n) not in whole:
            bad.append(f"{where} has no '# C:' marker")
        if not ISSUE.search(why):
            bad.append(f"{where} cites no issue (#N)")
    return Status(functions, c_lines, ports, bad, python_lines, later=later, no_counterpart=none, kept=kept)


def _literal(root: Path, module: str, name: str) -> dict:
    """A dict assigned in quickmud/core/<module>.py, read as a literal (the game isn't imported)."""
    path = game_dir(root) / "quickmud" / "core" / f"{module}.py"
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def no_counterpart(root: Path) -> dict:
    return _literal(root, "no_counterpart", "NO_COUNTERPART")


def kept_differences(root: Path) -> dict:
    return _literal(root, "kept_differences", "KEPT_DIFFERENCES")


def report(st: Status) -> str:
    full = [p for p in st.ports if not p.partial]
    ported = {(p.c_file, p.c_name) for p in full} | set(st.no_counterpart)
    partial = {(p.c_file, p.c_name) for p in st.ports if p.partial} - ported
    by_file: dict[str, list[CFunction]] = {}
    for f in st.functions:
        by_file.setdefault(f.file, []).append(f)
    out = [f"{'C file':<14} {'lines':>6}  {'ported':>6} {'partial':>7} {'of':>4}  Python modules"]
    for name in sorted(st.c_lines):
        fns = by_file.get(name, [])
        done = [f for f in fns if (f.file, f.name) in ported]
        part = [f for f in fns if (f.file, f.name) in partial]
        mods = sorted({p.module for p in st.ports if p.c_file == name})
        out.append(f"{name:<14} {st.c_lines[name]:>6}  {len(done):>6} {len(part):>7} {len(fns):>4}  "
                   f"{', '.join(mods)}")
    total = len(st.functions)
    done = [f for f in st.functions if (f.file, f.name) in ported]
    part = [f for f in st.functions if (f.file, f.name) in partial]
    c_done = sum(f.lines for f in done)
    py_done = sum({(p.module, p.def_name): p.lines for p in full if p.def_name}.values())
    out.append("")
    out.append(f"{len(done)} of {total} C functions ported ({100 * len(done) / total:.1f}%), {len(part)} more "
               f"partly: {c_done} + {sum(f.lines for f in part)} of {sum(f.lines for f in st.functions)} lines of C "
               f"functions")
    if c_done:
        out.append(f"Python lines per C line, for the ported functions: {py_done / c_done:.2f} "
                   f"({py_done} / {c_done})")
    c_any = c_done + sum(f.lines for f in part)
    if c_any:
        out.append(f"All hand-written Python in game/quickmud (not data/, which is generated, or testing/), per C line "
                   f"ported or partly ported:{st.python_lines / c_any:.2f} ({st.python_lines} / {c_any})")
    if st.no_counterpart:
        out.append("")
        out.append(f"Counted as done with no Python counterpart ({len(st.no_counterpart)}, quickmud/core/no_counterpart.py):")
        out += [f"  {f} {n}: {why}" for (f, n), why in sorted(st.no_counterpart.items())]
    if st.kept:
        out.append("")
        out.append(f"Ported whole but for a difference kept on purpose ({len(st.kept)}, "
                   f"quickmud/core/kept_differences.py):")
        out += [f"  {f} {n}: {why}" for (f, n), why in sorted(st.kept.items())]
    notes = [n for n in st.later if n.text]
    if notes:
        out.append("")
        out.append(f"Improvements noted for later ({len(notes)} '# LATER:' comments; the cross-cutting ones are in "
                   f"plans/python-port.md):")
        out += [f"  game/{n.module}:{n.line}  {n.text}" for n in notes]
    out += [f"error: {b}" for b in st.bad_markers]
    return "\n".join(out)


def run() -> int:
    st = status()
    print(report(st))
    return 1 if st.bad_markers else 0
