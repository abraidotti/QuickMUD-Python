"""mob_cmds.c: the commands a mob program runs with a "mob" line (mob echo, mob transfer, mob call, ...), the
immortals' mpstat and mpdump, and the mob command itself (#74, P4 PR 8).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mob_cmds.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import interpret, is_number, one_argument
from quickmud.core.errors import CWouldCrash
from quickmud.core.log import bug
from quickmud.core.rng import number_door, number_range
from quickmud.core.strings import atoi, str_cmp, str_prefix
from quickmud.data import constants as C
from quickmud.entities.handler import get_char_room, get_obj_here
from quickmud.net.act import act
from quickmud.net.output import send_to_char


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


def _vnum(ch) -> int:
    return ch.index.vnum if ch.is_npc else 0


# C: mob_cmds.c do_mob
def do_mob(ch, argument: str) -> None:
    from quickmud.entities.handler import get_trust

    if ch.desc is not None and get_trust(ch) < C.MAX_LEVEL:  # "Security check!"
        return
    mob_interpret(ch, argument)


# C: mob_cmds.c mob_interpret
def mob_interpret(ch, argument: str) -> None:
    """"Mob command interpreter... A trivial hack of interpret()": the first mob command the word starts."""
    argument, command = one_argument(argument)
    for name, fn in MOB_CMD_TABLE:
        if command and command[0] == name[0] and str_prefix(command, name):
            fn(ch, argument)
            return
    bug("Mob_interpret: invalid cmd from mob %d: '%s'" % (_vnum(ch), command), 0)


# C: mob_cmds.c mprog_type_to_name
def mprog_type_to_name(kind: int) -> str:
    return {C.TRIG_ACT: "ACT", C.TRIG_SPEECH: "SPEECH", C.TRIG_RANDOM: "RANDOM", C.TRIG_FIGHT: "FIGHT",
            C.TRIG_HPCNT: "HPCNT", C.TRIG_DEATH: "DEATH", C.TRIG_ENTRY: "ENTRY", C.TRIG_GREET: "GREET",
            C.TRIG_GRALL: "GRALL", C.TRIG_GIVE: "GIVE", C.TRIG_BRIBE: "BRIBE", C.TRIG_KILL: "KILL",
            C.TRIG_DELAY: "DELAY", C.TRIG_SURR: "SURRENDER", C.TRIG_EXIT: "EXIT",
            C.TRIG_EXALL: "EXALL"}.get(kind, "ERROR")


# C: mob_cmds.c do_mpstat
def do_mpstat(ch, argument: str) -> None:
    """"Displays MOBprogram triggers of a mobile"."""
    from quickmud.entities.handler import get_char_world

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Mpstat whom?\n\r", ch)
        return
    victim = get_char_world(_game(), ch, arg)
    if victim is None:
        send_to_char("No such creature.\n\r", ch)
        return
    if not victim.is_npc:
        send_to_char("That is not a mobile.\n\r", ch)
        return
    # (the C looks the mob up a second time here, for "No such creature visible.", and finds the same one)
    send_to_char("Mobile #%-6d [%s]\n\r" % (victim.index.vnum, victim.short_descr), ch)
    send_to_char("Delay   %-6d [%s]\n\r" % (victim.mprog_delay, "No target" if victim.mprog_target is None
                                            else victim.mprog_target.name), ch)
    if not victim.index.mprog_flags:
        send_to_char("[No programs set]\n\r", ch)
        return
    for i, prg in enumerate(victim.index.mprogs, 1):
        send_to_char("[%2d] Trigger [%-8s] Program [%4d] Phrase [%s]\n\r"
                     % (i, mprog_type_to_name(prg.trig_type), prg.vnum, prg.trig_phrase), ch)


# C: mob_cmds.c do_mpdump
def do_mpdump(ch, argument: str) -> None:
    """"Displays the source code of a given MOBprogram"."""
    from quickmud.net.output import page_to_char

    _, buf = one_argument(argument)
    code = _game().index.get_mprog_index(atoi(buf))
    if code is None:
        send_to_char("No such MOBprogram.\n\r", ch)
        return
    page_to_char(code, ch)


def _echo_to(d, argument: str) -> None:
    from quickmud.entities.handler import is_immortal

    if is_immortal(d.character):
        send_to_char("Mob echo> ", d.character)
    send_to_char(argument, d.character)
    send_to_char("\n\r", d.character)


# C: mob_cmds.c do_mpgecho
def do_mpgecho(ch, argument: str) -> None:
    """"Prints the argument to all active players in the game"."""
    if argument == "":
        bug("MpGEcho: missing argument from vnum %d", _vnum(ch))
        return
    for d in list(_game().descriptor_list):
        if d.connected == C.CON_PLAYING:
            _echo_to(d, argument)


# C: mob_cmds.c do_mpzecho
def do_mpzecho(ch, argument: str) -> None:
    """"Prints the argument to all players in the same area as the mob"."""
    if argument == "":
        bug("MpZEcho: missing argument from vnum %d", _vnum(ch))
        return
    if ch.in_room is None:
        return
    for d in list(_game().descriptor_list):
        if (d.connected == C.CON_PLAYING and d.character.in_room is not None
                and d.character.in_room.area is ch.in_room.area):
            _echo_to(d, argument)


# C: mob_cmds.c do_mpasound
def do_mpasound(ch, argument: str) -> None:
    """"Prints the argument to all the rooms aroud the mobile", with mob triggers off."""
    from quickmud.net.act import MOB_TRIGGER

    if argument == "":
        return
    was_in_room = ch.in_room
    for door in range(6):
        pexit = was_in_room.exit[door]
        if pexit is not None and pexit.to_room is not None and pexit.to_room is not was_in_room:
            ch.in_room = pexit.to_room
            MOB_TRIGGER[0] = False
            act(argument, ch, None, None, C.TO_ROOM)
            MOB_TRIGGER[0] = True
    ch.in_room = was_in_room


# C: mob_cmds.c do_mpkill
def do_mpkill(ch, argument: str) -> None:
    """"Lets the mobile kill any player or mobile without murder"."""
    from quickmud.systems.fight import multi_hit

    _, arg = one_argument(argument)
    if arg == "":
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        return
    if victim is ch or victim.is_npc or ch.position == C.POS_FIGHTING:  # sic (#89): any player, but no mobile
        return
    if ch.affected_by & C.AFF_CHARM and ch.master is victim:
        bug("MpKill - Charmed mob attacking master from vnum %d.", _vnum(ch))
        return
    multi_hit(ch, victim, C.TYPE_UNDEFINED)


# C: mob_cmds.c do_mpassist
def do_mpassist(ch, argument: str) -> None:
    """"Lets the mobile assist another mob or player": it attacks whoever they're fighting."""
    from quickmud.systems.fight import multi_hit

    _, arg = one_argument(argument)
    if arg == "":
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        return
    if victim is ch or ch.fighting is not None or victim.fighting is None:
        return
    multi_hit(ch, victim.fighting, C.TYPE_UNDEFINED)


# C: mob_cmds.c do_mpjunk
def do_mpjunk(ch, argument: str) -> None:
    """"Lets the mobile destroy an object in its inventory", worn or not, or all (all.name) of them."""
    from quickmud.entities.handler import extract_obj, get_obj_carry, get_obj_wear, is_name, unequip_char

    _, arg = one_argument(argument)
    if arg == "":
        return
    if not str_cmp(arg, "all") and not str_prefix("all.", arg):
        obj = get_obj_wear(ch, arg)
        if obj is not None:
            unequip_char(ch, obj)
            extract_obj(_game(), obj)
            return
        obj = get_obj_carry(ch, arg, ch)
        if obj is None:
            return
        extract_obj(_game(), obj)
        return
    for obj in list(ch.carrying):
        if len(arg) == 3 or is_name(arg[4:], obj.name):
            if obj.wear_loc != C.WEAR_NONE:
                unequip_char(ch, obj)
            extract_obj(_game(), obj)


# C: mob_cmds.c do_mpechoaround
def do_mpechoaround(ch, argument: str) -> None:
    """"Prints the message to everyone in the room other than the mob and victim"."""
    argument, arg = one_argument(argument)
    if arg == "":
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        return
    act(argument, ch, None, victim, C.TO_NOTVICT)


# C: mob_cmds.c do_mpechoat
def do_mpechoat(ch, argument: str) -> None:
    """"Prints the message to only the victim"."""
    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        return
    act(argument, ch, None, victim, C.TO_VICT)


# C: mob_cmds.c do_mpecho
def do_mpecho(ch, argument: str) -> None:
    """"Prints the message to the room at large"."""
    if argument == "":
        return
    act(argument, ch, None, None, C.TO_ROOM)


# C: mob_cmds.c do_mpmload
def do_mpmload(ch, argument: str) -> None:
    """"Lets the mobile load another mobile"."""
    from quickmud.entities.create import create_mobile
    from quickmud.entities.handler import char_to_room

    _, arg = one_argument(argument)
    if ch.in_room is None or arg == "" or not is_number(arg):
        return
    vnum = atoi(arg)
    index = _game().index.get_mob_index(vnum)
    if index is None:
        bug("Mpmload: bad mob index (%d) from mob %d" % (vnum, _vnum(ch)), 0)
        return
    victim = create_mobile(_game(), index)
    char_to_room(victim, ch.in_room)


# C: mob_cmds.c do_mpoload
def do_mpoload(ch, argument: str) -> None:
    """"Lets the mobile load an object": at a level (its trust, unless given), to its inventory, the room (R) or
    worn (W)."""
    from quickmud.commands.obj import wear_obj
    from quickmud.entities.create import create_object
    from quickmud.entities.handler import get_trust, obj_to_char, obj_to_room

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    _, arg3 = one_argument(argument)
    if arg1 == "" or not is_number(arg1):
        bug("Mpoload - Bad syntax from vnum %d.", _vnum(ch))
        return
    if arg2 == "":
        level = get_trust(ch)
    else:
        if not is_number(arg2):  # "New feature from Alander."
            bug("Mpoload - Bad syntax from vnum %d.", _vnum(ch))
            return
        level = atoi(arg2)
        if level < 0 or level > get_trust(ch):
            bug("Mpoload - Bad level from vnum %d.", _vnum(ch))
            return
    f_toroom = arg3[:1] in ("R", "r")
    f_wear = not f_toroom and arg3[:1] in ("W", "w")
    index = _game().index.get_obj_index(atoi(arg1))
    if index is None:
        bug("Mpoload - Bad vnum arg from vnum %d.", _vnum(ch))
        return
    obj = create_object(_game(), index, level)
    if (f_wear or not f_toroom) and obj.wear_flags & C.ITEM_TAKE:
        obj_to_char(obj, ch)
        if f_wear:
            wear_obj(ch, obj, True)
    else:
        obj_to_room(obj, ch.in_room)


# C: mob_cmds.c do_mppurge
def do_mppurge(ch, argument: str) -> None:
    """Purge every mob (but itself and those that can't be) and object in the room, or the one named."""
    from quickmud.entities.handler import extract_char, extract_obj

    game = _game()
    _, arg = one_argument(argument)
    if arg == "":
        for victim in list(ch.in_room.people):
            if victim.is_npc and victim is not ch and not victim.act & C.ACT_NOPURGE:
                extract_char(game, victim, True)
        for obj in list(ch.in_room.contents):
            if not obj.extra_flags & C.ITEM_NOPURGE:
                extract_obj(game, obj)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        obj = get_obj_here(ch, arg)
        if obj is not None:
            extract_obj(game, obj)
        else:
            bug("Mppurge - Bad argument from vnum %d.", _vnum(ch))
        return
    if not victim.is_npc:
        bug("Mppurge - Purging a PC from vnum %d.", _vnum(ch))
        return
    extract_char(game, victim, True)


def _find_location(ch, arg: str):
    from quickmud.commands.wiz import find_location

    return find_location(ch, arg)


# C: mob_cmds.c do_mpgoto
def do_mpgoto(ch, argument: str) -> None:
    """"Lets the mobile goto any location it wishes that is not private" (it doesn't check)."""
    from quickmud.entities.handler import char_from_room, char_to_room
    from quickmud.systems.fight import stop_fighting

    _, arg = one_argument(argument)
    if arg == "":
        bug("Mpgoto - No argument from vnum %d.", _vnum(ch))
        return
    location = _find_location(ch, arg)
    if location is None:
        bug("Mpgoto - No such location from vnum %d.", _vnum(ch))
        return
    if ch.fighting is not None:
        stop_fighting(_game(), ch, True)
    char_from_room(ch)
    char_to_room(ch, location)


# C: mob_cmds.c do_mpat
def do_mpat(ch, argument: str) -> None:
    """"Lets the mobile do a command at another location", and come back if it still exists."""
    from quickmud.entities.handler import char_from_room, char_to_room

    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        bug("Mpat - Bad argument from vnum %d.", _vnum(ch))
        return
    location = _find_location(ch, arg)
    if location is None:
        bug("Mpat - No such location from vnum %d.", _vnum(ch))
        return
    original, on = ch.in_room, ch.on
    char_from_room(ch)
    char_to_room(ch, location)
    interpret(ch, argument)
    if any(wch is ch for wch in _game().char_list):  # "See if 'ch' still exists before continuing!"
        char_from_room(ch)
        char_to_room(ch, original)
        ch.on = on


# C: mob_cmds.c do_mptransfer
def do_mptransfer(ch, argument: str) -> None:
    """"Lets the mobile transfer people", to a location or here; all is every player in the room."""
    from quickmud.commands.info import do_look
    from quickmud.entities.handler import char_from_room, char_to_room, get_char_world, room_is_private
    from quickmud.systems.fight import stop_fighting

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "":
        bug("Mptransfer - Bad syntax from vnum %d.", _vnum(ch))
        return
    if str_cmp(arg1, "all"):
        for victim in list(ch.in_room.people):
            if not victim.is_npc:
                do_mptransfer(ch, "%s %s" % (victim.name, arg2))
        return
    if arg2 == "":  # "Thanks to Grodyn for the optional location parameter."
        location = ch.in_room
    else:
        location = _find_location(ch, arg2)
        if location is None:
            bug("Mptransfer - No such location from vnum %d.", _vnum(ch))
            return
        if room_is_private(location):
            return
    victim = get_char_world(_game(), ch, arg1)
    if victim is None or victim.in_room is None:
        return
    if victim.fighting is not None:
        stop_fighting(_game(), victim, True)
    char_from_room(victim)
    char_to_room(victim, location)
    do_look(victim, "auto")


# C: mob_cmds.c do_mpgtransfer
def do_mpgtransfer(ch, argument: str) -> None:
    """"Lets the mobile transfer all chars in same group as the victim" (by name, through mob transfer)."""
    from quickmud.commands.comm import is_same_group

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "":
        bug("Mpgtransfer - Bad syntax from vnum %d.", _vnum(ch))
        return
    who = get_char_room(ch, arg1)
    if who is None:
        return
    for victim in list(ch.in_room.people):
        if is_same_group(who, victim):
            do_mptransfer(ch, "%s %s" % (victim.name, arg2))


# C: mob_cmds.c do_mpforce
def do_mpforce(ch, argument: str) -> None:
    """"Lets the mobile force someone to do something"; all is everyone in the room of lower trust it can see."""
    from quickmud.entities.handler import can_see, get_trust
    from quickmud.systems.fight import _char_list_from

    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        bug("Mpforce - Bad syntax from vnum %d.", _vnum(ch))
        return
    if str_cmp(arg, "all"):
        for vch in _char_list_from(_game().char_list, 0):
            if vch.in_room is ch.in_room and get_trust(vch) < get_trust(ch) and can_see(ch, vch):
                interpret(vch, argument)
        return
    victim = get_char_room(ch, arg)
    if victim is None or victim is ch:
        return
    interpret(victim, argument)


# C: mob_cmds.c do_mpgforce
def do_mpgforce(ch, argument: str) -> None:
    """"Lets the mobile force a group something"."""
    from quickmud.commands.comm import is_same_group
    from quickmud.systems.update import _people_from

    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        bug("MpGforce - Bad syntax from vnum %d.", _vnum(ch))
        return
    victim = get_char_room(ch, arg)
    if victim is None or victim is ch:
        return
    for vch in _people_from(victim.in_room.people):
        if is_same_group(victim, vch):
            interpret(vch, argument)


# C: mob_cmds.c do_mpvforce
def do_mpvforce(ch, argument: str) -> None:
    """"Forces all mobiles of certain vnum to do something (except ch)", those not fighting."""
    from quickmud.systems.fight import _char_list_from

    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        bug("MpVforce - Bad syntax from vnum %d.", _vnum(ch))
        return
    if not is_number(arg):
        bug("MpVforce - Non-number argument vnum %d.", _vnum(ch))
        return
    vnum = atoi(arg)
    for victim in _char_list_from(_game().char_list, 0):
        if victim.is_npc and victim.index.vnum == vnum and ch is not victim and victim.fighting is None:
            interpret(victim, argument)


# C: mob_cmds.c do_mpcast
def do_mpcast(ch, argument: str) -> None:
    """"Lets the mobile cast spells": no mana, and "only crude checking on the target validity"."""
    from quickmud.data.skills import SKILL_TABLE
    from quickmud.systems.magic import cast_spell
    from quickmud.world.lookup import skill_lookup

    argument, spell = one_argument(argument)
    _, target = one_argument(argument)
    if spell == "":
        bug("MpCast - Bad syntax from vnum %d.", _vnum(ch))
        return
    sn = skill_lookup(spell)
    if sn < 0:
        bug("MpCast - No such spell from vnum %d.", _vnum(ch))
        return
    vch = get_char_room(ch, target)
    obj = get_obj_here(ch, target)
    kind = SKILL_TABLE[sn].target
    if kind == C.TAR_IGNORE:
        victim = None
    elif kind == C.TAR_CHAR_OFFENSIVE:
        if vch is None or vch is ch:
            return
        victim = vch
    elif kind == C.TAR_CHAR_DEFENSIVE:
        victim = ch if vch is None else vch
    elif kind == C.TAR_CHAR_SELF:
        victim = ch
    elif kind in (C.TAR_OBJ_CHAR_DEF, C.TAR_OBJ_CHAR_OFF, C.TAR_OBJ_INV):
        if obj is None:
            return
        victim = obj
        if kind != C.TAR_OBJ_INV:
            # sic (#89): the spell is told its target is TAR_OBJ_CHAR_*, not TARGET_OBJ, so it takes the object for
            # a character
            raise CWouldCrash("mob_cmds.c do_mpcast: an object passed to %s as a character" % SKILL_TABLE[sn].name)
    else:
        return
    cast_spell(sn, ch.level, ch, victim, kind)  # the target type as skill_table has it, not TARGET_*


def _damage_roll(victim, low: int, high: int, f_kill: bool) -> int:
    if f_kill:
        return number_range(low, high)
    # UMIN (victim->hit, number_range (low, high)): sic (#89), rolled again when the roll is the smaller
    if victim.hit < number_range(low, high):
        return victim.hit
    return number_range(low, high)


# C: mob_cmds.c do_mpdamage
def do_mpdamage(ch, argument: str) -> None:
    """"Lets mob cause unconditional damage to someone", or everyone else here: low to high, but no more than
    their hit points unless a fourth word (kill) is given. Silent."""
    from quickmud.systems.fight import damage

    argument, target = one_argument(argument)
    argument, low_arg = one_argument(argument)
    argument, high_arg = one_argument(argument)
    if target == "":
        bug("MpDamage - Bad syntax from vnum %d.", _vnum(ch))
        return
    f_all, victim = str_cmp(target, "all"), None
    if not f_all:
        victim = get_char_room(ch, target)
        if victim is None:
            return
    if not is_number(low_arg):
        bug("MpDamage - Bad damage min vnum %d.", _vnum(ch))
        return
    low = atoi(low_arg)
    if not is_number(high_arg):
        bug("MpDamage - Bad damage max vnum %d.", _vnum(ch))
        return
    high = atoi(high_arg)
    _, target = one_argument(argument)
    f_kill = target != ""  # "If kill parameter is omitted, this command is "safe" and will not kill the victim."
    if f_all:
        for victim in list(ch.in_room.people):
            if victim is not ch:
                damage(victim, victim, _damage_roll(victim, low, high, f_kill), C.TYPE_UNDEFINED, C.DAM_NONE,
                       False)
    else:
        damage(victim, victim, _damage_roll(victim, low, high, f_kill), C.TYPE_UNDEFINED, C.DAM_NONE, False)


# C: mob_cmds.c do_mpremember
def do_mpremember(ch, argument: str) -> None:
    """"Lets the mobile to remember a target", for $q and $Q."""
    from quickmud.entities.handler import get_char_world

    _, arg = one_argument(argument)
    if arg != "":
        ch.mprog_target = get_char_world(_game(), ch, arg)
    else:
        bug("MpRemember: missing argument from vnum %d.", _vnum(ch))


# C: mob_cmds.c do_mpforget
def do_mpforget(ch, argument: str) -> None:
    ch.mprog_target = None


# C: mob_cmds.c do_mpdelay
def do_mpdelay(ch, argument: str) -> None:
    """"Sets a delay for MOBprogram execution", counted in mobile pulses, for the delay trigger."""
    _, arg = one_argument(argument)
    if not is_number(arg):
        bug("MpDelay: invalid arg from vnum %d.", _vnum(ch))
        return
    ch.mprog_delay = atoi(arg)


# C: mob_cmds.c do_mpcancel
def do_mpcancel(ch, argument: str) -> None:
    ch.mprog_delay = -1


# C: mob_cmds.c do_mpcall
def do_mpcall(ch, argument: str) -> None:
    """"Lets the mobile to call another MOBprogram withing a MOBprogram", with a character and two objects
    from the room (or none)."""
    from quickmud.systems.mobprog import program_flow

    argument, arg = one_argument(argument)
    if arg == "":
        bug("MpCall: missing arguments from vnum %d.", _vnum(ch))
        return
    vnum = atoi(arg)
    code = _game().index.get_mprog_index(vnum)
    if code is None:
        bug("MpCall: invalid prog from vnum %d.", _vnum(ch))
        return
    vch = obj1 = obj2 = None
    argument, arg = one_argument(argument)
    if arg != "":
        vch = get_char_room(ch, arg)
    argument, arg = one_argument(argument)
    if arg != "":
        obj1 = get_obj_here(ch, arg)
    argument, arg = one_argument(argument)
    if arg != "":
        obj2 = get_obj_here(ch, arg)
    program_flow(vnum, code, ch, vch, obj1, obj2)


# C: mob_cmds.c do_mpflee
def do_mpflee(ch, argument: str) -> None:
    """"Forces the mobile to flee": six tries at a random way out. Only when it isn't fighting (sic, #89)."""
    from quickmud.commands.move import move_char

    if ch.fighting is not None:
        return
    was_in = ch.in_room
    if was_in is None:
        return
    for _ in range(6):
        door = number_door()
        pexit = was_in.exit[door]
        if (pexit is None or pexit.to_room is None or pexit.exit_info & C.EX_CLOSED
                or (ch.is_npc and pexit.to_room.room_flags & C.ROOM_NO_MOB)):
            continue
        move_char(ch, door, False)
        if ch.in_room is not was_in:
            return


# C: mob_cmds.c do_mpotransfer
def do_mpotransfer(ch, argument: str) -> None:
    """"Lets the mobile to transfer an object", from the room or its own inventory."""
    from quickmud.entities.handler import obj_from_char, obj_from_room, obj_to_room, unequip_char

    argument, arg = one_argument(argument)
    if arg == "":
        bug("MpOTransfer - Missing argument from vnum %d.", _vnum(ch))
        return
    _, buf = one_argument(argument)
    location = _find_location(ch, buf)
    if location is None:
        bug("MpOTransfer - No such location from vnum %d.", _vnum(ch))
        return
    obj = get_obj_here(ch, arg)
    if obj is None:
        return
    if obj.carried_by is None:
        obj_from_room(obj)
    else:
        if obj.wear_loc != C.WEAR_NONE:
            unequip_char(ch, obj)
        obj_from_char(obj)
    obj_to_room(obj, location)


# C: mob_cmds.c do_mpremove
def do_mpremove(ch, argument: str) -> None:
    """"Lets the mobile to strip an object or all objects from the victim", by vnum or all."""
    from quickmud.core.cint import sh_int
    from quickmud.entities.handler import extract_obj, obj_from_char, unequip_char

    argument, arg = one_argument(argument)
    victim = get_char_room(ch, arg)
    if victim is None:
        return
    _, arg = one_argument(argument)
    f_all, vnum = False, 0
    if str_cmp(arg, "all"):
        f_all = True
    elif not is_number(arg):
        bug("MpRemove: Invalid object from vnum %d.", _vnum(ch))
        return
    else:
        vnum = sh_int(atoi(arg))
    for obj in list(victim.carrying):
        if f_all or obj.index.vnum == vnum:
            unequip_char(ch, obj)  # sic (#89): the mob, not the victim, and whether it's worn or not
            obj_from_char(obj)
            extract_obj(_game(), obj)


MOB_CMD_TABLE = (
    ("asound", do_mpasound), ("gecho", do_mpgecho), ("zecho", do_mpzecho), ("kill", do_mpkill),
    ("assist", do_mpassist), ("junk", do_mpjunk), ("echo", do_mpecho), ("echoaround", do_mpechoaround),
    ("echoat", do_mpechoat), ("mload", do_mpmload), ("oload", do_mpoload), ("purge", do_mppurge),
    ("goto", do_mpgoto), ("at", do_mpat), ("transfer", do_mptransfer), ("gtransfer", do_mpgtransfer),
    ("otransfer", do_mpotransfer), ("force", do_mpforce), ("gforce", do_mpgforce), ("vforce", do_mpvforce),
    ("cast", do_mpcast), ("damage", do_mpdamage), ("remember", do_mpremember), ("forget", do_mpforget),
    ("delay", do_mpdelay), ("cancel", do_mpcancel), ("call", do_mpcall), ("flee", do_mpflee),
    ("remove", do_mpremove),
)
