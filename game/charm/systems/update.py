"""update_handler: the game's clockwork, run once a pulse (a quarter of a second).

[partial], as #28 decided: the pulse counters are the C's exactly, and area_update runs on its pulse. The other
updates aren't ported and don't run. That's the one place the spike's game knowingly differs from the C: a running
Python world stops matching the C's after the first mobile pulse. The game logs what isn't running at boot
(NOT_RUNNING), and each has a LATER line below, so port status lists them.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/update.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.entities.resets import area_update
from charm.net.wiznet import wiznet

# LATER: song_update (music.c) isn't ported and doesn't run (#28)
# LATER: mobile_update isn't ported and doesn't run (#28): mobs don't move, scavenge or run specials
# LATER: violence_update (fight.c) isn't ported and doesn't run (#28)
# LATER: weather_update, char_update and obj_update aren't ported and don't run (#28): no ticks, idling or decay
# LATER: aggr_update isn't ported and doesn't run (#28): aggressive mobs don't attack
NOT_RUNNING = ("song_update", "mobile_update", "violence_update", "weather_update", "char_update", "obj_update",
               "aggr_update")


# C: update.c update_handler [partial]
def update_handler(game) -> None:
    game.pulse_area -= 1
    if game.pulse_area <= 0:
        game.pulse_area = C.PULSE_AREA
        area_update(game)

    game.pulse_music -= 1
    if game.pulse_music <= 0:
        game.pulse_music = C.PULSE_MUSIC  # song_update: not running

    game.pulse_mobile -= 1
    if game.pulse_mobile <= 0:
        game.pulse_mobile = C.PULSE_MOBILE  # mobile_update: not running

    game.pulse_violence -= 1
    if game.pulse_violence <= 0:
        game.pulse_violence = C.PULSE_VIOLENCE  # violence_update: not running

    game.pulse_point -= 1
    if game.pulse_point <= 0:
        wiznet(game, "TICK!", None, None, C.WIZ_TICKS, 0, 0)
        game.pulse_point = C.PULSE_TICK  # weather_update, char_update, obj_update: not running

    # aggr_update: not running


# C: update.c gain_exp [partial]
def gain_exp(ch, gain: int) -> None:
    """[partial]: gaining a level (advance_level) raises NotPorted."""
    from charm.core.errors import NotPorted
    from charm.systems.skills import exp_per_level

    if ch.is_npc or ch.level >= C.LEVEL_HERO:
        return
    ch.exp = max(exp_per_level(ch, ch.pcdata.points), ch.exp + gain)
    if ch.level < C.LEVEL_HERO and ch.exp >= exp_per_level(ch, ch.pcdata.points) * (ch.level + 1):
        raise NotPorted("update.c gain_exp: raising a level (advance_level)")
