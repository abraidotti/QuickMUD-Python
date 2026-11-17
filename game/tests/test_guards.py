"""Rules the whole package keeps, checked by reading the source (plans/python-port.md, #23).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import ast
import re
import unittest
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
PACKAGE = GAME / "charm"
MODULES = sorted(PACKAGE.rglob("*.py")) + sorted((GAME / "tests").rglob("*.py"))

CREDIT = ("Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik "
          "Staerfeldt, Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell "
          "Tse; and ROM 2.4 (c) 1993-98 Russ Taylor.")
POINTER = "Licence terms: README.md#licence-terms and doc/."
SOURCE = re.compile(r"(Ported from src/\w+\.c(, src/\w+\.c)*\.|Written for Charm; no single C source\.)")

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
