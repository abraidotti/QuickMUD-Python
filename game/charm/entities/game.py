"""The game's run-time state: the prototypes, every character and object, the clock and the weather.

The C keeps these as globals (char_list, object_list, time_info, weather_info, mobile_count, ...). Here they're one
Game, passed to the functions that use them, so a test can boot a world without touching another.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/merc.h. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from charm.entities.things import Char, Obj
from charm.world.index import Index


@dataclass
class TimeInfo:
    """time_info_data."""

    hour: int = 0
    day: int = 0
    month: int = 0
    year: int = 0


@dataclass
class WeatherInfo:
    """weather_data."""

    mmhg: int = 0
    change: int = 0
    sky: int = 0
    sunlight: int = 0


@dataclass(eq=False)
class Game:
    index: Index
    current_time: int
    char_list: list[Char] = field(default_factory=list)  # head first, as the C's char_list
    object_list: list[Obj] = field(default_factory=list)  # head first
    time_info: TimeInfo = field(default_factory=TimeInfo)
    weather_info: WeatherInfo = field(default_factory=WeatherInfo)
    mobile_count: int = 0
    last_mob_id: int = 0
