"""boot_db: seed the random numbers, set the clock and weather, load the areas, then reset every area once.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import time
from pathlib import Path

from charm.core import log
from charm.core.cint import c_div, c_mod
from charm.core.errors import NotPorted
from charm.core.rng import init_mm, number_range
from charm.data import constants as C
from charm.entities import game as game_module
from charm.entities.game import Game, TimeInfo, WeatherInfo
from charm.entities.resets import area_update
from charm.persist.boards import load_boards
from charm.world.areafile.world import load_world
from charm.world.index import build_index


class BootFailed(SystemExit):
    """boot_db stopped, as the C game's exit(1) would."""


def set_time_and_weather(t: TimeInfo, w: WeatherInfo, current_time: int) -> None:
    """boot_db's "Set time and weather" block: the game's hour, day, month and year from the clock, and a random
    pressure that decides the sky."""
    lhour = c_div(current_time - 650336715, c_div(C.PULSE_TICK, C.PULSE_PER_SECOND))
    t.hour = c_mod(lhour, 24)
    lday = c_div(lhour, 24)
    t.day = c_mod(lday, 35)
    lmonth = c_div(lday, 35)
    t.month = c_mod(lmonth, 17)
    t.year = c_div(lmonth, 17)

    if t.hour < 5:
        w.sunlight = C.SUN_DARK
    elif t.hour < 6:
        w.sunlight = C.SUN_RISE
    elif t.hour < 19:
        w.sunlight = C.SUN_LIGHT
    elif t.hour < 20:
        w.sunlight = C.SUN_SET
    else:
        w.sunlight = C.SUN_DARK

    w.change = 0
    w.mmhg = 960
    w.mmhg += number_range(1, 50) if 7 <= t.month <= 12 else number_range(1, 80)
    if w.mmhg <= 980:
        w.sky = C.SKY_LIGHTNING
    elif w.mmhg <= 1000:
        w.sky = C.SKY_RAINING
    elif w.mmhg <= 1020:
        w.sky = C.SKY_CLOUDY
    else:
        w.sky = C.SKY_CLOUDLESS


# C: db.c boot_db [partial]
def boot_db(area_dir: Path, current_time: int | None = None, environ: dict | None = None) -> Game:
    """Boot the world from area_dir (the directory holding area.lst), as the C game does from its area/.

    [partial]: bans and songs aren't loaded, and a board with notes raises NotPorted (load_boards). The skill
    numbers (the gsn globals) are charm.world.lookup.GSN, made from skill_table."""
    now = int(time.time()) if current_time is None else current_time  # clock: boot_db's current_time
    log.clock = lambda: now
    init_mm(environ, log.log_string)
    time_info, weather_info = TimeInfo(), WeatherInfo()
    set_time_and_weather(time_info, weather_info, now)

    world = load_world(Path(area_dir))
    for line in world.log_lines():
        log.log_string(line)
    if world.fatal is not None:
        raise BootFailed(str(world.fatal))

    game = Game(build_index(world), now, time_info=time_info, weather_info=weather_info, area_dir=Path(area_dir))
    game_module.current = game
    if any(not m.new_format for m in game.index.mobs.values()) or any(
            not o.new_format for o in game.index.objs.values()):
        raise NotPorted("db2.c convert_objects: old-format prototypes")
    area_update(game)
    load_boards(game)
    return game
