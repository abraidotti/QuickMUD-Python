"""Where the Charm checkout is.

The repo root is the nearest directory above this package (or CHARM_ROOT, if set) that holds both the game
(game/charm/__init__.py) and area/area.lst.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKERS = (Path("game") / "charm" / "__init__.py", Path("area") / "area.lst")


class RootNotFound(Exception):
    pass


def is_root(path: Path) -> bool:
    return all((path / m).is_file() for m in MARKERS)


def find_root(start: Path | None = None) -> Path:
    """The Charm repo root: CHARM_ROOT if set, else the nearest parent of start (default: this package)."""
    env = os.environ.get("CHARM_ROOT")
    if env:
        root = Path(env).resolve()
        if not is_root(root):
            raise RootNotFound(f"CHARM_ROOT={env} has no {' or '.join(str(m) for m in MARKERS)}")
        return root
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if is_root(candidate):
            return candidate
    raise RootNotFound(f"no Charm checkout (with {' and '.join(str(m) for m in MARKERS)}) above {here}")


def area_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / "area"


def game_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / "game"


def use_game(root: Path | None = None) -> Path:
    """Make the Python game (game/charm) importable, without installing it (abraidotti/charm#23, decision 1)."""
    import sys
    path = str(game_dir(root))
    if path not in sys.path:
        sys.path.insert(0, path)
    return Path(path)
