"""fight.c, the parts outside a fight that other code reaches: stop_fighting and update_pos.

violence_update and the rest of combat aren't ported (#28); quitting and extract_char reach these.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/fight.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C


# C: fight.c stop_fighting
def stop_fighting(game, ch, f_both: bool) -> None:
    for fch in game.char_list:
        if fch is ch or (f_both and fch.fighting is ch):
            fch.fighting = None
            fch.position = fch.default_pos if fch.is_npc else C.POS_STANDING
            update_pos(fch)


# C: fight.c update_pos
def update_pos(victim) -> None:
    if victim.hit > 0:
        if victim.position <= C.POS_STUNNED:
            victim.position = C.POS_STANDING
        return
    if victim.is_npc and victim.hit < 1:
        victim.position = C.POS_DEAD
        return
    if victim.hit <= -11:
        victim.position = C.POS_DEAD
        return
    if victim.hit <= -6:
        victim.position = C.POS_MORTAL
    elif victim.hit <= -3:
        victim.position = C.POS_INCAP
    else:
        victim.position = C.POS_STUNNED
