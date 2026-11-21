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


@dataclass(eq=False)
class TimeInfo:
    """time_info_data."""

    hour: int = 0
    day: int = 0
    month: int = 0
    year: int = 0


@dataclass(eq=False)
class WeatherInfo:
    """weather_data."""

    mmhg: int = 0
    change: int = 0
    sky: int = 0
    sunlight: int = 0


def _song_table() -> list:
    from charm.systems.music import new_song_table

    return new_song_table()


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
    area_dir: object | None = None  # the directory the C runs in (area/); its paths are relative to it
    wizlock: bool = False
    newlock: bool = False
    log_all: bool = False  # interp.c's fLogAll: 'log all' logs every command
    target_name: str = ""  # magic.c's: the rest of a cast's line, for the spells that read more of it
    last_pc_id: int = 0
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
    mprog_call_level: int = 0  # mob_prog.c program_flow's static call_level
    save_number: int = 0  # update.c's: which connections char_update saves this tick
    # the updates update_handler runs: CHARM_UPDATES's names (charm.systems.update.updates_named); all by default
    updates: frozenset = frozenset(("area", "song", "mobile", "violence", "weather", "char", "obj", "aggr"))
    str_boot_time: str = ""  # comm.c's, ctime of the boot; main sets it (the scenario oracle doesn't, so it's "")
    max_on: int = 0  # act_info.c's, the most players do_count has seen on
    # board.c's: each board's notes (note_first, oldest first) and whether it needs saving (changed), and
    # last_note_stamp, which keeps notes' date stamps unique
    notes: list = field(default_factory=list)
    board_changed: list = field(default_factory=list)
    last_note_stamp: int = 0
    ban_list: list = field(default_factory=list)  # ban.c's, head first
    # music.c's song_table and channel_songs (charm.systems.music); the C's globals start at zero
    songs: list = field(default_factory=lambda: _song_table())
    channel_songs: list = field(default_factory=lambda: [0] * 11)  # MAX_GLOBAL + 1
    # special.c spec_mayor's statics: the path he's on, his place on it, and whether he's walking
    mayor_path: str | None = None
    mayor_pos: int = 0
    mayor_move: bool = False
    # db.c's top_* counters and the boot's string space (areafile Counts, copied at boot), which memory prints;
    # OLC's constructors raise them for fresh memory, not for what they take back off a free list (mem.c)
    top: object | None = None
    free_resets: int = 0  # reset_free
    free_exits: int = 0  # exit_free
    free_shops: int = 0  # shop_free
    # comm.c's port and control socket (do_copyover passes them on), and the re-exec copyover uses: None for
    # charm.commands.copyover.exec_game; the scenario player puts a stub here, as its C driver wraps execl
    port: int = 0
    control: object | None = None
    exec_game: object | None = None


# LATER: the C reads its globals from anywhere; a few functions that don't take a Game (room_is_dark, called from
# can_see) read this one instead. Decide where game state lives (plans/python-port.md) and drop it.
current: Game | None = None


def weather() -> WeatherInfo:
    """weather_info, the C global, for code that isn't passed a Game."""
    return current.weather_info if current is not None else WeatherInfo()


def c_path(game: Game, path: str):
    """A path as the C opens it, relative to the directory it runs in: c_path(game, PLAYER_DIR + "Bob")."""
    from pathlib import Path
    return Path(game.area_dir) / path
