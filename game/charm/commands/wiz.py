"""Immortal commands: all of act_wiz.c but copyover, which P5 ports with OLC. Looking and moving about (goto, at,
transfer, violate, stat, vnum, the finds and wheres, sockets, the echoes, smote, poofs, invis, incognito, holylight,
prefix, wiznet); punishments (deny, disconnect, freeze, the no- commands, pardon, log, protect, snoop); switching;
making and unmaking (load, clone, purge, advance, trust, restore, peace); setting (set, string); force; the locks,
shutdown and reboot; and qmconfig.

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

# act_wiz.c functions named like commands that the command table doesn't list: the parts of stat, vnum, load and
# set.
NOT_COMMANDS = ("do_rstat", "do_ostat", "do_mstat", "do_mfind", "do_ofind", "do_slookup", "do_mload", "do_oload",
                "do_sset", "do_mset", "do_oset", "do_rset")


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


# -- punishments ---------------------------------------------------------------------------------------------------

def _wiznet(string: str, ch, obj, flag: int, flag_skip: int, min_level: int) -> None:
    from charm.net.wiznet import wiznet

    wiznet(game_module.current, string, ch, obj, flag, flag_skip, min_level)


def _trusted(ch, level: int) -> bool:
    """IS_TRUSTED."""
    return get_trust(ch) >= level


# C: act_wiz.c do_guild
def do_guild(ch, argument: str) -> None:
    from charm.data.clans import CLAN_TABLE
    from charm.persist.player import capitalize
    from charm.world.lookup import clan_lookup

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Syntax: guild <char> <cln name>\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("They aren't playing.\n\r", ch)
        return
    if str_prefix(arg2, "none"):
        send_to_char("They are now clanless.\n\r", ch)
        send_to_char("You are now a member of no clan!\n\r", victim)
        victim.clan = 0
        return
    clan = clan_lookup(arg2)
    if clan == 0:
        send_to_char("No such clan exists.\n\r", ch)
        return
    if CLAN_TABLE[clan].independent:
        send_to_char("They are now a %s.\n\r" % CLAN_TABLE[clan].name, ch)
        send_to_char("You are now a %s.\n\r" % CLAN_TABLE[clan].name, victim)
    else:
        send_to_char("They are now a member of clan %s.\n\r" % capitalize(CLAN_TABLE[clan].name), ch)
        # sic: the C builds the victim's "You are now a member of clan ..." and never sends it (#71)
    victim.clan = clan


def _silence(ch, argument: str, whom: str, not_npc: bool, bit: int, restored: tuple, revoked: tuple) -> None:
    """nochannels, noemote, noshout, notell: toggle a comm flag on someone of lower trust. restored and revoked
    are (the victim's message, the immortal's, the wiznet line's format)."""
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char(whom, ch)
        return
    victim = get_char_world(game_module.current, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if not_npc and victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return
    if get_trust(victim) >= get_trust(ch):
        send_to_char("You failed.\n\r", ch)
        return
    if victim.comm & bit:
        victim.comm &= ~bit
        to_victim, to_ch, line = restored
    else:
        victim.comm |= bit
        to_victim, to_ch, line = revoked
    send_to_char(to_victim, victim)
    send_to_char(to_ch, ch)
    _wiznet(line % victim.name, ch, None, C.WIZ_PENALTIES, C.WIZ_SECURE, 0)  # format: sprintf


# C: act_wiz.c do_nochannels
def do_nochannels(ch, argument: str) -> None:
    """"RT nochannels command, for those spammers"."""
    _silence(ch, argument, "Nochannel whom?", False, C.COMM_NOCHANNELS,  # sic: no "\n\r" (#71)
             ("The gods have restored your channel priviliges.\n\r", "NOCHANNELS removed.\n\r",
              "$N restores channels to %s"),
             ("The gods have revoked your channel priviliges.\n\r", "NOCHANNELS set.\n\r",
              "$N revokes %s's channels."))


# C: act_wiz.c do_noemote
def do_noemote(ch, argument: str) -> None:
    _silence(ch, argument, "Noemote whom?\n\r", False, C.COMM_NOEMOTE,
             ("You can emote again.\n\r", "NOEMOTE removed.\n\r", "$N restores emotes to %s."),
             ("You can't emote!\n\r", "NOEMOTE set.\n\r", "$N revokes %s's emotes."))


# C: act_wiz.c do_noshout
def do_noshout(ch, argument: str) -> None:
    _silence(ch, argument, "Noshout whom?\n\r", True, C.COMM_NOSHOUT,
             ("You can shout again.\n\r", "NOSHOUT removed.\n\r", "$N restores shouts to %s."),
             ("You can't shout!\n\r", "NOSHOUT set.\n\r", "$N revokes %s's shouts."))


# C: act_wiz.c do_notell
def do_notell(ch, argument: str) -> None:
    _silence(ch, argument, "Notell whom?", False, C.COMM_NOTELL,  # sic: no "\n\r" (#71)
             ("You can tell again.\n\r", "NOTELL removed.\n\r", "$N restores tells to %s."),
             ("You can't tell!\n\r", "NOTELL set.\n\r", "$N revokes %s's tells."))


def _player_below(ch, argument: str, whom: str):
    """deny's and freeze's victim: a player of lower trust, or None (and the refusal sent)."""
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char(whom, ch)
        return None
    victim = get_char_world(game_module.current, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return None
    if victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return None
    if get_trust(victim) >= get_trust(ch):
        send_to_char("You failed.\n\r", ch)
        return None
    return victim


# C: act_wiz.c do_deny
def do_deny(ch, argument: str) -> None:
    from charm.commands.comm import do_quit
    from charm.persist.player import save_char_obj
    from charm.systems.fight import stop_fighting

    game = game_module.current
    victim = _player_below(ch, argument, "Deny whom?\n\r")
    if victim is None:
        return
    victim.act |= C.PLR_DENY
    send_to_char("You are denied access!\n\r", victim)
    _wiznet("$N denies access to %s" % victim.name, ch, None, C.WIZ_PENALTIES, C.WIZ_SECURE, 0)
    send_to_char("OK.\n\r", ch)
    save_char_obj(game, victim)
    stop_fighting(game, victim, True)
    do_quit(victim, "")


# C: act_wiz.c do_freeze
def do_freeze(ch, argument: str) -> None:
    from charm.persist.player import save_char_obj

    victim = _player_below(ch, argument, "Freeze whom?\n\r")
    if victim is None:
        return
    if victim.act & C.PLR_FREEZE:
        victim.act &= ~C.PLR_FREEZE
        send_to_char("You can play again.\n\r", victim)
        send_to_char("FREEZE removed.\n\r", ch)
        _wiznet("$N thaws %s." % victim.name, ch, None, C.WIZ_PENALTIES, C.WIZ_SECURE, 0)
    else:
        victim.act |= C.PLR_FREEZE
        send_to_char("You can't do ANYthing!\n\r", victim)
        send_to_char("FREEZE set.\n\r", ch)
        _wiznet("$N puts %s in the deep freeze." % victim.name, ch, None, C.WIZ_PENALTIES, C.WIZ_SECURE, 0)
    save_char_obj(game_module.current, victim)


# C: act_wiz.c do_disconnect
def do_disconnect(ch, argument: str) -> None:
    from charm.core.log import bug
    from charm.net.server import close_socket

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Disconnect whom?\n\r", ch)
        return
    if is_number(arg):
        desc = atoi(arg)
        for d in list(game.descriptor_list):
            if d.fileno == desc:
                close_socket(d)
                send_to_char("Ok.\n\r", ch)
                return
    victim = get_char_world(game, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.desc is None:
        act("$N doesn't have a descriptor.", ch, None, victim, C.TO_CHAR)
        return
    for d in list(game.descriptor_list):
        if d is victim.desc:
            close_socket(d)
            send_to_char("Ok.\n\r", ch)
            return
    bug("Do_disconnect: desc not found.", 0)
    send_to_char("Descriptor not found!\n\r", ch)


# C: act_wiz.c do_pardon
def do_pardon(ch, argument: str) -> None:
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Syntax: pardon <character> <killer|thief>.\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return
    if str_cmp(arg2, "killer"):
        if victim.act & C.PLR_KILLER:
            victim.act &= ~C.PLR_KILLER
            send_to_char("Killer flag removed.\n\r", ch)
            send_to_char("You are no longer a KILLER.\n\r", victim)
        return
    if str_cmp(arg2, "thief"):
        if victim.act & C.PLR_THIEF:
            victim.act &= ~C.PLR_THIEF
            send_to_char("Thief flag removed.\n\r", ch)
            send_to_char("You are no longer a THIEF.\n\r", victim)
        return
    send_to_char("Syntax: pardon <character> <killer|thief>.\n\r", ch)


# C: act_wiz.c do_log
def do_log(ch, argument: str) -> None:
    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Log whom?\n\r", ch)
        return
    if str_cmp(arg, "all"):
        game.log_all = not game.log_all
        send_to_char("Log ALL on.\n\r" if game.log_all else "Log ALL off.\n\r", ch)
        return
    victim = get_char_world(game, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return
    # "No level check, gods can log anyone."
    if victim.act & C.PLR_LOG:
        victim.act &= ~C.PLR_LOG
        send_to_char("LOG removed.\n\r", ch)
    else:
        victim.act |= C.PLR_LOG
        send_to_char("LOG set.\n\r", ch)


# C: act_wiz.c do_protect
def do_protect(ch, argument: str) -> None:
    from charm.net.act import act_new

    if argument == "":
        send_to_char("Protect whom from snooping?\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, argument)
    if victim is None:
        send_to_char("You can't find them.\n\r", ch)
        return
    if victim.comm & C.COMM_SNOOP_PROOF:
        act_new("$N is no longer snoop-proof.", ch, None, victim, C.TO_CHAR, C.POS_DEAD)
        send_to_char("Your snoop-proofing was just removed.\n\r", victim)
        victim.comm &= ~C.COMM_SNOOP_PROOF
    else:
        act_new("$N is now snoop-proof.", ch, None, victim, C.TO_CHAR, C.POS_DEAD)
        send_to_char("You are now immune to snooping.\n\r", victim)
        victim.comm |= C.COMM_SNOOP_PROOF


# C: act_wiz.c do_peace
def do_peace(ch, argument: str) -> None:
    from charm.systems.fight import stop_fighting

    for rch in list(ch.in_room.people):
        if rch.fighting is not None:
            stop_fighting(game_module.current, rch, True)
        if rch.is_npc and rch.act & C.ACT_AGGRESSIVE:
            rch.act &= ~C.ACT_AGGRESSIVE
    send_to_char("Ok.\n\r", ch)


# C: act_wiz.c do_wizlock
def do_wizlock(ch, argument: str) -> None:
    game = game_module.current
    game.wizlock = not game.wizlock
    if game.wizlock:
        _wiznet("$N has wizlocked the game.", ch, None, 0, 0, 0)
        send_to_char("Game wizlocked.\n\r", ch)
    else:
        _wiznet("$N removes wizlock.", ch, None, 0, 0, 0)
        send_to_char("Game un-wizlocked.\n\r", ch)


# C: act_wiz.c do_newlock
def do_newlock(ch, argument: str) -> None:
    """"RT anti-newbie code"."""
    game = game_module.current
    game.newlock = not game.newlock
    if game.newlock:
        _wiznet("$N locks out new characters.", ch, None, 0, 0, 0)
        send_to_char("New characters have been locked out.\n\r", ch)
    else:
        _wiznet("$N allows new characters back in.", ch, None, 0, 0, 0)
        send_to_char("Newlock removed.\n\r", ch)


# -- shutting down -------------------------------------------------------------------------------------------------

# C: act_wiz.c do_reboo
def do_reboo(ch, argument: str) -> None:
    send_to_char("If you want to REBOOT, spell it out.\n\r", ch)


# C: act_wiz.c do_reboot
def do_reboot(ch, argument: str) -> None:
    from charm.net.server import shutdown_all

    if ch.invis_level < C.LEVEL_HERO:
        do_echo(ch, "Reboot by %s." % ch.name)
    shutdown_all(game_module.current, None)


# C: act_wiz.c do_shutdow
def do_shutdow(ch, argument: str) -> None:
    send_to_char("If you want to SHUTDOWN, spell it out.\n\r", ch)


# C: act_wiz.c do_shutdown
def do_shutdown(ch, argument: str) -> None:
    from charm.commands.info import append_file
    from charm.net.server import shutdown_all

    # Charm's fix for #6: buf is always filled (a wizinvis immortal's was left uninitialised), and only the echo
    # depends on visibility.
    buf = "Shutdown by %s." % ch.name
    append_file(ch, C.SHUTDOWN_FILE, buf)
    buf += "\n\r"
    if ch.invis_level < C.LEVEL_HERO:
        do_echo(ch, buf)
    shutdown_all(game_module.current, None)


# -- snooping and switching ----------------------------------------------------------------------------------------

def _private_from(ch, victim) -> bool:
    """snoop's, switch's and force's test: the victim is in a private room the immortal isn't in."""
    return (not is_room_owner(ch, victim.in_room) and ch.in_room is not victim.in_room
            and room_is_private(victim.in_room) and not _trusted(ch, C.IMPLEMENTOR))


# C: act_wiz.c do_snoop
def do_snoop(ch, argument: str) -> None:
    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Snoop whom?\n\r", ch)
        return
    victim = get_char_world(game, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.desc is None:
        send_to_char("No descriptor to snoop.\n\r", ch)
        return
    if victim is ch:
        send_to_char("Cancelling all snoops.\n\r", ch)
        _wiznet("$N stops being such a snoop.", ch, None, C.WIZ_SNOOPS, C.WIZ_SECURE, get_trust(ch))
        for d in game.descriptor_list:
            if d.snoop_by is ch.desc:
                d.snoop_by = None
        return
    if victim.desc.snoop_by is not None:
        send_to_char("Busy already.\n\r", ch)
        return
    if _private_from(ch, victim):
        send_to_char("That character is in a private room.\n\r", ch)
        return
    if get_trust(victim) >= get_trust(ch) or victim.comm & C.COMM_SNOOP_PROOF:
        send_to_char("You failed.\n\r", ch)
        return
    if ch.desc is not None:
        d = ch.desc.snoop_by
        while d is not None:
            if d.character is victim or d.original is victim:
                send_to_char("No snoop loops.\n\r", ch)
                return
            d = d.snoop_by
    victim.desc.snoop_by = ch.desc
    _wiznet("$N starts snooping on %s" % (victim.short_descr if ch.is_npc else victim.name), ch, None,
            C.WIZ_SNOOPS, C.WIZ_SECURE, get_trust(ch))
    send_to_char("Ok.\n\r", ch)


# C: act_wiz.c do_switch
def do_switch(ch, argument: str) -> None:
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Switch into whom?\n\r", ch)
        return
    if ch.desc is None:
        return
    if ch.desc.original is not None:
        send_to_char("You are already switched.\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim is ch:
        send_to_char("Ok.\n\r", ch)
        return
    if not victim.is_npc:
        send_to_char("You can only switch into mobiles.\n\r", ch)
        return
    if _private_from(ch, victim):
        send_to_char("That character is in a private room.\n\r", ch)
        return
    if victim.desc is not None:
        send_to_char("Character in use.\n\r", ch)
        return
    _wiznet("$N switches into %s" % victim.short_descr, ch, None, C.WIZ_SWITCHES, C.WIZ_SECURE, get_trust(ch))
    d = ch.desc
    d.character = victim
    d.original = ch
    victim.desc = d
    ch.desc = None
    # "change communications to match"
    if ch.prompt is not None:
        victim.prompt = ch.prompt
    victim.comm = ch.comm
    victim.lines = ch.lines
    send_to_char("Ok.\n\r", victim)


# C: act_wiz.c do_return
def do_return(ch, argument: str) -> None:
    if ch.desc is None:
        return
    if ch.desc.original is None:
        send_to_char("You aren't switched.\n\r", ch)
        return
    send_to_char("You return to your original body. Type replay to see any missed tells.\n\r", ch)
    if ch.prompt is not None:
        ch.prompt = None
    _wiznet("$N returns from %s." % ch.short_descr, ch.desc.original, None, C.WIZ_SWITCHES, C.WIZ_SECURE,
            get_trust(ch))
    d = ch.desc
    d.character = d.original
    d.original = None
    d.character.desc = d
    ch.desc = None


# -- making and unmaking -------------------------------------------------------------------------------------------

# C: act_wiz.c obj_check
def obj_check(ch, obj) -> bool:
    """"trust levels for load and clone"."""
    return (_trusted(ch, C.GOD)
            or (_trusted(ch, C.IMMORTAL) and obj.level <= 20 and obj.cost <= 1000)
            or (_trusted(ch, C.DEMI) and obj.level <= 10 and obj.cost <= 500)
            or (_trusted(ch, C.ANGEL) and obj.level <= 5 and obj.cost <= 250)
            or (_trusted(ch, C.AVATAR) and obj.level == 0 and obj.cost <= 100))


# C: act_wiz.c recursive_clone
def recursive_clone(ch, obj, clone) -> None:
    """"for clone, to insure that cloning goes many levels deep"."""
    from charm.entities.create import clone_object
    from charm.entities.handler import obj_to_obj

    for c_obj in list(obj.contains):
        if obj_check(ch, c_obj):
            t_obj = create_object(game_module.current, c_obj.index, 0)
            clone_object(c_obj, t_obj)
            obj_to_obj(t_obj, clone)
            recursive_clone(ch, c_obj, t_obj)


# C: act_wiz.c do_clone
def do_clone(ch, argument: str) -> None:
    """"command that is similar to load"."""
    from charm.entities.create import clone_mobile, clone_object, create_mobile
    from charm.entities.handler import get_char_room, get_obj_here, obj_to_room

    game = game_module.current
    rest, arg = one_argument(argument)
    if arg == "":
        send_to_char("Clone what?\n\r", ch)
        return
    if str_prefix(arg, "object"):
        mob, obj = None, get_obj_here(ch, rest)
        if obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
    elif str_prefix(arg, "mobile") or str_prefix(arg, "character"):
        obj, mob = None, get_char_room(ch, rest)
        if mob is None:
            send_to_char("You don't see that here.\n\r", ch)
            return
    else:  # "find both"
        mob = get_char_room(ch, argument)
        obj = get_obj_here(ch, argument)
        if mob is None and obj is None:
            send_to_char("You don't see that here.\n\r", ch)
            return

    if obj is not None:  # "clone an object"
        if not obj_check(ch, obj):
            send_to_char("Your powers are not great enough for such a task.\n\r", ch)
            return
        clone = create_object(game, obj.index, 0)
        clone_object(obj, clone)
        if obj.carried_by is not None:
            obj_to_char(clone, ch)
        else:
            obj_to_room(clone, ch.in_room)
        recursive_clone(ch, obj, clone)
        act("$n has created $p.", ch, clone, None, C.TO_ROOM)
        act("You clone $p.", ch, clone, None, C.TO_CHAR)
        _wiznet("$N clones $p.", ch, clone, C.WIZ_LOAD, C.WIZ_SECURE, get_trust(ch))
        return

    if not mob.is_npc:
        send_to_char("You can only clone mobiles.\n\r", ch)
        return
    if ((mob.level > 20 and not _trusted(ch, C.GOD)) or (mob.level > 10 and not _trusted(ch, C.IMMORTAL))
            or (mob.level > 5 and not _trusted(ch, C.DEMI)) or (mob.level > 0 and not _trusted(ch, C.ANGEL))
            or not _trusted(ch, C.AVATAR)):
        send_to_char("Your powers are not great enough for such a task.\n\r", ch)
        return
    clone = create_mobile(game, mob.index)
    clone_mobile(mob, clone)
    for obj in list(mob.carrying):
        if obj_check(ch, obj):
            new_obj = create_object(game, obj.index, 0)
            clone_object(obj, new_obj)
            recursive_clone(ch, obj, new_obj)
            obj_to_char(new_obj, clone)
            new_obj.wear_loc = obj.wear_loc  # sic: worn without equip_char, so its affects never apply (#71)
    char_to_room(clone, ch.in_room)
    act("$n has created $N.", ch, None, clone, C.TO_ROOM)
    act("You clone $N.", ch, None, clone, C.TO_CHAR)
    _wiznet("$N clones %s." % clone.short_descr, ch, None, C.WIZ_LOAD, C.WIZ_SECURE, get_trust(ch))


# C: act_wiz.c do_load
def do_load(ch, argument: str) -> None:
    """"RT to replace the two load commands"."""
    argument, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  load mob <vnum>\n\r", ch)
        send_to_char("  load obj <vnum> <level>\n\r", ch)
        return
    if str_cmp(arg, "mob") or str_cmp(arg, "char"):
        do_mload(ch, argument)
        return
    if str_cmp(arg, "obj"):
        do_oload(ch, argument)
        return
    do_load(ch, "")  # "echo syntax"


# C: act_wiz.c do_mload
def do_mload(ch, argument: str) -> None:
    from charm.entities.create import create_mobile

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "" or not is_number(arg):
        send_to_char("Syntax: load mob <vnum>.\n\r", ch)
        return
    index = game.index.get_mob_index(atoi(arg))
    if index is None:
        send_to_char("No mob has that vnum.\n\r", ch)
        return
    victim = create_mobile(game, index)
    char_to_room(victim, ch.in_room)
    act("$n has created $N!", ch, None, victim, C.TO_ROOM)
    _wiznet("$N loads %s." % victim.short_descr, ch, None, C.WIZ_LOAD, C.WIZ_SECURE, get_trust(ch))
    send_to_char("Ok.\n\r", ch)


# C: act_wiz.c do_oload
def do_oload(ch, argument: str) -> None:
    from charm.entities.handler import obj_to_room

    game = game_module.current
    argument, arg1 = one_argument(argument)
    _, arg2 = one_argument(argument)
    if arg1 == "" or not is_number(arg1):
        send_to_char("Syntax: load obj <vnum> <level>.\n\r", ch)
        return
    level = get_trust(ch)  # "default"
    if arg2 != "":  # "load with a level"
        if not is_number(arg2):
            send_to_char("Syntax: oload <vnum> <level>.\n\r", ch)
            return
        level = atoi(arg2)
        if level < 0 or level > get_trust(ch):
            send_to_char("Level must be be between 0 and your level.\n\r", ch)  # sic: "be be" (#71)
            return
    index = game.index.get_obj_index(atoi(arg1))
    if index is None:
        send_to_char("No object has that vnum.\n\r", ch)
        return
    obj = create_object(game, index, level)
    if obj.wear_flags & C.ITEM_TAKE:
        obj_to_char(obj, ch)
    else:
        obj_to_room(obj, ch.in_room)
    act("$n has created $p!", ch, obj, None, C.TO_ROOM)
    _wiznet("$N loads $p.", ch, obj, C.WIZ_LOAD, C.WIZ_SECURE, get_trust(ch))
    send_to_char("Ok.\n\r", ch)


# C: act_wiz.c do_purge
def do_purge(ch, argument: str) -> None:
    from charm.entities.handler import extract_char, extract_obj
    from charm.net.server import close_socket
    from charm.persist.player import save_char_obj

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":  # "'purge'"
        # extracting a mob takes no one else with it (only a player has a pet), so the C's next pointers hold
        for victim in list(ch.in_room.people):
            if victim.is_npc and not victim.act & C.ACT_NOPURGE and victim is not ch:  # "safety precaution"
                extract_char(game, victim, True)
        for obj in list(ch.in_room.contents):
            if not obj.extra_flags & C.ITEM_NOPURGE:
                extract_obj(game, obj)
        act("$n purges the room!", ch, None, None, C.TO_ROOM)
        send_to_char("Ok.\n\r", ch)
        return
    victim = get_char_world(game, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if not victim.is_npc:
        if ch is victim:
            send_to_char("Ho ho ho.\n\r", ch)
            return
        if get_trust(ch) <= get_trust(victim):
            send_to_char("Maybe that wasn't a good idea...\n\r", ch)
            send_to_char("%s tried to purge you!\n\r" % ch.name, victim)  # into buf[100]: names are short
            return
        act("$n disintegrates $N.", ch, None, victim, C.TO_NOTVICT)
        if victim.level > 1:
            save_char_obj(game, victim)
        d = victim.desc
        extract_char(game, victim, True)
        if d is not None:
            close_socket(d)
        return
    act("$n purges $N.", ch, None, victim, C.TO_NOTVICT)
    extract_char(game, victim, True)


# -- levels and healing --------------------------------------------------------------------------------------------

# C: act_wiz.c do_advance
def do_advance(ch, argument: str) -> None:
    from charm.persist.player import save_char_obj
    from charm.systems.skills import exp_per_level
    from charm.systems.update import advance_level

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "" or not is_number(arg2):
        send_to_char("Syntax: advance <char> <level>.\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("That player is not here.\n\r", ch)
        return
    if victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return
    level = atoi(arg2)
    if level < 1 or level > C.MAX_LEVEL:
        send_to_char("Level must be 1 to %d.\n\r" % C.MAX_LEVEL, ch)
        return
    if level > get_trust(ch):
        send_to_char("Limited to your trust level.\n\r", ch)
        return
    # "Lower level: Reset to level 1. Then raise again. Currently, an imp can lower another imp. -- Swiftest"
    if level <= victim.level:
        send_to_char("Lowering a player's level!\n\r", ch)
        send_to_char("**** OOOOHHHHHHHHHH  NNNNOOOO ****\n\r", victim)
        temp_prac = victim.practice
        victim.level = 1
        victim.exp = exp_per_level(victim, victim.pcdata.points)
        victim.max_hit = 10
        victim.max_mana = 100
        victim.max_move = 100
        victim.practice = 0
        victim.hit = victim.max_hit
        victim.mana = victim.max_mana
        victim.move = victim.max_move
        advance_level(victim, True)
        victim.practice = temp_prac
    else:
        send_to_char("Raising a player's level!\n\r", ch)
        send_to_char("**** OOOOHHHHHHHHHH  YYYYEEEESSS ****\n\r", victim)
    for _ in range(victim.level, level):
        victim.level += 1
        advance_level(victim, True)
    send_to_char("You are now level %d.\n\r" % victim.level, victim)
    victim.exp = int32(exp_per_level(victim, victim.pcdata.points) * max(1, victim.level))
    victim.trust = 0
    save_char_obj(game_module.current, victim)


# C: act_wiz.c do_trust
def do_trust(ch, argument: str) -> None:
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or arg2 == "" or not is_number(arg2):
        send_to_char("Syntax: trust <char> <level>.\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("That player is not here.\n\r", ch)
        return
    level = atoi(arg2)
    if level < 0 or level > C.MAX_LEVEL:
        send_to_char("Level must be 0 (reset) or 1 to %d.\n\r" % C.MAX_LEVEL, ch)
        return
    if level > get_trust(ch):
        send_to_char("Limited to your trust.\n\r", ch)
        return
    victim.trust = level  # sic: nothing is sent (#71)


def _restore(victim) -> None:
    from charm.entities.handler import affect_strip
    from charm.systems.fight import update_pos

    for gsn in ("gsn_plague", "gsn_poison", "gsn_blindness", "gsn_sleep", "gsn_curse"):
        affect_strip(victim, GSN[gsn])
    victim.hit = victim.max_hit
    victim.mana = victim.max_mana
    victim.move = victim.max_move
    update_pos(victim)


# C: act_wiz.c do_restore
def do_restore(ch, argument: str) -> None:
    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "" or str_cmp(arg, "room"):  # "cure room"
        for vch in list(ch.in_room.people):
            _restore(vch)
            act("$n has restored you.", ch, None, vch, C.TO_VICT)
        _wiznet("$N restored room %d." % ch.in_room.vnum, ch, None, C.WIZ_RESTORE, C.WIZ_SECURE, get_trust(ch))
        send_to_char("Room restored.\n\r", ch)
        return
    if get_trust(ch) >= C.MAX_LEVEL - 1 and str_cmp(arg, "all"):  # "cure all"
        for d in list(game.descriptor_list):
            victim = d.character
            if victim is None or victim.is_npc:
                continue
            _restore(victim)
            if victim.in_room is not None:
                act("$n has restored you.", ch, None, victim, C.TO_VICT)
        send_to_char("All active players restored.\n\r", ch)
        return
    victim = get_char_world(game, ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    _restore(victim)
    act("$n has restored you.", ch, None, victim, C.TO_VICT)
    _wiznet("$N restored %s" % (victim.short_descr if victim.is_npc else victim.name), ch, None, C.WIZ_RESTORE,
            C.WIZ_SECURE, get_trust(ch))
    send_to_char("Ok.\n\r", ch)


# -- setting things ------------------------------------------------------------------------------------------------

# C: act_wiz.c do_set
def do_set(ch, argument: str) -> None:
    argument, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  set mob       <name> <field> <value>\n\r", ch)
        send_to_char("  set character <name> <field> <value>\n\r", ch)
        send_to_char("  set obj       <name> <field> <value>\n\r", ch)
        send_to_char("  set room      <room> <field> <value>\n\r", ch)
        send_to_char("  set skill     <name> <spell or skill> <value>\n\r", ch)
        return
    if str_prefix(arg, "mobile") or str_prefix(arg, "character"):
        do_mset(ch, argument)
        return
    if str_prefix(arg, "skill") or str_prefix(arg, "spell"):
        do_sset(ch, argument)
        return
    if str_prefix(arg, "object"):
        do_oset(ch, argument)
        return
    if str_prefix(arg, "room"):
        do_rset(ch, argument)
        return
    do_set(ch, "")  # "echo syntax"


# C: act_wiz.c do_sset
def do_sset(ch, argument: str) -> None:
    from charm.data.skills import SKILL_TABLE
    from charm.world.lookup import skill_lookup

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    argument, arg3 = one_argument(argument)
    if arg1 == "" or arg2 == "" or arg3 == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  set skill <name> <spell or skill> <value>\n\r", ch)
        send_to_char("  set skill <name> all <value>\n\r", ch)
        send_to_char("   (use the name of the skill, not the number)\n\r", ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.is_npc:
        send_to_char("Not on NPC's.\n\r", ch)
        return
    f_all = str_cmp(arg2, "all")
    sn = 0
    if not f_all:
        sn = skill_lookup(arg2)
        if sn < 0:
            send_to_char("No such skill or spell.\n\r", ch)
            return
    # "Snarf the value."
    if not is_number(arg3):
        send_to_char("Value must be numeric.\n\r", ch)
        return
    value = atoi(arg3)
    if value < 0 or value > 100:
        send_to_char("Value range is 0 to 100.\n\r", ch)
        return
    if f_all:
        for sn, skill in enumerate(SKILL_TABLE):  # the C's rows past the table's end have no name
            if skill.name is not None:
                victim.pcdata.learned[sn] = value
    else:
        victim.pcdata.learned[sn] = value


_STATS = (("str", C.STAT_STR, "Strength range is 3 to %d\n\r."),  # sic: the full stop after "\n\r" (#71)
          ("int", C.STAT_INT, "Intelligence range is 3 to %d.\n\r"),
          ("wis", C.STAT_WIS, "Wisdom range is 3 to %d.\n\r"),
          ("dex", C.STAT_DEX, "Dexterity range is 3 to %d.\n\r"),
          ("con", C.STAT_CON, "Constitution range is 3 to %d.\n\r"))


def _mset_usage(ch) -> None:
    send_to_char("Syntax:\n\r", ch)
    send_to_char("  set char <name> <field> <value>\n\r", ch)
    send_to_char("  Field being one of:\n\r", ch)
    send_to_char("    str int wis dex con sex class level\n\r", ch)
    send_to_char("    race group gold silver hp mana move prac\n\r", ch)
    send_to_char("    align train thirst hunger drunk full\n\r", ch)
    send_to_char("    security hours\n\r", ch)


# C: act_wiz.c do_mset
def do_mset(ch, argument: str) -> None:
    from charm.core.cint import sh_int
    from charm.data.classes import CLASS_TABLE
    from charm.data.races import RACE_TABLE
    from charm.net.output import printf_to_char
    from charm.world.lookup import class_lookup, race_lookup

    argument = smash_tilde(argument)
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    arg3 = argument
    if arg1 == "" or arg2 == "" or arg3 == "":
        _mset_usage(ch)
        return
    victim = get_char_world(game_module.current, ch, arg1)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    # "clear zones for mobs": victim->zone = NULL. Nothing in the C ever sets a zone, so there's nothing to clear.
    value = atoi(arg3) if is_number(arg3) else -1  # "Snarf the value (which need not be numeric)."

    # "Set something."
    for name, stat, message in _STATS[:1]:
        if str_cmp(arg2, name):
            _mset_stat(ch, victim, value, stat, message)
            return
    if str_cmp(arg2, "security"):  # "OLC"
        if ch.is_npc:
            send_to_char("NPC's can't set this value.\n\r", ch)
            return
        if victim.is_npc:
            send_to_char("Not on NPC's.\n\r", ch)
            return
        if value > ch.pcdata.security or value < 0:
            if ch.pcdata.security != 0:
                send_to_char("Valid security is 0-%d.\n\r" % ch.pcdata.security, ch)
            else:
                send_to_char("Valid security is 0 only.\n\r", ch)
            return
        victim.pcdata.security = value
        return
    for name, stat, message in _STATS[1:]:
        if str_cmp(arg2, name):
            _mset_stat(ch, victim, value, stat, message)
            return
    if str_prefix(arg2, "sex"):
        if value < 0 or value > 2:
            send_to_char("Sex range is 0 to 2.\n\r", ch)
            return
        victim.sex = value
        if not victim.is_npc:
            victim.pcdata.true_sex = value
        return
    if str_prefix(arg2, "class"):
        if victim.is_npc:
            send_to_char("Mobiles have no class.\n\r", ch)
            return
        class_ = class_lookup(arg3)
        if class_ == -1:
            send_to_char("Possible classes are: %s.\n\r" % " ".join(c.name for c in CLASS_TABLE[:C.MAX_CLASS]), ch)
            return
        victim.class_ = class_
        return
    if str_prefix(arg2, "level"):
        if not victim.is_npc:
            send_to_char("Not on PC's.\n\r", ch)
            return
        if value < 0 or value > C.MAX_LEVEL:
            send_to_char("Level range is 0 to %d.\n\r" % C.MAX_LEVEL, ch)
            return
        victim.level = value
        return
    if str_prefix(arg2, "gold"):
        victim.gold = value
        return
    if str_prefix(arg2, "silver"):
        victim.silver = value
        return
    for name, field, low, message in (
            ("hp", "hit", -10, "Hp range is -10 to 30,000 hit points.\n\r"),
            ("mana", "mana", 0, "Mana range is 0 to 30,000 mana points.\n\r"),
            ("move", "move", 0, "Move range is 0 to 30,000 move points.\n\r")):
        if str_prefix(arg2, name):
            if value < low or value > 30000:
                send_to_char(message, ch)
                return
            setattr(victim, "max_" + field, value)
            if not victim.is_npc:
                setattr(victim.pcdata, "perm_" + field, value)
            return
    for name, field, high, message in (
            ("practice", "practice", 250, "Practice range is 0 to 250 sessions.\n\r"),
            ("train", "train", 50, "Training session range is 0 to 50 sessions.\n\r")):
        if str_prefix(arg2, name):
            if value < 0 or value > high:
                send_to_char(message, ch)
                return
            setattr(victim, field, value)
            return
    if str_prefix(arg2, "align"):
        if value < -1000 or value > 1000:
            send_to_char("Alignment range is -1000 to 1000.\n\r", ch)
            return
        victim.alignment = value
        return
    for name, cond, message in (("thirst", C.COND_THIRST, "Thirst range is -1 to 100.\n\r"),
                                ("drunk", C.COND_DRUNK, "Drunk range is -1 to 100.\n\r"),
                                ("full", C.COND_FULL, "Full range is -1 to 100.\n\r"),
                                ("hunger", C.COND_HUNGER, "Full range is -1 to 100.\n\r")):  # sic: "Full" (#71)
        if str_prefix(arg2, name):
            if victim.is_npc:
                send_to_char("Not on NPC's.\n\r", ch)
                return
            if value < -1 or value > 100:
                send_to_char(message, ch)
                return
            victim.pcdata.condition[cond] = value
            return
    if str_prefix(arg2, "race"):
        race = race_lookup(arg3)
        if race == 0:
            send_to_char("That is not a valid race.\n\r", ch)
            return
        if not victim.is_npc and not RACE_TABLE[race].pc_race:
            send_to_char("That is not a valid player race.\n\r", ch)
            return
        victim.race = race
        return
    if str_prefix(arg2, "group"):
        if not victim.is_npc:
            send_to_char("Only on NPCs.\n\r", ch)
            return
        victim.group = sh_int(value)
        return
    if str_prefix(arg2, "hours"):
        if victim.is_npc:
            send_to_char("Not on NPC's.\n\r", ch)
            return
        if not is_number(arg3):
            send_to_char("Value must be numeric.\n\r", ch)
            return
        value = atoi(arg3)
        if value < 0 or value > 999:
            send_to_char("Value must be between 0 and 999.\n\r", ch)
            return
        victim.played = value * 3600
        printf_to_char(ch, "%s's hours set to %d.", victim.name, value)  # sic: no "\n\r" (#71)
        return
    do_mset(ch, "")  # "Generate usage message."


def _mset_stat(ch, victim, value: int, stat: int, message: str) -> None:
    from charm.entities.handler import get_max_train

    top = get_max_train(victim, stat)
    if value < 3 or value > top:
        send_to_char(message % top, ch)  # format: sprintf
        return
    victim.perm_stat[stat] = value


# C: act_wiz.c do_string
def do_string(ch, argument: str) -> None:
    from charm.commands.info import set_title
    from charm.world.index import ExtraDescr
    from charm.world.lookup import spec_lookup

    argument = smash_tilde(argument)
    argument, type_ = one_argument(argument)
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    arg3 = argument
    if type_ == "" or arg1 == "" or arg2 == "" or arg3 == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  string char <name> <field> <string>\n\r", ch)
        send_to_char("    fields: name short long desc title spec\n\r", ch)
        send_to_char("  string obj  <name> <field> <string>\n\r", ch)
        send_to_char("    fields: name short long extended\n\r", ch)
        return
    if str_prefix(type_, "character") or str_prefix(type_, "mobile"):
        victim = get_char_world(game_module.current, ch, arg1)
        if victim is None:
            send_to_char("They aren't here.\n\r", ch)
            return
        # "clear zone for mobs": nothing sets one (see do_mset)
        # "string something"
        if str_prefix(arg2, "name"):
            if not victim.is_npc:
                send_to_char("Not on PC's.\n\r", ch)
                return
            victim.name = arg3
            return
        if str_prefix(arg2, "description"):
            victim.description = arg3
            return
        if str_prefix(arg2, "short"):
            victim.short_descr = arg3
            return
        if str_prefix(arg2, "long"):
            victim.long_descr = arg3 + "\n\r"
            return
        if str_prefix(arg2, "title"):
            if victim.is_npc:
                send_to_char("Not on NPC's.\n\r", ch)
                return
            set_title(victim, arg3)
            return
        if str_prefix(arg2, "spec"):
            if not victim.is_npc:
                send_to_char("Not on PC's.\n\r", ch)
                return
            victim.spec_fun = spec_lookup(arg3)  # sic: a name that isn't one takes the mob's away (#71)
            if victim.spec_fun is None:
                send_to_char("No such spec fun.\n\r", ch)
            return
    if str_prefix(type_, "object"):  # "string an obj"
        obj = get_obj_world(ch, arg1)
        if obj is None:
            send_to_char("Nothing like that in heaven or earth.\n\r", ch)
            return
        if str_prefix(arg2, "name"):
            obj.name = arg3
            return
        if str_prefix(arg2, "short"):
            obj.short_descr = arg3
            return
        if str_prefix(arg2, "long"):
            obj.description = arg3
            return
        if str_prefix(arg2, "ed") or str_prefix(arg2, "extended"):
            # The C's "argument == NULL" test for a missing string can't be true: one_argument never returns NULL.
            argument, arg3 = one_argument(argument)
            obj.extra_descr.insert(0, ExtraDescr(arg3, argument + "\n\r"))
            return
    do_string(ch, "")  # "echo bad use message"


# C: act_wiz.c do_oset
def do_oset(ch, argument: str) -> None:
    from charm.core.cint import sh_int

    argument = smash_tilde(argument)
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    arg3 = argument
    if arg1 == "" or arg2 == "" or arg3 == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  set obj <object> <field> <value>\n\r", ch)
        send_to_char("  Field being one of:\n\r", ch)
        send_to_char("    value0 value1 value2 value3 value4 (v1-v4)\n\r", ch)
        send_to_char("    extra wear level weight cost timer\n\r", ch)
        return
    obj = get_obj_world(ch, arg1)
    if obj is None:
        send_to_char("Nothing like that in heaven or earth.\n\r", ch)
        return
    value = atoi(arg3)  # "Snarf the value (which need not be numeric)."
    # "Set something."
    for i in range(5):
        if str_cmp(arg2, "value%d" % i) or str_cmp(arg2, "v%d" % i):
            obj.value[i] = min(50, value) if i == 0 else value
            return
    if str_prefix(arg2, "extra"):
        obj.extra_flags = value
        return
    if str_prefix(arg2, "wear"):
        obj.wear_flags = value
        return
    if str_prefix(arg2, "level"):
        obj.level = sh_int(value)
        return
    if str_prefix(arg2, "weight"):
        obj.weight = sh_int(value)
        return
    if str_prefix(arg2, "cost"):
        obj.cost = value
        return
    if str_prefix(arg2, "timer"):
        obj.timer = sh_int(value)
        return
    do_oset(ch, "")  # "Generate usage message."


# C: act_wiz.c do_rset
def do_rset(ch, argument: str) -> None:
    from charm.core.cint import sh_int

    argument = smash_tilde(argument)
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    arg3 = argument
    if arg1 == "" or arg2 == "" or arg3 == "":
        send_to_char("Syntax:\n\r", ch)
        send_to_char("  set room <location> <field> <value>\n\r", ch)
        send_to_char("  Field being one of:\n\r", ch)
        send_to_char("    flags sector\n\r", ch)
        return
    location = find_location(ch, arg1)
    if location is None:
        send_to_char("No such location.\n\r", ch)
        return
    if (not is_room_owner(ch, location) and ch.in_room is not location and room_is_private(location)
            and not _trusted(ch, C.IMPLEMENTOR)):
        send_to_char("That room is private right now.\n\r", ch)
        return
    if not is_number(arg3):  # "Snarf the value."
        send_to_char("Value must be numeric.\n\r", ch)
        return
    value = atoi(arg3)
    # "Set something."
    if str_prefix(arg2, "flags"):
        location.room_flags = value
        return
    if str_prefix(arg2, "sector"):
        location.sector_type = sh_int(value)
        return
    do_rset(ch, "")  # "Generate usage message."


# -- force ---------------------------------------------------------------------------------------------------------

def _force_each(ch, buf: str, argument: str, whom) -> None:
    """force players' and force gods' loop: the C walks char_list by the next pointer it took before each
    command, so a command that frees that next character (a player quitting frees their pet, loaded just after
    them) sends the loop through freed memory (#72)."""
    from charm.commands.interp import interpret

    chars = game_module.current.char_list
    vch = chars[0] if chars else None
    while vch is not None:
        at = chars.index(vch)
        vch_next = chars[at + 1] if at + 1 < len(chars) else None
        if whom(vch):
            act(buf, ch, None, vch, C.TO_VICT)
            interpret(vch, argument)
        if vch_next is not None and not vch_next.valid:
            raise CWouldCrash("act_wiz.c do_force: the command freed the next character, which the loop reads")
        vch = vch_next


# C: act_wiz.c do_force
def do_force(ch, argument: str) -> None:
    from charm.commands.interp import interpret

    game = game_module.current
    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        send_to_char("Force whom to do what?\n\r", ch)
        return
    _, arg2 = one_argument(argument)
    if str_cmp(arg2, "delete") or str_prefix(arg2, "mob"):
        send_to_char("That will NOT be done.\n\r", ch)
        return
    buf = "$n forces you to '%s'." % argument  # act reads any $ codes in the command too (#71)

    if str_cmp(arg, "all"):
        # "Replaced original block with code by Edwin to keep from corrupting pfiles in certain pet-infested
        # situations. JR -- 10/15/00"
        if get_trust(ch) < C.MAX_LEVEL - 3:
            send_to_char("Not at your level!\n\r", ch)
            return
        descs = game.descriptor_list
        desc = descs[0] if descs else None
        while desc is not None:
            at = descs.index(desc)
            desc_next = descs[at + 1] if at + 1 < len(descs) else None
            if desc.connected == C.CON_PLAYING and get_trust(desc.character) < get_trust(ch):
                act(buf, ch, None, desc.character, C.TO_VICT)
                interpret(desc.character, argument)
            if desc_next is not None and desc_next.closed:
                raise CWouldCrash("act_wiz.c do_force: the command closed the next connection, which the loop reads")
            desc = desc_next
    elif str_cmp(arg, "players"):
        if get_trust(ch) < C.MAX_LEVEL - 2:
            send_to_char("Not at your level!\n\r", ch)
            return
        _force_each(ch, buf, argument,
                    lambda vch: not vch.is_npc and get_trust(vch) < get_trust(ch) and vch.level < C.LEVEL_HERO)
    elif str_cmp(arg, "gods"):
        if get_trust(ch) < C.MAX_LEVEL - 2:
            send_to_char("Not at your level!\n\r", ch)
            return
        _force_each(ch, buf, argument,
                    lambda vch: not vch.is_npc and get_trust(vch) < get_trust(ch) and vch.level >= C.LEVEL_HERO)
    else:
        victim = get_char_world(game, ch, arg)
        if victim is None:
            send_to_char("They aren't here.\n\r", ch)
            return
        if victim is ch:
            send_to_char("Aye aye, right away!\n\r", ch)
            return
        if _private_from(ch, victim):
            send_to_char("That character is in a private room.\n\r", ch)
            return
        if get_trust(victim) >= get_trust(ch):
            send_to_char("Do it yourself!\n\r", ch)
            return
        if not victim.is_npc and get_trust(ch) < C.MAX_LEVEL - 3:
            send_to_char("Not at your level!\n\r", ch)
            return
        act(buf, ch, None, victim, C.TO_VICT)
        interpret(victim, argument)
    send_to_char("Ok.\n\r", ch)


# -- QuickMUD's settings -------------------------------------------------------------------------------------------

# C: act_wiz.c do_qmconfig
def do_qmconfig(ch, argument: str) -> None:
    """"This _should_ encompass all the QuickMUD config commands -- JR 11/24/00"."""
    from charm.net.config import qmconfig_read
    from charm.net.output import printf_to_char

    game = game_module.current
    config = game.config
    if ch.is_npc:
        return
    if argument == "":
        printf_to_char(ch, "Valid qmconfig options are:\n\r")
        printf_to_char(ch, "    show       (shows current status of toggles)\n\r")
        printf_to_char(ch, "    ansiprompt [on|off]\n\r")
        printf_to_char(ch, "    ansicolor  [on|off]\n\r")
        printf_to_char(ch, "    telnetga   [on|off]\n\r")
        printf_to_char(ch, "    read\n\r")
        return
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if str_prefix(arg1, "read"):
        qmconfig_read(game_module.c_path(game, "../area/qmconfig.rc"), config)
        return
    if str_prefix(arg1, "show"):
        printf_to_char(ch, "ANSI prompt: %s", "{GON{x\n\r" if config.ansiprompt else "{ROFF{x\n\r")
        printf_to_char(ch, "ANSI color : %s", "{GON{x\n\r" if config.ansicolor else "{ROFF{x\n\r")
        printf_to_char(ch, "IP Address : %s\n\r", config.ipaddress)
        printf_to_char(ch, "Telnet GA  : %s", "{GON{x\n\r" if config.telnetga else "{ROFF{x\n\r")
        return
    for name, field, on, off in (
            ("ansiprompt", "ansiprompt", "New logins will now get an ANSI color prompt.\n\r",
             "New logins will not get an ANSI color prompt.\n\r"),
            ("ansicolor", "ansicolor", "New players will have color enabled.\n\r",
             "New players will not have color enabled.\n\r"),
            ("telnetga", "telnetga", "Telnet GA will be enabled for new players.\n\r",
             "Telnet GA will be disabled for new players.\n\r")):
        if str_prefix(arg1, name):
            if str_prefix(arg2, "on"):
                setattr(config, field, 1)  # TRUE
                printf_to_char(ch, on)  # format: sprintf
                return
            if str_prefix(arg2, "off"):
                setattr(config, field, 0)  # FALSE
                printf_to_char(ch, off)  # format: sprintf
                return
            printf_to_char(ch, "Valid arguments are \"on\" and \"off\".\n\r")
            return
    printf_to_char(ch, "I have no clue what you are trying to do...\n\r")
