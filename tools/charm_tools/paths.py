"""Where the Charm checkout is.

The repo root is the nearest directory above this package (or above CHARM_ROOT, if set) that holds both
src/merc.h and area/area.lst.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKERS = (Path("src") / "merc.h", Path("area") / "area.lst")


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


def src_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / "src"


def area_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / "area"
