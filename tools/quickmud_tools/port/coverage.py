"""quickmud_tools port coverage: which lines of the ported functions nothing runs (abraidotti/QuickMUD-Python#39, decision 6).

It runs the game's unit tests in this process (they replay every scenario's golden), or with --scenarios only the
scenarios, and records each line of game/quickmud that runs, and each function that starts, with sys.monitoring
(stdlib, Python 3.12+). Then, for each function with a "# C:" marker, it lists the lines that never ran, or says
that nothing called it.

It's a report, not a gate: a PR lists what's left and why (a branch that needs a fight, say, waits for P4).

    python -m quickmud_tools port coverage act_move.c act_enter.c     # the functions ported from these files
    python -m quickmud_tools port coverage --scenarios act_move.c     # what the scenarios alone reach
    python -m quickmud_tools port coverage                            # every ported function
"""

from __future__ import annotations

import ast
import io
import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from ..paths import find_root, game_dir, use_game
from .status import MARKER, markers


@dataclass
class Function:
    c_file: str
    c_name: str
    module: str  # relative to game/
    name: str
    first: int  # the def line
    code_first: int  # the code object's first line: the first decorator's, if any
    lines: list[int]  # every line of the body with code
    missing: list[int]
    called: bool = False


@dataclass
class Hits:
    lines: set[tuple[str, int]]  # (file, line) that ran
    starts: set[tuple[str, int]]  # (file, the code object's first line) of each function that started


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def record(run) -> Hits:
    """The lines of game/quickmud that run during run(), and the functions that start."""
    mon = sys.monitoring
    tool = mon.COVERAGE_ID
    prefix = _norm(str(game_dir() / "quickmud"))
    hits = Hits(set(), set())

    def on_line(code, line):
        f = _norm(code.co_filename)
        if f.startswith(prefix):
            hits.lines.add((f, line))
        return mon.DISABLE  # once is enough for this place in the code

    def on_start(code, offset):
        f = _norm(code.co_filename)
        if f.startswith(prefix):
            hits.starts.add((f, code.co_firstlineno))
        return mon.DISABLE

    mon.use_tool_id(tool, "quickmud_tools port coverage")
    try:
        mon.register_callback(tool, mon.events.LINE, on_line)
        mon.register_callback(tool, mon.events.PY_START, on_start)
        mon.set_events(tool, mon.events.LINE | mon.events.PY_START)
        run()
    finally:
        mon.set_events(tool, 0)
        mon.register_callback(tool, mon.events.LINE, None)
        mon.register_callback(tool, mon.events.PY_START, None)
        mon.free_tool_id(tool)
    return hits


def run_tests() -> None:
    game = game_dir()
    suite = unittest.defaultTestLoader.discover(str(game / "tests"), top_level_dir=str(game))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(f"port coverage: the game's tests fail ({len(result.failures)} failures, "
                         f"{len(result.errors)} errors); fix them first")


def run_scenarios() -> None:
    from quickmud.testing.scenario import play_fresh

    root = find_root()
    for scn in sorted((game_dir() / "tests" / "data" / "scenarios").glob("*.scn")):
        play_fresh(scn.read_text(encoding="latin-1"), root)


def _code_lines(code) -> set[int]:
    lines = {line for _, _, line in code.co_lines() if line is not None}
    for const in code.co_consts:
        if hasattr(const, "co_lines"):
            lines |= _code_lines(const)
    return lines


def functions(c_files: set[str] | None) -> list[Function]:
    """Every marked function (from c_files, if given), with the lines that have code."""
    root = find_root()
    game = game_dir(root)
    out = []
    by_module: dict[str, list] = {}
    for p in markers(root):
        if p.def_name and (not c_files or p.c_file in c_files):
            by_module.setdefault(p.module, []).append(p)
    for module, ports in sorted(by_module.items()):
        path = game / module
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        codes: dict[tuple[str, int], object] = {}
        stack = [compile(text, str(path), "exec")]
        while stack:
            code = stack.pop()
            codes[(code.co_name, code.co_firstlineno)] = code
            stack += [c for c in code.co_consts if hasattr(c, "co_lines")]
        defs = {n.lineno: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        src = text.splitlines()
        for p in ports:
            k = p.line + 1  # the def is the first line after the markers, as port status reads it
            while k <= len(src) and MARKER.match(src[k - 1]):
                k += 1
            node = defs.get(k)
            if node is None:
                continue
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            code = codes.get((node.name, first)) or codes.get((node.name, node.lineno))
            if code is None:
                continue
            # The def line has no line event of its own (its RESUME starts the function); PY_START covers it.
            lines = sorted(_code_lines(code) - {first, node.lineno})
            out.append(Function(p.c_file, p.c_name, module, node.name, node.lineno, code.co_firstlineno, lines, []))
    return out


def report(funcs: list[Function], hits: Hits, out=sys.stdout) -> int:
    root = find_root()
    game = game_dir(root)
    total = missed = 0
    for f in sorted(funcs, key=lambda f: (f.c_file, f.module, f.first)):
        path = game / f.module
        file = _norm(str(path))
        f.called = (file, f.code_first) in hits.starts
        f.missing = [n for n in f.lines if (file, n) not in hits.lines]
        total += len(f.lines)
        missed += len(f.missing)
        ran = len(f.lines) - len(f.missing)
        mark = "--" if not f.called else "- " if f.missing else "  "
        what = "never called" if not f.called else f"{ran}/{len(f.lines)} lines"
        print(f"{mark} {f.c_file} {f.c_name:<24} game/{f.module}:{f.first}  {what}", file=out)
        if f.called and f.missing:
            src = path.read_text(encoding="utf-8").splitlines()
            for n in f.missing:
                print(f"       {n:5}  {src[n - 1].strip()}", file=out)
    never = sum(1 for f in funcs if not f.called)
    print(f"{len(funcs)} functions, {total} lines with code: {total - missed} run, {missed} not "
          f"({never} functions never called)", file=out)
    return 0


def run(c_files: list[str], scenarios_only: bool) -> int:
    use_game()
    funcs = functions(set(c_files) if c_files else None)
    if not funcs:
        print("port coverage: no ported functions" + (f" from {', '.join(c_files)}" if c_files else ""))
        return 1
    hits = record(run_scenarios if scenarios_only else run_tests)
    return report(funcs, hits)
