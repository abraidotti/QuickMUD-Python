"""Immortal commands. So far do_outfit, which login gives a new character's equipment with.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_wiz.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C
from charm.data.items import WEAPON_TABLE
from charm.entities import game as game_module
from charm.entities.create import create_object
from charm.entities.handler import equip_char, get_eq_char, obj_to_char
from charm.net.output import send_to_char
from charm.world.lookup import GSN


# C: act_wiz.c do_outfit
def do_outfit(ch, argument: str) -> None:
    game = game_module.current
    ix = game.index
    if ch.level > 5 or ch.is_npc:
        send_to_char("Find it yourself!\n\r", ch)
        return

    def give(vnum: int, wear: int, free: bool = True) -> None:
        obj = create_object(game, ix.get_obj_index(vnum), 0)
        if free:
            obj.cost = 0
        obj_to_char(obj, ch)
        equip_char(ch, obj, wear)

    if get_eq_char(ch, C.WEAR_LIGHT) is None:
        give(C.OBJ_VNUM_SCHOOL_BANNER, C.WEAR_LIGHT)
    if get_eq_char(ch, C.WEAR_BODY) is None:
        give(C.OBJ_VNUM_SCHOOL_VEST, C.WEAR_BODY)
    if get_eq_char(ch, C.WEAR_WIELD) is None:  # "do the weapon thing"
        sn, vnum = 0, C.OBJ_VNUM_SCHOOL_SWORD  # "just in case!"
        for w in WEAPON_TABLE:
            if ch.pcdata.learned[sn] < ch.pcdata.learned[GSN[w.gsn]]:
                sn, vnum = GSN[w.gsn], w.vnum
        give(vnum, C.WEAR_WIELD, free=False)
    wield = get_eq_char(ch, C.WEAR_WIELD)
    if (wield is None or not wield.value[4] & C.WEAPON_TWO_HANDS) and get_eq_char(ch, C.WEAR_SHIELD) is None:
        give(C.OBJ_VNUM_SCHOOL_SHIELD, C.WEAR_SHIELD)
    send_to_char("You have been equipped by Mota.\n\r", ch)
