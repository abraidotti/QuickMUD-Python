"""update_handler: the game's clockwork, run once a pulse (a quarter of a second).

[partial], as #28 decided: the pulse counters are the C's exactly, and area_update, song_update (music.c) and
violence_update run on their pulses. The other updates aren't ported and don't run. That's the one place the game
knowingly differs from the C: a running Python world stops matching the C's after the first mobile pulse. The
game logs what isn't running at boot (NOT_RUNNING), and each has a LATER line below, so port status lists them.

CHARM_UPDATES names the updates that run, in both games (#74): area, song, mobile, violence, weather, char, obj and
aggr, comma-separated, or all. Unset, everything runs (everything ported, here).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/update.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.entities.resets import area_update
from charm.net.wiznet import wiznet

# LATER: mobile_update isn't ported and doesn't run (#28): mobs don't move, scavenge or run specials
# LATER: weather_update, char_update and obj_update aren't ported and don't run (#28): no ticks, idling or decay
# LATER: aggr_update isn't ported and doesn't run (#28): aggressive mobs don't attack
NOT_RUNNING = ("mobile_update", "weather_update", "char_update", "obj_update", "aggr_update")

UPDATES = ("area", "song", "mobile", "violence", "weather", "char", "obj", "aggr")  # CHARM_UPDATES's names
PORTED = frozenset({"area", "song", "violence"})


def updates_named(value: str | None) -> frozenset[str]:
    """The updates CHARM_UPDATES names, as update.c's update_runs reads it: None (unset) is all of them."""
    from charm.core.log import bug
    from charm.core.strings import str_cmp

    if value is None:
        return frozenset(UPDATES)
    on: set[str] = set()
    for name in value[:C.MAX_INPUT_LENGTH - 1].split(","):
        if name == "":
            continue  # strtok skips empty fields
        if str_cmp(name, "all"):
            on.update(UPDATES)
            continue
        found = next((u for u in UPDATES if str_cmp(name, u)), None)
        if found is None:
            bug("CHARM_UPDATES: no update called that", 0)
        else:
            on.add(found)
    return frozenset(on)


# C: update.c update_handler [partial]
def update_handler(game) -> None:
    from charm.systems.fight import violence_update
    from charm.systems.music import song_update

    on = game.updates
    game.pulse_area -= 1
    if game.pulse_area <= 0:
        game.pulse_area = C.PULSE_AREA
        if "area" in on:
            area_update(game)

    game.pulse_music -= 1
    if game.pulse_music <= 0:
        game.pulse_music = C.PULSE_MUSIC
        if "song" in on:
            song_update(game)

    game.pulse_mobile -= 1
    if game.pulse_mobile <= 0:
        game.pulse_mobile = C.PULSE_MOBILE  # mobile_update: not running

    game.pulse_violence -= 1
    if game.pulse_violence <= 0:
        game.pulse_violence = C.PULSE_VIOLENCE
        if "violence" in on:
            violence_update(game)

    game.pulse_point -= 1
    if game.pulse_point <= 0:
        wiznet(game, "TICK!", None, None, C.WIZ_TICKS, 0, 0)
        game.pulse_point = C.PULSE_TICK  # weather_update, char_update, obj_update: not running

    # aggr_update: not running


# C: update.c gain_condition
def gain_condition(ch, i_cond: int, value: int) -> None:
    from charm.net.output import send_to_char

    if value == 0 or ch.is_npc or ch.level >= C.LEVEL_IMMORTAL:
        return
    condition = ch.pcdata.condition[i_cond]
    if condition == -1:
        return
    ch.pcdata.condition[i_cond] = max(0, min(condition + value, 48))  # URANGE(0, condition + value, 48)
    if ch.pcdata.condition[i_cond] == 0:
        if i_cond == C.COND_HUNGER:
            send_to_char("You are hungry.\n\r", ch)
        elif i_cond == C.COND_THIRST:
            send_to_char("You are thirsty.\n\r", ch)
        elif i_cond == C.COND_DRUNK and condition != 0:
            send_to_char("You are sober.\n\r", ch)


# C: update.c advance_level
def advance_level(ch, hide: bool) -> None:
    """A level's gains: the title, then hit points, mana, moves (three random draws, in that order) and practices.
    do_advance calls it with hide set; gain_exp without, to tell the player."""
    from charm.commands.info import set_title
    from charm.core.cint import c_div, sh_int
    from charm.core.rng import number_range
    from charm.data.attributes import CON_APP, WIS_APP
    from charm.data.classes import CLASS_TABLE, TITLE_TABLE
    from charm.entities import game as game_module
    from charm.entities.handler import get_curr_stat
    from charm.net.output import send_to_char

    ch.pcdata.last_level = c_div(ch.played + int(game_module.current.current_time - ch.logon), 3600)
    set_title(ch, "the %s" % TITLE_TABLE[ch.class_][ch.level][1 if ch.sex == C.SEX_FEMALE else 0])
    cls = CLASS_TABLE[ch.class_]
    add_hp = CON_APP[get_curr_stat(ch, C.STAT_CON)].hitp + number_range(cls.hp_min, cls.hp_max)
    add_mana = number_range(2, c_div(2 * get_curr_stat(ch, C.STAT_INT) + get_curr_stat(ch, C.STAT_WIS), 5))
    if not cls.fMana:
        add_mana = c_div(add_mana, 2)
    add_move = number_range(1, c_div(get_curr_stat(ch, C.STAT_CON) + get_curr_stat(ch, C.STAT_DEX), 6))
    add_prac = WIS_APP[get_curr_stat(ch, C.STAT_WIS)].practice
    add_hp = max(2, c_div(add_hp * 9, 10))
    add_mana = max(2, c_div(add_mana * 9, 10))
    add_move = max(6, c_div(add_move * 9, 10))
    ch.max_hit = sh_int(ch.max_hit + add_hp)
    ch.max_mana = sh_int(ch.max_mana + add_mana)
    ch.max_move = sh_int(ch.max_move + add_move)
    ch.practice = sh_int(ch.practice + add_prac)
    ch.train = sh_int(ch.train + 1)
    ch.pcdata.perm_hit = sh_int(ch.pcdata.perm_hit + add_hp)
    ch.pcdata.perm_mana = sh_int(ch.pcdata.perm_mana + add_mana)
    ch.pcdata.perm_move = sh_int(ch.pcdata.perm_move + add_move)
    if not hide:
        send_to_char("You gain %d hit point%s, %d mana, %d move, and %d practice%s.\n\r"
                     % (add_hp, "" if add_hp == 1 else "s", add_mana, add_move, add_prac,
                        "" if add_prac == 1 else "s"), ch)


# C: update.c gain_exp
def gain_exp(ch, gain: int) -> None:
    from charm.core.cint import sh_int
    from charm.core.log import log_string
    from charm.entities import game as game_module
    from charm.net.output import send_to_char
    from charm.persist.player import save_char_obj
    from charm.systems.skills import exp_per_level

    if ch.is_npc or ch.level >= C.LEVEL_HERO:
        return
    ch.exp = max(exp_per_level(ch, ch.pcdata.points), ch.exp + gain)
    while ch.level < C.LEVEL_HERO and ch.exp >= exp_per_level(ch, ch.pcdata.points) * (ch.level + 1):
        send_to_char("{GYou raise a level!!  {x", ch)
        ch.level = sh_int(ch.level + 1)
        log_string("%s gained level %d" % (ch.name, ch.level))
        wiznet(game_module.current, "$N has attained level %d!" % ch.level, ch, None, C.WIZ_LEVELS, 0, 0)
        advance_level(ch, False)
        save_char_obj(game_module.current, ch)
