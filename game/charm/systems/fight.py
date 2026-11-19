"""fight.c, the parts outside a fight that other code reaches: stop_fighting, update_pos and is_safe.

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


# C: fight.c is_safe
def is_safe(ch, victim) -> bool:
    from charm.entities.handler import is_affected, is_clan, is_immortal
    from charm.net.act import act
    from charm.net.output import send_to_char

    if victim.in_room is None or ch.in_room is None:
        return True
    if victim.fighting is ch or victim is ch:
        return False
    if is_immortal(ch) and ch.level > C.LEVEL_IMMORTAL:
        return False
    if victim.is_npc:
        # "killing mobiles"
        if victim.in_room.room_flags & C.ROOM_SAFE:
            send_to_char("Not in this room.\n\r", ch)
            return True
        if victim.index.shop is not None:
            send_to_char("The shopkeeper wouldn't like that.\n\r", ch)
            return True
        # "no killing healers, trainers, etc"
        if victim.act & (C.ACT_TRAIN | C.ACT_PRACTICE | C.ACT_IS_HEALER | C.ACT_IS_CHANGER):
            send_to_char("I don't think Mota would approve.\n\r", ch)
            return True
        if not ch.is_npc:
            if victim.act & C.ACT_PET:
                act("But $N looks so cute and cuddly...", ch, None, victim, C.TO_CHAR)
                return True
            if is_affected(victim, C.AFF_CHARM) and ch is not victim.master:
                send_to_char("You don't own that monster.\n\r", ch)
                return True
    elif ch.is_npc:
        # "killing players", "NPC doing the killing"
        if victim.in_room.room_flags & C.ROOM_SAFE:
            send_to_char("Not in this room.\n\r", ch)
            return True
        if is_affected(ch, C.AFF_CHARM) and ch.master is not None and ch.master.fighting is not victim:
            send_to_char("Players are your friends!\n\r", ch)
            return True
    else:
        # "player doing the killing"
        if not is_clan(ch):
            send_to_char("Join a clan if you want to kill players.\n\r", ch)
            return True
        if victim.act & (C.PLR_KILLER | C.PLR_THIEF):
            return False
        if not is_clan(victim):
            send_to_char("They aren't in a clan, leave them alone.\n\r", ch)
            return True
        if ch.level > victim.level + 8:
            send_to_char("Pick on someone your own size.\n\r", ch)
            return True
    return False
