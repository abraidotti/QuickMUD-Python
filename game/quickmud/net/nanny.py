"""nanny: a connection's way from the name prompt into the game, one line of input at a time.

Ported line by line from nanny.c, with the checks it calls from comm.c (check_parse_name, check_reconnect,
check_playing).

The note-writing states (CON_NOTE_*) go to board.c's handlers, in quickmud.persist.boards.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/nanny.c, src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.info import do_help, do_look, set_title
from quickmud.commands.interp import SPACE, one_argument
from quickmud.commands.wiz import do_outfit
from quickmud.core.crypt import crypt
from quickmud.core.log import bug, log_string
from quickmud.core.strings import lower, str_cmp, str_prefix, str_suffix
from quickmud.data import constants as C
from quickmud.data.classes import CLASS_TABLE, TITLE_TABLE
from quickmud.data.clans import CLAN_TABLE
from quickmud.data.items import WEAPON_TABLE
from quickmud.data.races import PC_RACE_TABLE, RACE_TABLE
from quickmud.entities.create import create_object, free_char
from quickmud.entities.handler import char_to_room, get_trust, is_exact_name, is_immortal, is_name, obj_to_char, \
    reset_char
from quickmud.entities.things import new_gen_data
from quickmud.net.act import act
from quickmud.net.output import send_to_char, send_to_desc, write_to_buffer
from quickmud.net.wiznet import wiznet
from quickmud.persist.boards import do_board
from quickmud.persist.player import capitalize, load_char_obj
from quickmud.systems.skills import do_skills, exp_per_level, group_add, list_group_costs, parse_gen_groups
from quickmud.world.lookup import GSN, class_lookup, race_lookup, weapon_lookup

ECHO_OFF = "\xff\xfb\x01"  # echo_off_str: IAC WILL TELOPT_ECHO
ECHO_ON = "\xff\xfc\x01"  # echo_on_str: IAC WONT TELOPT_ECHO
WELCOME = "\n\rWelcome to QuickMUD-Python.  Please don't feed the mobiles!\n\r"


def _crypt(key: str, salt: str) -> str:
    """crypt() as the C game calls it: glibc gives its failure token, "*0", for a salt it can't use (an empty
    password field, say), and that never equals a stored password."""
    try:
        return crypt(key, salt)
    except ValueError:
        return "*0"


def _upper(c: str) -> str:
    return chr(ord(c) - 32) if "a" <= c <= "z" else c


# C: comm.c check_parse_name
def check_parse_name(game, name: str) -> bool:
    from quickmud.net.server import close_socket

    if is_exact_name(name, "all auto immortal self someone something the you loner none"):  # reserved words
        return False
    for clan in CLAN_TABLE:  # check clans
        if clan.name and lower(name[:1]) == lower(clan.name[0]) and str_cmp(name, clan.name):
            return False
    if not str_cmp(capitalize(name), "Alander") and (str_prefix("alan", name)
                                                    or str_suffix("alander", name)):
        return False
    if len(name) < 2 or len(name) > 12:  # length restrictions
        return False
    # "Alphanumerics only. Lock out IllIll twits."
    ill, adjcaps, cleancaps, total_caps = True, False, False, 0
    for c in name:
        if not ("a" <= c <= "z" or "A" <= c <= "Z"):
            return False
        if "A" <= c <= "Z":  # "ugly anti-caps hack"
            if adjcaps:
                cleancaps = True
            total_caps += 1
            adjcaps = True
        else:
            adjcaps = False
        if lower(c) not in ("i", "l"):
            ill = False
    if ill:
        return False
    if cleancaps or (total_caps > len(name) // 2 and len(name) < 3):  # non-negative: a length
        return False
    for m in game.index.mobs.values():  # "Prevent players from naming themselves after mobs."
        if is_name(name, m.player_name):
            return False
    if game.descriptor_list:  # "Check names of people playing" (half-made newbies of the same name)
        count = 0
        for d in list(game.descriptor_list):
            ch = d.character
            # sic: someone writing a note isn't CON_PLAYING either, so it's closed too (#66)
            if d.connected != C.CON_PLAYING and ch is not None and ch.name and str_cmp(ch.name, name):
                count += 1
                close_socket(d)
        if count:
            wiznet(game, f"Double newbie alert ({name})", None, None, C.WIZ_LOGINS, 0, 0)
            return False
    return True


# C: comm.c check_reconnect
def check_reconnect(game, d, name: str, conn: bool) -> bool:
    for ch in game.char_list:
        if not ch.is_npc and (not conn or ch.desc is None) and str_cmp(d.character.name, ch.name):
            if not conn:
                d.character.pcdata.pwd = ch.pcdata.pwd
            else:
                free_char(game, d.character)
                d.character = ch
                ch.desc = d
                ch.timer = 0
                send_to_char("Reconnecting. Type replay to see missed tells.\n\r", ch)
                act("$n has reconnected.", ch, None, None, C.TO_ROOM)
                log_string(f"{ch.name}@{d.host} reconnected.")
                wiznet(game, "$N groks the fullness of $S link.", ch, None, C.WIZ_LINKS, 0, 0)
                d.connected = C.CON_PLAYING
                if ch.pcdata.in_progress:
                    send_to_char("You have a note in progress. Type NWRITE to continue it.\n\r", ch)
            return True
    return False


# C: comm.c check_playing
def check_playing(game, d, name: str) -> bool:
    for dold in game.descriptor_list:
        who = dold.original if dold.original is not None else dold.character
        if (dold is not d and dold.character is not None and dold.connected != C.CON_GET_NAME
                and dold.connected != C.CON_GET_OLD_PASSWORD and str_cmp(name, who.name)):
            write_to_buffer(d, "That character is already playing.\n\r")
            write_to_buffer(d, "Do you wish to connect anyway (Y/N)?")
            d.connected = C.CON_BREAK_CONNECT
            return True
    return False


def _greet(game, d) -> None:
    greeting = game.index.help_greeting
    send_to_desc(greeting[1:] if greeting.startswith(".") else greeting, d)


def _races(d) -> None:
    for race in RACE_TABLE[1:]:
        if not race.pc_race:
            break
        write_to_buffer(d, race.name)
        write_to_buffer(d, " ", 1)
    write_to_buffer(d, "\n\r")


def _weapons(ch) -> str:
    return "".join(w.name + " " for w in WEAPON_TABLE if ch.pcdata.learned[GSN[w.gsn]] > 0) + "\n\rYour choice? "


# C: nanny.c nanny
def nanny(game, d, argument: str) -> None:
    from quickmud.net.server import check_ban, close_socket

    if d.connected != C.CON_NOTE_TEXT:  # "Delete leading spaces UNLESS character is writing a note"
        argument = argument.lstrip(SPACE)
    ch = d.character
    state = d.connected

    if state == C.CON_ANSI:
        first = _upper(argument[:1]) if argument else ""
        if argument == "" or first == "Y":
            d.ansi = True
            send_to_desc("{RAnsi enabled!{x\n\r", d)
            d.connected = C.CON_GET_NAME
            _greet(game, d)
        elif first == "N":
            d.ansi = False
            send_to_desc("Ansi disabled!\n\r", d)
            d.connected = C.CON_GET_NAME
            _greet(game, d)
        else:
            send_to_desc("Do you want ANSI? (Y/n) ", d)

    elif state == C.CON_GET_NAME:
        if argument == "":
            close_socket(d)
            return
        argument = _upper(argument[0]) + argument[1:]
        if not check_parse_name(game, argument):
            send_to_desc("Illegal name, try another.\n\rName: ", d)
            return
        old = load_char_obj(game, d, argument)
        ch = d.character
        if ch.act & C.PLR_DENY:
            log_string(f"Denying access to {argument}@{d.host}.")
            send_to_desc("You are denied access.\n\r", d)
            close_socket(d)
            return
        if check_ban(game, d.host, C.BAN_PERMIT) and not ch.act & C.PLR_PERMIT:
            send_to_desc("Your site has been banned from this mud.\n\r", d)
            close_socket(d)
            return
        if check_reconnect(game, d, argument, False):
            old = True
        elif game.wizlock and not is_immortal(ch):
            send_to_desc("The game is wizlocked.\n\r", d)
            close_socket(d)
            return
        if old:  # old player
            send_to_desc("Password: ", d)
            write_to_buffer(d, ECHO_OFF)
            d.connected = C.CON_GET_OLD_PASSWORD
            return
        if game.newlock:  # new player
            send_to_desc("The game is newlocked.\n\r", d)
            close_socket(d)
            return
        if check_ban(game, d.host, C.BAN_NEWBIES):
            send_to_desc("New players are not allowed from your site.\n\r", None)  # sic: the C passes 0 (#65)
            close_socket(d)
            return
        send_to_desc(f"Did I get that right, {argument} (Y/N)? ", d)
        d.connected = C.CON_CONFIRM_NEW_NAME

    elif state == C.CON_GET_OLD_PASSWORD:
        write_to_buffer(d, "\n\r", 2)
        if _crypt(argument, ch.pcdata.pwd) != ch.pcdata.pwd:
            send_to_desc("Wrong password.\n\r", d)
            close_socket(d)
            return
        write_to_buffer(d, ECHO_ON)
        if check_playing(game, d, ch.name):
            return
        if check_reconnect(game, d, ch.name, True):
            return
        text = f"{ch.name}@{d.host} has connected."
        log_string(text)
        wiznet(game, text, None, None, C.WIZ_SITES, 0, get_trust(ch))
        if ch.desc.ansi:
            ch.act |= C.PLR_COLOUR
        else:
            ch.act &= ~C.PLR_COLOUR
        if is_immortal(ch):
            do_help(ch, "imotd")
            d.connected = C.CON_READ_IMOTD
        else:
            do_help(ch, "motd")
            d.connected = C.CON_READ_MOTD

    elif state == C.CON_BREAK_CONNECT:  # "RT code for breaking link"
        c = argument[:1]
        if c in ("y", "Y"):
            for dold in list(game.descriptor_list):
                if dold is d or dold.character is None:
                    continue
                who = dold.original if dold.original is not None else dold.character
                if not str_cmp(ch.name, who.name):
                    continue
                close_socket(dold)
            if check_reconnect(game, d, ch.name, True):
                return
            send_to_desc("Reconnect attempt failed.\n\rName: ", d)
            if d.character is not None:
                free_char(game, d.character)
                d.character = None
            d.connected = C.CON_GET_NAME
        elif c in ("n", "N"):
            send_to_desc("Name: ", d)
            if d.character is not None:
                free_char(game, d.character)
                d.character = None
            d.connected = C.CON_GET_NAME
        else:
            send_to_desc("Please type Y or N? ", d)

    elif state == C.CON_CONFIRM_NEW_NAME:
        c = argument[:1]
        if c in ("y", "Y"):
            send_to_desc(f"New character.\n\rGive me a password for {ch.name}: {ECHO_OFF}", d)
            d.connected = C.CON_GET_NEW_PASSWORD
            if ch.desc.ansi:
                ch.act |= C.PLR_COLOUR
        elif c in ("n", "N"):
            send_to_desc("Ok, what IS it, then? ", d)
            free_char(game, d.character)
            d.character = None
            d.connected = C.CON_GET_NAME
        else:
            send_to_desc("Please type Yes or No? ", d)

    elif state == C.CON_GET_NEW_PASSWORD:
        write_to_buffer(d, "\n\r", 2)
        if len(argument) < 5:
            send_to_desc("Password must be at least five characters long.\n\rPassword: ", d)
            return
        new = _crypt(argument, ch.name)
        if "~" in new:
            send_to_desc("New password not acceptable, try again.\n\rPassword: ", d)
            return
        ch.pcdata.pwd = new
        send_to_desc("Please retype password: ", d)
        d.connected = C.CON_CONFIRM_NEW_PASSWORD

    elif state == C.CON_CONFIRM_NEW_PASSWORD:
        write_to_buffer(d, "\n\r", 2)
        if _crypt(argument, ch.pcdata.pwd) != ch.pcdata.pwd:
            send_to_desc("Passwords don't match.\n\rRetype password: ", d)
            d.connected = C.CON_GET_NEW_PASSWORD
            return
        write_to_buffer(d, ECHO_ON)
        send_to_desc("The following races are available:\n\r  ", d)
        _races(d)
        send_to_desc("What is your race (help for more information)? ", d)
        d.connected = C.CON_GET_NEW_RACE

    elif state == C.CON_GET_NEW_RACE:
        _, arg = one_argument(argument)
        if arg == "help":
            rest, arg = one_argument(argument)
            do_help(ch, "race help" if rest == "" else rest)
            send_to_desc("What is your race (help for more information)? ", d)
            return
        race = race_lookup(argument)
        if race == 0 or not RACE_TABLE[race].pc_race:
            send_to_desc("That is not a valid race.\n\r", d)
            send_to_desc("The following races are available:\n\r  ", d)
            _races(d)
            send_to_desc("What is your race? (help for more information) ", d)
            return
        ch.race = race
        pr, rt = PC_RACE_TABLE[race], RACE_TABLE[race]
        ch.perm_stat = list(pr.stats)  # initialize stats
        ch.affected_by |= rt.aff
        ch.imm_flags |= rt.imm
        ch.res_flags |= rt.res
        ch.vuln_flags |= rt.vuln
        ch.form = rt.form
        ch.parts = rt.parts
        for skill in pr.skills:  # add skills
            if skill is None:
                break
            group_add(ch, skill, False)
        ch.pcdata.points = pr.points  # add cost
        ch.size = pr.size
        send_to_desc("What is your sex (M/F)? ", d)
        d.connected = C.CON_GET_NEW_SEX

    elif state == C.CON_GET_NEW_SEX:
        c = argument[:1]
        if c in ("m", "M"):
            ch.sex = ch.pcdata.true_sex = C.SEX_MALE
        elif c in ("f", "F"):
            ch.sex = ch.pcdata.true_sex = C.SEX_FEMALE
        else:
            send_to_desc("That's not a sex.\n\rWhat IS your sex? ", d)
            return
        write_to_buffer(d, "Select a class [" + " ".join(c.name for c in CLASS_TABLE) + "]: ")
        d.connected = C.CON_GET_NEW_CLASS

    elif state == C.CON_GET_NEW_CLASS:
        i = class_lookup(argument)
        if i == -1:
            send_to_desc("That's not a class.\n\rWhat IS your class? ", d)
            return
        ch.class_ = i
        text = f"{ch.name}@{d.host} new player."
        log_string(text)
        wiznet(game, "Newbie alert!  $N sighted.", ch, None, C.WIZ_NEWBIE, 0, 0)
        wiznet(game, text, None, None, C.WIZ_SITES, 0, get_trust(ch))
        write_to_buffer(d, "\n\r", 2)
        send_to_desc("You may be good, neutral, or evil.\n\r", d)
        send_to_desc("Which alignment (G/N/E)? ", d)
        d.connected = C.CON_GET_ALIGNMENT

    elif state == C.CON_GET_ALIGNMENT:
        c = argument[:1]
        if c in ("g", "G"):
            ch.alignment = 750
        elif c in ("n", "N"):
            ch.alignment = 0
        elif c in ("e", "E"):
            ch.alignment = -750
        else:
            send_to_desc("That's not a valid alignment.\n\r", d)
            send_to_desc("Which alignment (G/N/E)? ", d)
            return
        write_to_buffer(d, "\n\r")
        group_add(ch, "rom basics", False)
        group_add(ch, CLASS_TABLE[ch.class_].base_group, False)
        ch.pcdata.learned[GSN["gsn_recall"]] = 50
        send_to_desc("Do you wish to customize this character?\n\r", d)
        send_to_desc("Customization takes time, but allows a wider range of skills and abilities.\n\r", d)
        send_to_desc("Customize (Y/N)? ", d)
        d.connected = C.CON_DEFAULT_CHOICE

    elif state == C.CON_DEFAULT_CHOICE:
        write_to_buffer(d, "\n\r", 2)
        c = argument[:1]
        if c in ("y", "Y"):
            ch.gen_data = new_gen_data()
            ch.gen_data.points_chosen = ch.pcdata.points
            do_help(ch, "group header")
            list_group_costs(ch)
            write_to_buffer(d, "You already have the following skills:\n\r")
            do_skills(ch, "")
            do_help(ch, "menu choice")
            d.connected = C.CON_GEN_GROUPS
        elif c in ("n", "N"):
            group_add(ch, CLASS_TABLE[ch.class_].default_group, True)
            write_to_buffer(d, "\n\r", 2)
            write_to_buffer(d, "Please pick a weapon from the following choices:\n\r")
            write_to_buffer(d, _weapons(ch))
            d.connected = C.CON_PICK_WEAPON
        else:
            write_to_buffer(d, "Please answer (Y/N)? ")

    elif state == C.CON_PICK_WEAPON:
        write_to_buffer(d, "\n\r", 2)
        w = weapon_lookup(argument)
        if w == -1 or ch.pcdata.learned[GSN[WEAPON_TABLE[w].gsn]] <= 0:
            write_to_buffer(d, "That's not a valid selection. Choices are:\n\r")
            write_to_buffer(d, _weapons(ch))
            return
        ch.pcdata.learned[GSN[WEAPON_TABLE[w].gsn]] = 40
        write_to_buffer(d, "\n\r", 2)
        do_help(ch, "motd")
        d.connected = C.CON_READ_MOTD

    elif state == C.CON_GEN_GROUPS:
        send_to_char("\n\r", ch)
        race_points = PC_RACE_TABLE[ch.race].points
        if str_cmp(argument, "done"):
            if ch.pcdata.points == race_points:
                send_to_char("You didn't pick anything.\n\r", ch)
                return
            if ch.pcdata.points < 40 + race_points:
                send_to_char("You must take at least %d points of skills and groups" % (40 + race_points), ch)
                return
            send_to_char("Creation points: %d\n\r" % ch.pcdata.points, ch)
            buf = "Experience per level: %d\n\r" % exp_per_level(ch, ch.gen_data.points_chosen)
            if ch.pcdata.points < 40:
                ch.train = (40 - ch.pcdata.points + 1) // 2  # non-negative: points < 40
            ch.gen_data = None
            send_to_char(buf, ch)
            write_to_buffer(d, "\n\r", 2)
            write_to_buffer(d, "Please pick a weapon from the following choices:\n\r")
            write_to_buffer(d, _weapons(ch))
            d.connected = C.CON_PICK_WEAPON
            return
        if not parse_gen_groups(ch, argument):
            send_to_char("Choices are: list,learned,premise,add,drop,info,help, and done.\n\r", ch)
        do_help(ch, "menu choice")

    elif state == C.CON_READ_IMOTD:
        write_to_buffer(d, "\n\r", 2)
        do_help(ch, "motd")
        d.connected = C.CON_READ_MOTD

    elif C.CON_NOTE_TO <= state <= C.CON_NOTE_FINISH:
        from quickmud.persist import boards

        {C.CON_NOTE_TO: boards.handle_con_note_to, C.CON_NOTE_SUBJECT: boards.handle_con_note_subject,
         C.CON_NOTE_EXPIRE: boards.handle_con_note_expire, C.CON_NOTE_TEXT: boards.handle_con_note_text,
         C.CON_NOTE_FINISH: boards.handle_con_note_finish}[state](d, argument)

    elif state == C.CON_READ_MOTD:
        if ch.pcdata is None or ch.pcdata.pwd == "":
            write_to_buffer(d, "Warning! Null password!\n\r")
            write_to_buffer(d, "Please report old password with bug.\n\r")
            write_to_buffer(d, "Type 'password null <new password>' to fix.\n\r")
        write_to_buffer(d, WELCOME)
        game.char_list.insert(0, ch)
        d.connected = C.CON_PLAYING
        reset_char(ch)
        ix = game.index
        if ch.level == 0:
            if game.config.ansicolor:
                ch.act |= C.PLR_COLOUR
            if game.config.telnetga:
                ch.comm |= C.COMM_TELNET_GA
            ch.perm_stat[CLASS_TABLE[ch.class_].attr_prime] += 3
            ch.level = 1
            ch.exp = exp_per_level(ch, ch.pcdata.points)
            ch.hit, ch.mana, ch.move = ch.max_hit, ch.max_mana, ch.max_move
            ch.train = 3
            ch.practice = 5
            set_title(ch, "the %s" % TITLE_TABLE[ch.class_][ch.level][1 if ch.sex == C.SEX_FEMALE else 0])
            do_outfit(ch, "")
            obj_to_char(create_object(game, ix.get_obj_index(C.OBJ_VNUM_MAP), 0), ch)
            char_to_room(ch, ix.get_room_index(C.ROOM_VNUM_SCHOOL))
            send_to_char("\n\r", ch)
            do_help(ch, "newbie info")
            send_to_char("\n\r", ch)
        elif ch.in_room is not None:
            char_to_room(ch, ch.in_room)
        elif is_immortal(ch):
            char_to_room(ch, ix.get_room_index(C.ROOM_VNUM_CHAT))
        else:
            char_to_room(ch, ix.get_room_index(C.ROOM_VNUM_TEMPLE))
        act("$n has entered the game.", ch, None, None, C.TO_ROOM)
        do_look(ch, "auto")
        wiznet(game, "$N has left real life behind.", ch, None, C.WIZ_LOGINS, C.WIZ_SITES, get_trust(ch))
        if ch.pet is not None:
            char_to_room(ch.pet, ch.in_room)
            act("$n has entered the game.", ch.pet, None, None, C.TO_ROOM)
        send_to_char("\n", ch)
        do_board(ch, "")

    else:
        bug("Nanny: bad d->connected %d.", d.connected)
        close_socket(d)
