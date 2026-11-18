"""Rules the whole package keeps, checked by reading the source (plans/python-port.md, #23).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import ast
import io
import re
import textwrap
import tokenize
import unittest
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
PACKAGE = GAME / "charm"
MODULES = sorted(PACKAGE.rglob("*.py")) + sorted((GAME / "tests").rglob("*.py"))

CREDIT = ("Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik "
          "Staerfeldt, Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell "
          "Tse; and ROM 2.4 (c) 1993-98 Russ Taylor.")
POINTER = "Licence terms: README.md#licence-terms and doc/."
SOURCE = re.compile(r"(Ported from src/\w+\.[ch](, src/\w+\.[ch])*\.|Written for Charm; no single C source\.)")

# Which charm packages each layer may import. Rules for the layers after world wait until the port shows where the
# C game's circular calls land (#23, decision 3).
LAYERS = {"core": {"core"}, "data": {"core", "data"}, "world": {"core", "data", "world"}}


def docstring(path):
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


def charm_imports(path, package_parts):
    """Every charm.* module path imports, with relative imports resolved."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package_parts[: len(package_parts) - node.level + 1])
                yield ".".join(base + ([node.module] if node.module else []))
            else:
                yield node.module


# -- Divergence guards (#35, decision 6) -----------------------------------------------------------------------------
# Each guard reads one module and returns (line, what) for every place the Python would go quietly different from
# the C. A line it should allow carries a comment that starts with the guard's marker and says why, such as
# "# clock: the loop's pulse". DivergenceGuards runs them over game/charm; GuardsCatch checks each one on snippets.

# Python's // and % floor, and the C's / and % truncate: they differ when one side is negative. cint.c_div and
# c_mod do what the C does.
DIVISION_HOME = {"core/cint.py"}
# Python's lower() and upper() change letters over 127 too; core.strings changes A-Z and a-z only, like LOWER.
CASE_HOME = {"core/strings.py"}
CASE_CALLS = {"lower", "upper", "casefold", "capitalize", "title", "swapcase"}
# The area files as read, before boot makes runtime things of them. They're values: the loader's tests compare
# them whole.
VALUE_PACKAGES = ("world/areafile/",)
# Lists the C keeps head-first: it adds to the front, so the Python inserts at 0.
HEAD_FIRST = {"people", "contents", "carrying", "contains", "affected", "char_list", "object_list",
              "descriptor_list"}


def comments(src):
    """{line number: the comment on it}."""
    return {tok.start[0]: tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline)
            if tok.type == tokenize.COMMENT}


def marked(notes, first, last, *markers):
    """True if a line from first to last carries a comment that starts with one of markers."""
    return any(notes.get(n, "").startswith(markers) for n in range(first, last + 1))


def imported(node):
    """The absolute module names an import statement names."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom) and not node.level:
        return [node.module or ""]
    return []


def random_finds(rel, text):
    """The game draws from core.rng, the C's random(); Python's random would draw other numbers."""
    return [(node.lineno, f"imports {n}") for node in ast.walk(ast.parse(text)) for n in imported(node)
            if n.split(".")[0] in ("random", "secrets", "numpy")]


def clock_finds(rel, text):
    """The game's time is game.current_time, set by the loop (or a scenario's clock). Reading the real clock
    anywhere else gives a different answer from the C's, and makes scenarios unrepeatable."""
    notes, finds = comments(text), []
    for node in ast.walk(ast.parse(text)):
        what = None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "time":
            what = f"time.{node.attr}"
        elif isinstance(node, ast.ImportFrom) and node.module in ("time", "datetime"):
            what = f"from {node.module} import"
        elif "datetime" in imported(node):
            what = "import datetime"
        if what and not marked(notes, node.lineno, node.end_lineno, "# clock:"):
            finds.append((node.lineno, what))
    return finds


def division_finds(rel, text):
    if rel in DIVISION_HOME:
        return []
    notes, finds = comments(text), []
    for node in ast.walk(ast.parse(text)):
        op = node.op if isinstance(node, (ast.BinOp, ast.AugAssign)) else None
        if not isinstance(op, (ast.FloorDiv, ast.Mod)):
            continue
        left = node.left if isinstance(node, ast.BinOp) else node.target
        if isinstance(op, ast.Mod) and (isinstance(left, ast.JoinedStr) or
                                        isinstance(left, ast.Constant) and isinstance(left.value, str)):
            continue  # "..." % args formats a string
        if not marked(notes, node.lineno, node.end_lineno, "# non-negative:", "# format:"):
            finds.append((node.lineno, "//" if isinstance(op, ast.FloorDiv) else "%"))
    return finds


def case_finds(rel, text):
    if rel in CASE_HOME:
        return []
    notes = comments(text)
    return [(node.lineno, f".{node.func.attr}()") for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CASE_CALLS
            and not marked(notes, node.lineno, node.end_lineno, "# not LOWER:")]


def identity_finds(rel, text):
    """The C compares pointers: two characters with the same fields are still two characters. A dataclass
    compares fields unless it says eq=False, so `ch in room.people` or `list.remove` could pick the wrong one."""
    if rel.startswith(VALUE_PACKAGES):
        return []
    notes, finds = comments(text), []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.ClassDef):
            continue
        for d in node.decorator_list:
            call = d if isinstance(d, ast.Call) else None
            if ast.unparse(call.func if call else d) not in ("dataclass", "dataclasses.dataclass"):
                continue
            keywords = {k.arg: k.value for k in (call.keywords if call else [])}
            eq, frozen = keywords.get("eq"), keywords.get("frozen")
            if isinstance(eq, ast.Constant) and eq.value is False:
                continue
            if isinstance(frozen, ast.Constant) and frozen.value is True:
                continue  # a frozen value, like Dice: nothing to tell apart
            if not marked(notes, d.lineno, node.lineno, "# value:"):
                finds.append((node.lineno, f"@dataclass class {node.name} without eq=False"))
    return finds


def head_first_finds(rel, text):
    """The C pushes onto the head of its lists, so the newest comes first, and that order shows (who's listed
    first in a room, which object `get` takes). Appending would reverse it."""
    finds = []
    for node in ast.walk(ast.parse(text)):
        target = what = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("append",
                                                                                                    "extend"):
            target, what = node.func.value, f".{node.func.attr}()"
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            target, what = node.target, " +="
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name in HEAD_FIRST:
            finds.append((node.lineno, f"{name}{what}"))
    return finds


def synchronous_finds(rel, text):
    """The C game is one thread, and its order of events is the port's. No coroutines or threads."""
    finds = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            finds.append((node.lineno, type(node).__name__))
        finds += [(node.lineno, f"imports {n}") for n in imported(node)
                  if n.split(".")[0] in ("threading", "asyncio", "concurrent", "multiprocessing", "_thread")]
    return finds


GUARDS = [random_finds, clock_finds, division_finds, case_finds, identity_finds, head_first_finds,
          synchronous_finds]


class DivergenceGuards(unittest.TestCase):
    """Every guard, over every module in game/charm. A failure lists each line, with what it found."""

    def test_game_keeps_every_guard(self):
        modules = [(p.relative_to(PACKAGE).as_posix(), p.read_text(encoding="utf-8"))
                   for p in sorted(PACKAGE.rglob("*.py"))]
        self.assertTrue(modules)
        for guard in GUARDS:
            with self.subTest(guard=guard.__name__):
                finds = [f"game/charm/{rel}:{n}: {what}" for rel, text in modules for n, what in guard(rel, text)]
                if finds:
                    self.fail("\n" + "\n".join(finds))


class GuardsCatch(unittest.TestCase):
    """Each guard on snippets: it finds what it's for, and a marked line or the safe way passes."""

    def finds(self, guard, text, rel="net/x.py"):
        return [what for _, what in sorted(guard(rel, textwrap.dedent(text)))]

    def test_random(self):
        self.assertEqual(self.finds(random_finds, "import random\nfrom random import randint\n"),
                         ["imports random", "imports random"])
        self.assertEqual(self.finds(random_finds, "from charm.core.rng import number_range\n"), [])

    def test_clock(self):
        self.assertEqual(self.finds(clock_finds, "import time\nt = time.time()\n"), ["time.time"])
        self.assertEqual(self.finds(clock_finds, "from time import time\nimport datetime\n"),
                         ["from time import", "import datetime"])
        self.assertEqual(self.finds(clock_finds, "t = time.time()  # clock: the loop's\n"), [])

    def test_division(self):
        self.assertEqual(self.finds(division_finds, "a = b // 2\nc = d % 3\ne //= 2\n"), ["//", "%", "//"])
        self.assertEqual(self.finds(division_finds, 'a = "%d" % n\nb = f"{n}" % ()\nc = c_div(x, 2)\n'), [])
        self.assertEqual(self.finds(division_finds, "a = (b +\n     c) // 2  # non-negative: a count\n"), [])
        self.assertEqual(self.finds(division_finds, "s = fmt % args  # format: sprintf\n"), [])
        self.assertEqual(self.finds(division_finds, "a = b // 2\n", rel="core/cint.py"), [])

    def test_case(self):
        self.assertEqual(self.finds(case_finds, "a = s.lower()\nb = s[0].upper()\nc = s.casefold()\n"),
                         [".lower()", ".upper()", ".casefold()"])
        self.assertEqual(self.finds(case_finds, "a = lower(s)\nb = str_cmp(s, t)\n"), [])
        self.assertEqual(self.finds(case_finds, "a = s.lower()  # not LOWER: a file name\n"), [])

    def test_identity(self):
        bad = "@dataclass\nclass Char:\n    pass\n\n@dataclass(eq=True)\nclass Obj:\n    pass\n"
        self.assertEqual(self.finds(identity_finds, bad),
                         ["@dataclass class Char without eq=False", "@dataclass class Obj without eq=False"])
        good = ("@dataclass(eq=False)\nclass Char:\n    pass\n\n@dataclass(frozen=True)\nclass Dice:\n    pass\n\n"
                "@dataclass  # value: settings\nclass Config:\n    pass\n")
        self.assertEqual(self.finds(identity_finds, good), [])
        self.assertEqual(self.finds(identity_finds, bad, rel="world/areafile/model.py"), [])

    def test_head_first(self):
        bad = "room.people.append(ch)\ngame.char_list.extend(mobs)\nch.carrying += [obj]\n"
        self.assertEqual(self.finds(head_first_finds, bad),
                         ["people.append()", "char_list.extend()", "carrying +="])
        self.assertEqual(self.finds(head_first_finds, "room.people.insert(0, ch)\nout.append(line)\n"), [])

    def test_synchronous(self):
        self.assertEqual(self.finds(synchronous_finds, "import threading\nasync def f():\n    await g()\n"),
                         ["imports threading", "AsyncFunctionDef", "Await"])
        self.assertEqual(self.finds(synchronous_finds, "import selectors\n"), [])


class LicenceHeader(unittest.TestCase):
    def test_every_module_carries_it(self):
        self.assertTrue(MODULES)
        for path in MODULES:
            with self.subTest(module=str(path.relative_to(GAME))):
                text = " ".join(docstring(path).split())
                self.assertIn(CREDIT, text)
                self.assertIn(POINTER, text)
                self.assertRegex(text, SOURCE)


class Layers(unittest.TestCase):
    def test_imports_go_one_way(self):
        for path in sorted(PACKAGE.rglob("*.py")):
            rel = path.relative_to(PACKAGE).parts
            layer = rel[0] if len(rel) > 1 else None
            if layer not in LAYERS:
                continue
            package_parts = ("charm",) + rel[:-1]
            for name in charm_imports(path, package_parts):
                parts = name.split(".")
                if parts[0] == "charm" and len(parts) > 1:
                    with self.subTest(module=str(path.relative_to(GAME)), imports=name):
                        self.assertIn(parts[1], LAYERS[layer])


if __name__ == "__main__":
    unittest.main()
