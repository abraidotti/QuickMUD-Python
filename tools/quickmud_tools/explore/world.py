"""The area loader, from the Python game (game/quickmud/world/areafile), with quickmud_tools' defaults for where area/ is.

T1 wrote the loader here; P1 (#25) moved it into the game, which now owns it. Explore uses the game's own loader, so
what it checks is what the game will load.
"""

from __future__ import annotations

from pathlib import Path

from ..paths import area_dir as _area_dir
from ..paths import use_game

use_game()

from quickmud.world.areafile.boot import Counts  # noqa: E402  (after use_game)
from quickmud.world.areafile.world import World  # noqa: E402
from quickmud.world.areafile.world import load_world as _load_world  # noqa: E402

__all__ = ["Counts", "World", "load_world"]


def load_world(root: Path | None = None, area_dir: Path | None = None) -> World:
    """Boot every area in area.lst: this checkout's area/ by default, or another copy of it."""
    return _load_world(area_dir or _area_dir(root))
