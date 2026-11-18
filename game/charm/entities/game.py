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
    # comm.c's: the connections (head first), and the loop's state
    descriptor_list: list = field(default_factory=list)
    merc_down: bool = False
    shutdown_signal: int = 0
    config: object | None = None  # charm.net.config.Config
    selector: object | None = None
    # update_handler's static counters; they start at 0, so every update is due on the first pulse
    pulse_area: int = 0
    pulse_music: int = 0
    pulse_mobile: int = 0
    pulse_violence: int = 0
    pulse_point: int = 0


# LATER: the C reads its globals from anywhere; a few functions that don't take a Game (room_is_dark, called from
# can_see) read this one instead. Decide where game state lives (plans/python-port.md) and drop it.
current: Game | None = None


def weather() -> WeatherInfo:
    """weather_info, the C global, for code that isn't passed a Game."""
    return current.weather_info if current is not None else WeatherInfo()
