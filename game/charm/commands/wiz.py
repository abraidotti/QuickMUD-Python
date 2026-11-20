"""Immortal commands, act_wiz.c. So far: do_outfit, and the ones for looking and moving about: goto, at, transfer,
violate, stat (rooms, objects, mobs), vnum, mfind, ofind, owhere, mwhere, slookup, sockets, the echoes, smote,
bamfin and bamfout, invis, incognito, holylight, prefix and wiznet. The ones that change things come in P3's last
PR.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_wiz.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import is_number, one_argument
from charm.core.cint import c_div, int32
from charm.core.errors import CWouldCrash
from charm.core.strings import atoi, smash_tilde, str_cmp, str_prefix, upper
from charm.data import constants as C
from charm.data.items import WEAPON_TABLE
from charm.entities import game as game_module
from charm.entities.create import create_object
from charm.entities.handler import (
    act_bit_name, affect_bit_name, affect_loc_name, can_see, can_see_obj, can_see_room, char_from_room,
    char_to_room, comm_bit_name, cont_bit_name, equip_char, extra_bit_name, form_bit_name, get_ac, get_age,
    get_carry_weight, get_char_world, get_curr_stat, get_damroll, get_eq_char, get_hitroll, get_obj_number,
    get_obj_weight, get_obj_world, get_true_weight, get_trust, imm_bit_name, is_name, is_room_owner, item_name,
    obj_to_char, off_bit_name, part_bit_name, pers, room_is_private, wear_bit_name, weapon_bit_name, wiznet_lookup)
from charm.entities.things import add_buf, new_buf
from charm.net.act import act
from charm.net.output import page_to_char, send_to_char
from charm.world.lookup import GSN

# act_wiz.c functions named like commands that the command table doesn't list: stat's and vnum's parts.
NOT_COMMANDS = ("do_rstat", "do_ostat", "do_mstat", "do_mfind", "do_ofind", "do_slookup")


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


# -- wiznet --------------------------------------------------------------------------------------------------------

# C: act_wiz.c do_wiznet
def do_wiznet(ch, argument: str) -> None:
    from charm.data.characters import WIZNET_TABLE

    if argument == "":
        if ch.wiznet & C.WIZ_ON:
            send_to_char("Signing off of Wiznet.\n\r", ch)
            ch.wiznet &= ~C.WIZ_ON
        else:
            send_to_char("Welcome to Wiznet!\n\r", ch)
            ch.wiznet |= C.WIZ_ON
        return
    if str_prefix(argument, "on"):
        send_to_char("Welcome to Wiznet!\n\r", ch)
        ch.wiznet |= C.WIZ_ON
        return
    if str_prefix(argument, "off"):
        send_to_char("Signing off of Wiznet.\n\r", ch)
        ch.wiznet &= ~C.WIZ_ON
        return
    if str_prefix(argument, "status"):  # "show wiznet status"
        buf = "" if ch.wiznet & C.WIZ_ON else "off "
        buf += "".join(w.name + " " for w in WIZNET_TABLE if ch.wiznet & w.flag)
        send_to_char("Wiznet status:\n\r", ch)
        send_to_char(buf + "\n\r", ch)
        return
    if str_prefix(argument, "show"):  # "list of all wiznet options"
        buf = "".join(w.name + " " for w in WIZNET_TABLE if w.level <= get_trust(ch))
        send_to_char("Wiznet options available to you are:\n\r", ch)
        send_to_char(buf + "\n\r", ch)
        return
    flag = wiznet_lookup(argument)
    if flag == -1 or get_trust(ch) < WIZNET_TABLE[flag].level:
        send_to_char("No such option.\n\r", ch)
        return
    w = WIZNET_TABLE[flag]
    if ch.wiznet & w.flag:
        send_to_char("You will no longer see %s on wiznet.\n\r" % w.name, ch)
        ch.wiznet &= ~w.flag
    else:
        send_to_char("You will now see %s on wiznet.\n\r" % w.name, ch)
        ch.wiznet |= w.flag


# -- emotes and echoes ---------------------------------------------------------------------------------------------

# C: act_wiz.c do_smote
def do_smote(ch, argument: str) -> None:
    """An emote that must include your own name; each player sees their name turned into "you"."""
    from charm.commands.comm import name_to_you

    matches = 0  # sic: once, not for each player, as in do_pmote (#54)
    if not ch.is_npc and ch.comm & C.COMM_NOEMOTE:
        send_to_char("You can't show your emotions.\n\r", ch)
        return
    if argument == "":
        send_to_char("Emote what?\n\r", ch)
        return
    if ch.name not in argument:
        send_to_char("You must include your name in an smote.\n\r", ch)
        return
    send_to_char(argument, ch)
    send_to_char("\n\r", ch)
    for vch in list(ch.in_room.people):
        if vch.desc is None or vch is ch:
            continue
        at = argument.find(vch.name)
        if at < 0:
            send_to_char(argument, vch)
            send_to_char("\n\r", vch)
            continue
        temp, matches = name_to_you(argument, at, vch.name, matches)
        send_to_char(temp, vch)
        send_to_char("\n\r", vch)


def _bamf(ch, argument: str, which: str) -> None:
    if ch.is_npc:
        return
    argument = smash_tilde(argument)
    field = "bamfin" if which == "poofin" else "bamfout"
    if argument == "":
        send_to_char("Your %s is %s\n\r" % (which, getattr(ch.pcdata, field)), ch)
        return
    if ch.name not in argument:
        send_to_char("You must include your name.\n\r", ch)
        return
    setattr(ch.pcdata, field, argument)
    send_to_char("Your %s is now %s\n\r" % (which, argument), ch)


# C: act_wiz.c do_bamfin
def do_bamfin(ch, argument: str) -> None:
    _bamf(ch, argument, "poofin")


# C: act_wiz.c do_bamfout
def do_bamfout(ch, argument: str) -> None:
    _bamf(ch, argument, "poofout")


def _echo(ch, argument: str, empty: str, tag: str, where) -> None:
    if argument == "":
        send_to_char(empty, ch)
        return
    for d in list(game_module.current.descriptor_list):
        if d.connected == C.CON_PLAYING and where(d.character):
            if get_trust(d.character) >= get_trust(ch):
                send_to_char(tag, d.character)
            send_to_char(argument, d.character)
            send_to_char("\n\r", d.character)


# C: act_wiz.c do_echo
def do_echo(ch, argument: str) -> None:
    _echo(ch, argument, "Global echo what?\n\r", "global> ", lambda vch: True)


# C: act_wiz.c do_recho
def do_recho(ch, argument: str) -> None:
    _echo(ch, argument, "Local echo what?\n\r", "local> ", lambda vch: vch.in_room is ch.in_room)


# C: act_wiz.c do_zecho
def do_zecho(ch, argument: str) -> None:
    _echo(ch, argument, "Zone echo what?\n\r", "zone> ",
          lambda vch: vch.in_room is not None and ch.in_room is not None and vch.in_room.area is ch.in_room.area)


# C: act_wiz.c do_pecho
def do_pecho(ch, argument: str) -> None:
    argument, arg = one_argument(argument)
    if argument == "" or arg == "":
        send_to_char("Personal echo what?\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg)
    if victim is None:
        send_to_char("Target not found.\n\r", ch)
        return
    if get_trust(victim) >= get_trust(ch) and get_trust(ch) != C.MAX_LEVEL:
        send_to_char("personal> ", victim)
    send_to_char(argument, victim)
    send_to_char("\n\r", victim)
    send_to_char("personal> ", ch)
    send_to_char(argument, ch)
    send_to_char("\n\r", ch)


# -- moving about --------------------------------------------------------------------------------------------------

# C: act_wiz.c find_location
def find_location(ch, arg: str):
    """A room by number, or the room of the character or object called arg."""
    game = game_module.current
    if is_number(arg):
        return game.index.get_room_index(atoi(arg))
    victim = get_char_world(game, ch, arg)
    if victim is not None:
        return victim.in_room
    obj = get_obj_world(ch, arg)
    if obj is not None:
        return obj.in_room
    return None


def _private(ch, location) -> bool:
    return not is_room_owner(ch, location) and room_is_private(location) and get_trust(ch) < C.MAX_LEVEL


# C: act_wiz.c do_transfer
def do_transfer(ch, argument: str) -> None:
    from charm.commands.info import do_look
    from charm.systems.fight import stop_fighting

    game = game_module.current
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "":
        send_to_char("Transfer whom (and where)?\n\r", ch)
        return
    if str_cmp(arg1, "all"):
        for d in list(game.descriptor_list):
            if (d.connected == C.CON_PLAYING and d.character is not ch and d.character.in_room is not None
                    and can_see(ch, d.character)):
                do_transfer(ch, "%s %s" % (d.character.name, arg2))
        return
    if arg2 == "":  # "Thanks to Grodyn for the optional location parameter."
        location = ch.in_room
    else:
        location = find_location(ch, arg2)
        if location is None:
            send_to_char("No such location.\n\r", ch)
            return
        if _private(ch, location):
            send_to_char("That room is private right now.\n\r", ch)
            return
    victim = get_char_world(game, ch, arg1)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.in_room is None:
        send_to_char("They are in limbo.\n\r", ch)
        return
    if victim.fighting is not None:
        stop_fighting(game, victim, True)
    act("$n disappears in a mushroom cloud.", victim, None, None, C.TO_ROOM)
    char_from_room(victim)
    char_to_room(victim, location)
    act("$n arrives from a puff of smoke.", victim, None, None, C.TO_ROOM)
    if ch is not victim:
        act("$n has transferred you.", ch, None, victim, C.TO_VICT)
    do_look(victim, "auto")
    send_to_char("Ok.\n\r", ch)


# C: act_wiz.c do_at
def do_at(ch, argument: str) -> None:
    from charm.commands.interp import interpret

    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        send_to_char("At where what?\n\r", ch)
        return
    location = find_location(ch, arg)
    if location is None:
        send_to_char("No such location.\n\r", ch)
        return
    if _private(ch, location):
        send_to_char("That room is private right now.\n\r", ch)
        return
    original, on = ch.in_room, ch.on
    char_from_room(ch)
    char_to_room(ch, location)
    interpret(ch, argument)
    # "See if 'ch' still exists before continuing! Handles 'at XXXX quit' case."
    if any(wch is ch for wch in game_module.current.char_list):
        char_from_room(ch)
        char_to_room(ch, original)
        ch.on = on


def _swirl(ch, location) -> None:
    """goto's and violate's: leave in a swirling mist (or the bamfout), arrive (or the bamfin), and look."""
    from charm.commands.info import do_look
    from charm.systems.fight import stop_fighting

    if ch.fighting is not None:
        stop_fighting(game_module.current, ch, True)
    for rch in list(ch.in_room.people):
        if get_trust(rch) >= ch.invis_level:
            if ch.pcdata is not None and ch.pcdata.bamfout:
                act("$t", ch, ch.pcdata.bamfout, rch, C.TO_VICT)
            else:
                act("$n leaves in a swirling mist.", ch, None, rch, C.TO_VICT)
    char_from_room(ch)
    char_to_room(ch, location)
    for rch in list(ch.in_room.people):
        if get_trust(rch) >= ch.invis_level:
            if ch.pcdata is not None and ch.pcdata.bamfin:
                act("$t", ch, ch.pcdata.bamfin, rch, C.TO_VICT)
            else:
                act("$n appears in a swirling mist.", ch, None, rch, C.TO_VICT)
    do_look(ch, "auto")


# C: act_wiz.c do_goto
def do_goto(ch, argument: str) -> None:
    if argument == "":
        send_to_char("Goto where?\n\r", ch)
        return
    location = find_location(ch, argument)
    if location is None:
        send_to_char("No such location.\n\r", ch)
        return
    count = len(location.people)
    if not is_room_owner(ch, location) and room_is_private(location) and (count > 1 or get_trust(ch) < C.MAX_LEVEL):
        send_to_char("That room is private right now.\n\r", ch)
        return
    _swirl(ch, location)


# C: act_wiz.c do_violate
def do_violate(ch, argument: str) -> None:
    """goto, into a private room."""
    if argument == "":
        send_to_char("Goto where?\n\r", ch)
        return
    location = find_location(ch, argument)
    if location is None:
        send_to_char("No such location.\n\r", ch)
        return
    if not room_is_private(location):
        send_to_char("That room isn't private, use goto.\n\r", ch)
        return
    _swirl(ch, location)


# -- stat ----------------------------------------------------------------------------------------------------------

# C: act_wiz.c do_stat
def do_stat(ch, argument: str) -> None:
    """"RT to replace the 3 stat commands"."""
    string, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:\n\r  stat <name>\n\r  stat obj <name>\n\r  stat mob <name>\n\r  stat room <number>\n\r", ch)
        return
    if str_cmp(arg, "room"):
        do_rstat(ch, string)
        return
    if str_cmp(arg, "obj"):
        do_ostat(ch, string)
        return
    if str_cmp(arg, "char") or str_cmp(arg, "mob"):
        do_mstat(ch, string)
        return
    # "do it the old way"
    if get_obj_world(ch, argument) is not None:
        do_ostat(ch, argument)
        return
    if get_char_world(game_module.current, ch, argument) is not None:
        do_mstat(ch, argument)
        return
    if find_location(ch, argument) is not None:
        do_rstat(ch, argument)
        return
    send_to_char("Nothing by that name found anywhere.\n\r", ch)


def _keywords(eds) -> str:
    """Each keyword, with a space between them (but not after the last)."""
    return " ".join(ed.keyword for ed in eds)


# C: act_wiz.c do_rstat
def do_rstat(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    location = ch.in_room if arg == "" else find_location(ch, arg)
    if location is None:
        send_to_char("No such location.\n\r", ch)
        return
    if (not is_room_owner(ch, location) and ch.in_room is not location and room_is_private(location)
            and get_trust(ch) < C.IMPLEMENTOR):
        send_to_char("That room is private right now.\n\r", ch)
        return
    send_to_char("Name: '%s'\n\rArea: '%s'\n\r" % (location.name, location.area.name), ch)
    send_to_char("Vnum: %d  Sector: %d  Light: %d  Healing: %d  Mana: %d\n\r"
                 % (location.vnum, location.sector_type, location.light, location.heal_rate, location.mana_rate), ch)
    send_to_char("Room flags: %d.\n\rDescription:\n\r%s" % (location.room_flags, location.description), ch)
    if location.extra_descr:
        send_to_char("Extra description keywords: '" + _keywords(location.extra_descr) + "'.\n\r", ch)
    send_to_char("Characters:", ch)
    for rch in location.people:
        if can_see(ch, rch):
            send_to_char(" " + one_argument(rch.name)[1], ch)
    send_to_char(".\n\rObjects:   ", ch)
    for obj in location.contents:
        send_to_char(" " + one_argument(obj.name)[1], ch)
    send_to_char(".\n\r", ch)
    for door in range(6):
        ex = location.exit[door]
        if ex is not None:
            send_to_char("Door: %d.  To: %d.  Key: %d.  Exit flags: %d.\n\rKeyword: '%s'.  Description: %s"
                         % (door, ex.to_room.vnum if ex.to_room is not None else -1, ex.key, ex.exit_info, ex.keyword,
                            ex.description if ex.description else "(none).\n\r"), ch)


def _skill_name(sn: int) -> str:
    """skill_table[sn].name for 0 <= sn < MAX_SKILL: the rows past the table are zeros, whose name send_to_char
    skips (NULL)."""
    from charm.data.skills import SKILL_TABLE

    return SKILL_TABLE[sn].name if sn < len(SKILL_TABLE) else ""


def _row(table, i: int, field: str, where: str):
    """table[i].field, where the C's table ends in a row of NULLs (printed "(null)") and has no bounds check."""
    if 0 <= i < len(table):
        return getattr(table[i], field)
    if i == len(table):
        return "(null)"
    raise CWouldCrash(f"act_wiz.c {where}: {i} is past the table")


_WEAPON_CLASSES = {C.WEAPON_EXOTIC: "exotic", C.WEAPON_SWORD: "sword", C.WEAPON_DAGGER: "dagger",
                   C.WEAPON_SPEAR: "spear/staff", C.WEAPON_MACE: "mace/club", C.WEAPON_AXE: "axe",
                   C.WEAPON_FLAIL: "flail", C.WEAPON_WHIP: "whip", C.WEAPON_POLEARM: "polearm"}


def _adds(paf, with_weapon: bool) -> str:
    """ostat's line for an affect's bits."""
    where = paf.where
    if where == C.TO_AFFECTS:
        return "Adds %s affect.\n" % affect_bit_name(paf.bitvector)  # sic: no \r (#68)
    if where == C.TO_WEAPON and with_weapon:
        return "Adds %s weapon flags.\n" % weapon_bit_name(paf.bitvector)  # sic: no \r (#68)
    if where == C.TO_OBJECT:
        return "Adds %s object flag.\n" % extra_bit_name(paf.bitvector)  # sic: no \r (#68)
    if where == C.TO_IMMUNE:
        return "Adds immunity to %s.\n" % imm_bit_name(paf.bitvector)  # sic: no \r (#68)
    if where == C.TO_RESIST:
        return "Adds resistance to %s.\n\r" % imm_bit_name(paf.bitvector)
    if where == C.TO_VULN:
        return "Adds vulnerability to %s.\n\r" % imm_bit_name(paf.bitvector)
    return "Unknown bit %d: %d\n\r" % (where, paf.bitvector)


# C: act_wiz.c do_ostat
def do_ostat(ch, argument: str) -> None:
    from charm.commands.obj import _liquid
    from charm.data.attacks import ATTACK_TABLE

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Stat what?\n\r", ch)
        return
    obj = get_obj_world(ch, argument)
    if obj is None:
        send_to_char("Nothing like that in hell, earth, or heaven.\n\r", ch)
        return
    p, v = obj.index, obj.value
    send_to_char("Name(s): %s\n\r" % obj.name, ch)
    send_to_char("Vnum: %d  Format: %s  Type: %s  Resets: %d\n\r"
                 % (p.vnum, "new" if p.new_format else "old", item_name(obj.item_type), p.reset_num), ch)
    send_to_char("Short description: %s\n\rLong description: %s\n\r" % (obj.short_descr, obj.description), ch)
    send_to_char("Wear bits: %s\n\rExtra bits: %s\n\r" % (wear_bit_name(obj.wear_flags),
                                                          extra_bit_name(obj.extra_flags)), ch)
    send_to_char("Number: %d/%d  Weight: %d/%d/%d (10th pounds)\n\r"
                 % (1, get_obj_number(obj), obj.weight, get_obj_weight(obj), get_true_weight(obj)), ch)
    send_to_char("Level: %d  Cost: %d  Condition: %d  Timer: %d\n\r" % (obj.level, obj.cost, obj.condition,
                                                                       obj.timer), ch)
    carried = ("(none)" if obj.carried_by is None else obj.carried_by.name if can_see(ch, obj.carried_by)
               else "someone")
    send_to_char("In room: %d  In object: %s  Carried by: %s  Wear_loc: %d\n\r"
                 % (obj.in_room.vnum if obj.in_room is not None else 0,
                    obj.in_obj.short_descr if obj.in_obj is not None else "(none)", carried, obj.wear_loc), ch)
    send_to_char("Values: %d %d %d %d %d\n\r" % tuple(v), ch)
    # "now give out vital statistics as per identify"
    t = obj.item_type
    if t in (C.ITEM_SCROLL, C.ITEM_POTION, C.ITEM_PILL):
        send_to_char("Level %d spells of:" % v[0], ch)
        for sn in v[1:5]:
            if 0 <= sn < C.MAX_SKILL:
                send_to_char(" '" + _skill_name(sn) + "'", ch)
        send_to_char(".\n\r", ch)
    elif t in (C.ITEM_WAND, C.ITEM_STAFF):
        send_to_char("Has %d(%d) charges of level %d" % (v[1], v[2], v[0]), ch)
        if 0 <= v[3] < C.MAX_SKILL:
            send_to_char(" '" + _skill_name(v[3]) + "'", ch)
        send_to_char(".\n\r", ch)
    elif t == C.ITEM_DRINK_CON:
        liq = _liquid(v[2], "do_ostat")
        send_to_char("It holds %s-colored %s.\n\r" % (liq.liq_color, liq.liq_name), ch)
    elif t == C.ITEM_WEAPON:
        send_to_char("Weapon type is %s\n\r" % _WEAPON_CLASSES.get(v[0], "unknown"), ch)
        if p.new_format:
            send_to_char("Damage is %dd%d (average %d)\n\r" % (v[1], v[2], c_div((1 + v[2]) * v[1], 2)), ch)
        else:
            send_to_char("Damage is %d to %d (average %d)\n\r" % (v[1], v[2], c_div(v[1] + v[2], 2)), ch)
        noun = _row(ATTACK_TABLE, v[3], "noun", "do_ostat") if 0 < v[3] < C.MAX_DAMAGE_MESSAGE else "undefined"
        send_to_char("Damage noun is %s.\n\r" % noun, ch)
        if v[4]:  # "weapon flags"
            send_to_char("Weapons flags: %s\n\r" % weapon_bit_name(v[4]), ch)
    elif t == C.ITEM_ARMOR:
        send_to_char("Armor class is %d pierce, %d bash, %d slash, and %d vs. magic\n\r" % tuple(v[:4]), ch)
    elif t == C.ITEM_CONTAINER:
        send_to_char("Capacity: %d#  Maximum weight: %d#  flags: %s\n\r" % (v[0], v[3], cont_bit_name(v[1])), ch)
        if v[4] != 100:
            send_to_char("Weight multiplier: %d%%\n\r" % v[4], ch)
    if obj.extra_descr or p.extra_descr:
        # sic: no space between the object's own keywords and its prototype's (#68)
        send_to_char("Extra description keywords: '" + _keywords(obj.extra_descr) + _keywords(p.extra_descr)
                     + "'\n\r", ch)
    for paf in obj.affected:
        send_to_char("Affects %s by %d, level %d" % (affect_loc_name(paf.location), paf.modifier, paf.level), ch)
        send_to_char(", %d hours.\n\r" % paf.duration if paf.duration > -1 else ".\n\r", ch)
        if paf.bitvector:
            send_to_char(_adds(paf, True), ch)
    if not obj.enchanted:
        for paf in p.affected:
            send_to_char("Affects %s by %d, level %d.\n\r" % (affect_loc_name(paf.location), paf.modifier,
                                                             paf.level), ch)
            if paf.bitvector:
                send_to_char(_adds(paf, False), ch)  # (this switch has no TO_WEAPON: "Unknown bit")


# C: act_wiz.c do_mstat
def do_mstat(ch, argument: str) -> None:
    from charm.data.attacks import ATTACK_TABLE
    from charm.data.characters import POSITION_TABLE, SEX_TABLE
    from charm.data.classes import CLASS_TABLE
    from charm.data.races import RACE_TABLE, SIZE_TABLE
    from charm.data.skills import SKILL_TABLE
    from charm.world.lookup import spec_name

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Stat whom?\n\r", ch)
        return
    victim = get_char_world(game, ch, argument)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    npc = victim.is_npc
    send_to_char("Name: %s\n\r" % victim.name, ch)
    send_to_char("Vnum: %d  Format: %s  Race: %s  Group: %d  Sex: %s  Room: %d\n\r"
                 % (victim.index.vnum if npc else 0, ("new" if victim.index.new_format else "old") if npc else "pc",
                    _row(RACE_TABLE, victim.race, "name", "do_mstat"), victim.group if npc else 0,
                    _row(SEX_TABLE, victim.sex, "name", "do_mstat"),
                    victim.in_room.vnum if victim.in_room is not None else 0), ch)
    if npc:
        send_to_char("Count: %d  Killed: %d\n\r" % (victim.index.count, victim.index.killed), ch)
    stats = []
    for s in (C.STAT_STR, C.STAT_INT, C.STAT_WIS, C.STAT_DEX, C.STAT_CON):
        stats += [victim.perm_stat[s], get_curr_stat(victim, s)]
    send_to_char("Str: %d(%d)  Int: %d(%d)  Wis: %d(%d)  Dex: %d(%d)  Con: %d(%d)\n\r" % tuple(stats), ch)
    # sic: Practices is 0 when ch, the one looking, is a mob, not when the victim is (#68)
    send_to_char("Hp: %d/%d  Mana: %d/%d  Move: %d/%d  Practices: %d\n\r"
                 % (victim.hit, victim.max_hit, victim.mana, victim.max_mana, victim.move, victim.max_move,
                    0 if ch.is_npc else victim.practice), ch)
    send_to_char("Lv: %d  Class: %s  Align: %d  Gold: %d  Silver: %d  Exp: %d\n\r"
                 % (victim.level, "mobile" if npc else CLASS_TABLE[victim.class_].name, victim.alignment,
                    victim.gold, victim.silver, victim.exp), ch)
    send_to_char("Armor: pierce: %d  bash: %d  slash: %d  magic: %d\n\r"
                 % (get_ac(victim, C.AC_PIERCE), get_ac(victim, C.AC_BASH), get_ac(victim, C.AC_SLASH),
                    get_ac(victim, C.AC_EXOTIC)), ch)
    send_to_char("Hit: %d  Dam: %d  Saves: %d  Size: %s  Position: %s  Wimpy: %d\n\r"
                 % (get_hitroll(victim), get_damroll(victim), victim.saving_throw,
                    _row(SIZE_TABLE, victim.size, "name", "do_mstat"),
                    _row(POSITION_TABLE, victim.position, "name", "do_mstat"), victim.wimpy), ch)
    if npc and victim.index.new_format:
        send_to_char("Damage: %dd%d  Message:  %s\n\r"
                     % (victim.damage[C.DICE_NUMBER], victim.damage[C.DICE_TYPE],
                        _row(ATTACK_TABLE, victim.dam_type, "noun", "do_mstat")), ch)
    send_to_char("Fighting: %s\n\r" % (victim.fighting.name if victim.fighting is not None else "(none)"), ch)
    if not npc:
        cond = victim.pcdata.condition
        send_to_char("Thirst: %d  Hunger: %d  Full: %d  Drunk: %d\n\r"
                     % (cond[C.COND_THIRST], cond[C.COND_HUNGER], cond[C.COND_FULL], cond[C.COND_DRUNK]), ch)
    send_to_char("Carry number: %d  Carry weight: %d\n\r" % (victim.carry_number, c_div(get_carry_weight(victim), 10)),
                 ch)
    if not npc:
        send_to_char("Age: %d  Played: %d  Last Level: %d  Timer: %d\n\r"
                     % (get_age(game, victim), c_div(int32(victim.played + game.current_time - victim.logon), 3600),
                        victim.pcdata.last_level, victim.timer), ch)
    send_to_char("Act: %s\n\r" % act_bit_name(victim.act), ch)
    if victim.comm:
        send_to_char("Comm: %s\n\r" % comm_bit_name(victim.comm), ch)
    if npc and victim.off_flags:
        send_to_char("Offense: %s\n\r" % off_bit_name(victim.off_flags), ch)
    if victim.imm_flags:
        send_to_char("Immune: %s\n\r" % imm_bit_name(victim.imm_flags), ch)
    if victim.res_flags:
        send_to_char("Resist: %s\n\r" % imm_bit_name(victim.res_flags), ch)
    if victim.vuln_flags:
        send_to_char("Vulnerable: %s\n\r" % imm_bit_name(victim.vuln_flags), ch)
    send_to_char("Form: %s\n\rParts: %s\n\r" % (form_bit_name(victim.form), part_bit_name(victim.parts)), ch)
    if victim.affected_by:
        send_to_char("Affected by %s\n\r" % affect_bit_name(victim.affected_by), ch)
    send_to_char("Master: %s  Leader: %s  Pet: %s\n\r"
                 % (victim.master.name if victim.master else "(none)", victim.leader.name if victim.leader else "(none)",
                    victim.pet.name if victim.pet else "(none)"), ch)
    if not npc:
        send_to_char("Security: %d.\n\r" % victim.pcdata.security, ch)  # "OLC"
    send_to_char("Short description: %s\n\rLong  description: %s"
                 % (victim.short_descr, victim.long_descr if victim.long_descr else "(none)\n\r"), ch)
    if npc and victim.spec_fun is not None:
        name = spec_name(victim.spec_fun)
        send_to_char("Mobile has special procedure %s.\n\r" % ("(null)" if name is None else name), ch)
    for paf in victim.affected:
        send_to_char("Spell: '%s' modifies %s by %d for %d hours with bits %s, level %d.\n\r"
                     % (SKILL_TABLE[paf.type].name, affect_loc_name(paf.location), paf.modifier, paf.duration,
                        affect_bit_name(paf.bitvector), paf.level), ch)


# -- finding things ------------------------------------------------------------------------------------------------

# C: act_wiz.c do_vnum
def do_vnum(ch, argument: str) -> None:
    """"ofind and mfind replaced with vnum, vnum skill also added"."""
    string, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:\n\r  vnum obj <name>\n\r  vnum mob <name>\n\r  vnum skill <skill or spell>\n\r", ch)
        return
    if str_cmp(arg, "obj"):
        do_ofind(ch, string)
        return
    if str_cmp(arg, "mob") or str_cmp(arg, "char"):
        do_mfind(ch, string)
        return
    if str_cmp(arg, "skill") or str_cmp(arg, "spell"):
        do_slookup(ch, string)
        return
    do_mfind(ch, argument)  # "do both"
    do_ofind(ch, argument)


def _find(ch, argument: str, empty: str, protos: dict, name_of, none: str) -> None:
    """mfind's and ofind's: every prototype whose names match, by vnum. (The C walks the vnums from 0 until it has
    seen every prototype, which is the same order.)"""
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char(empty, ch)
        return
    found = False
    for vnum in sorted(protos):
        p = protos[vnum]
        if is_name(argument, name_of(p)):
            found = True
            send_to_char("[%5d] %s\n\r" % (p.vnum, p.short_descr), ch)
    if not found:
        send_to_char(none, ch)


# C: act_wiz.c do_mfind
def do_mfind(ch, argument: str) -> None:
    _find(ch, argument, "Find whom?\n\r", game_module.current.index.mobs, lambda p: p.player_name,
          "No mobiles by that name.\n\r")


# C: act_wiz.c do_ofind
def do_ofind(ch, argument: str) -> None:
    _find(ch, argument, "Find what?\n\r", game_module.current.index.objs, lambda p: p.name,
          "No objects by that name.\n\r")


# C: act_wiz.c do_owhere
def do_owhere(ch, argument: str) -> None:
    buffer = new_buf()
    if argument == "":
        send_to_char("Find what?\n\r", ch)
        return
    found = False
    number = 0
    for obj in list(game_module.current.object_list):
        if not can_see_obj(ch, obj) or not is_name(argument, obj.name) or ch.level < obj.level:
            continue
        found = True
        number += 1
        in_obj = obj
        while in_obj.in_obj is not None:
            in_obj = in_obj.in_obj
        if (in_obj.carried_by is not None and can_see(ch, in_obj.carried_by)
                and in_obj.carried_by.in_room is not None):
            buf = "%3d) %s is carried by %s [Room %d]\n\r" % (number, obj.short_descr, pers(in_obj.carried_by, ch),
                                                              in_obj.carried_by.in_room.vnum)
        elif in_obj.in_room is not None and can_see_room(ch, in_obj.in_room):
            buf = "%3d) %s is in %s [Room %d]\n\r" % (number, obj.short_descr, in_obj.in_room.name,
                                                      in_obj.in_room.vnum)
        else:
            buf = "%3d) %s is somewhere\n\r" % (number, obj.short_descr)
        if len(buf) >= C.MAX_INPUT_LENGTH:
            raise CWouldCrash("act_wiz.c do_owhere: a line overflows buf[MAX_INPUT_LENGTH]")
        add_buf(buffer, upper(buf[:1]) + buf[1:])
        if number >= 200:  # max_found
            break
    if not found:
        send_to_char("Nothing like that in heaven or earth.\n\r", ch)
    else:
        page_to_char(buffer.string, ch)


# C: act_wiz.c do_mwhere
def do_mwhere(ch, argument: str) -> None:
    game = game_module.current
    count = 0
    buffer = new_buf()
    if argument == "":  # "show characters logged"
        for d in list(game.descriptor_list):
            victim = d.character
            if (victim is not None and d.connected == C.CON_PLAYING and victim.in_room is not None
                    and can_see(ch, victim) and can_see_room(ch, victim.in_room)):
                count += 1
                if d.original is not None:
                    add_buf(buffer, "%3d) %s (in the body of %s) is in %s [%d]\n\r"
                            % (count, d.original.name, victim.short_descr, victim.in_room.name, victim.in_room.vnum))
                else:
                    add_buf(buffer, "%3d) %s is in %s [%d]\n\r" % (count, victim.name, victim.in_room.name,
                                                                   victim.in_room.vnum))
        page_to_char(buffer.string, ch)
        return
    found = False
    for victim in list(game.char_list):
        if victim.in_room is not None and is_name(argument, victim.name):
            found = True
            count += 1
            add_buf(buffer, "%3d) [%5d] %-28s [%5d] %s\n\r"
                    % (count, victim.index.vnum if victim.is_npc else 0,
                       victim.short_descr if victim.is_npc else victim.name, victim.in_room.vnum, victim.in_room.name))
    if not found:
        act("You didn't find any $T.", ch, None, argument, C.TO_CHAR)
    else:
        page_to_char(buffer.string, ch)


# C: act_wiz.c do_slookup
def do_slookup(ch, argument: str) -> None:
    from charm.data.skills import SKILL_TABLE
    from charm.world.lookup import skill_lookup

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Lookup which skill or spell?\n\r", ch)
        return
    if str_cmp(arg, "all"):
        for sn, s in enumerate(SKILL_TABLE):  # (the C stops at the first row with no name: the end of the table)
            send_to_char("Sn: %3d  Slot: %3d  Skill/spell: '%s'\n\r" % (sn, s.slot, s.name), ch)
        return
    sn = skill_lookup(arg)
    if sn < 0:
        send_to_char("No such skill or spell.\n\r", ch)
        return
    send_to_char("Sn: %3d  Slot: %3d  Skill/spell: '%s'\n\r" % (sn, SKILL_TABLE[sn].slot, SKILL_TABLE[sn].name), ch)


# C: act_wiz.c do_sockets
def do_sockets(ch, argument: str) -> None:
    count = 0
    buf = ""
    _, arg = one_argument(argument)
    for d in list(game_module.current.descriptor_list):
        if d.character is not None and can_see(ch, d.character) and (
                arg == "" or is_name(arg, d.character.name) or (d.original is not None and is_name(arg, d.original.name))):
            count += 1
            buf += "[%3d %2d] %s@%s\n\r" % (d.fileno, d.connected,
                                             d.original.name if d.original is not None else d.character.name, d.host)
            if len(buf) >= 2 * C.MAX_STRING_LENGTH:
                raise CWouldCrash("act_wiz.c do_sockets: the list overflows buf[2 * MAX_STRING_LENGTH]")
    if count == 0:
        send_to_char("No one by that name is connected.\n\r", ch)
        return
    page_to_char(buf + "%d user%s\n\r" % (count, "" if count == 1 else "s"), ch)


# -- an immortal's own settings ------------------------------------------------------------------------------------

def _cloak(ch, argument: str, field: str, off_room: str, off_char: str, on_room: str, on_char: str,
           refusal: str) -> None:
    """invis's and incognito's: toggle at your own level, or set a level (2 to your trust)."""
    _, arg = one_argument(argument)  # "RT code for taking a level argument"
    if arg == "":  # "take the default path"
        if getattr(ch, field):
            setattr(ch, field, 0)
            act(off_room, ch, None, None, C.TO_ROOM)
            send_to_char(off_char, ch)
        else:
            setattr(ch, field, get_trust(ch))
            act(on_room, ch, None, None, C.TO_ROOM)
            send_to_char(on_char, ch)
        return
    level = atoi(arg)  # "do the level thing"
    if level < 2 or level > get_trust(ch):
        send_to_char(refusal, ch)
        return
    ch.reply = None
    setattr(ch, field, level)
    act(on_room, ch, None, None, C.TO_ROOM)
    send_to_char(on_char, ch)


# C: act_wiz.c do_invis
def do_invis(ch, argument: str) -> None:
    _cloak(ch, argument, "invis_level", "$n slowly fades into existence.", "You slowly fade back into existence.\n\r",
           "$n slowly fades into thin air.", "You slowly vanish into thin air.\n\r",
           "Invis level must be between 2 and your level.\n\r")


# C: act_wiz.c do_incognito
def do_incognito(ch, argument: str) -> None:
    _cloak(ch, argument, "incog_level", "$n is no longer cloaked.", "You are no longer cloaked.\n\r",
           "$n cloaks $s presence.", "You cloak your presence.\n\r",
           "Incog level must be between 2 and your level.\n\r")


# C: act_wiz.c do_holylight
def do_holylight(ch, argument: str) -> None:
    if ch.is_npc:
        return
    if ch.act & C.PLR_HOLYLIGHT:
        ch.act &= ~C.PLR_HOLYLIGHT
        send_to_char("Holy light mode off.\n\r", ch)
    else:
        ch.act |= C.PLR_HOLYLIGHT
        send_to_char("Holy light mode on.\n\r", ch)


# C: act_wiz.c do_prefi
def do_prefi(ch, argument: str) -> None:
    send_to_char("You cannot abbreviate the prefix command.\r\n", ch)  # sic: "\r\n" (#68)


# C: act_wiz.c do_prefix
def do_prefix(ch, argument: str) -> None:
    """"prefix command: it will put the string typed on each line typed"."""
    if argument == "":
        if ch.prefix == "":
            send_to_char("You have no prefix to clear.\r\n", ch)  # sic: "\r\n" (#68)
            return
        send_to_char("Prefix removed.\r\n", ch)
        ch.prefix = ""
        return
    # sic: the C writes "Prefix changed to ..." or "Prefix set to ..." into buf and never sends it (#68)
    buf = ("Prefix changed to %s.\r\n" if ch.prefix else "Prefix set to %s.\r\n") % argument  # format: sprintf
    if len(buf) >= C.MAX_INPUT_LENGTH:  # into buf[MAX_INPUT_LENGTH], with its NUL
        raise CWouldCrash("act_wiz.c do_prefix: the message overflows buf[MAX_INPUT_LENGTH]")
    ch.prefix = argument
