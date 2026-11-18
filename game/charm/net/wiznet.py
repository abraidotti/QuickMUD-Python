"""wiznet: send a line to every immortal playing who has that wiznet channel on.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_wiz.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C


# C: act_wiz.c wiznet
def wiznet(game, string: str, ch, obj, flag: int, flag_skip: int, min_level: int) -> None:
    from charm.entities.handler import get_trust, is_immortal
    from charm.net.act import act_new
    from charm.net.output import send_to_char

    for d in list(game.descriptor_list):
        to = d.character
        if (d.connected == C.CON_PLAYING and is_immortal(to) and to.wiznet & C.WIZ_ON
                and (not flag or to.wiznet & flag) and (not flag_skip or not to.wiznet & flag_skip)
                and get_trust(to) >= min_level and to is not ch):
            send_to_char("{Z--> " if to.wiznet & C.WIZ_PREFIX else "{Z", to)
            act_new(string, to, obj, ch, C.TO_CHAR, C.POS_DEAD)
            send_to_char("{x", to)
