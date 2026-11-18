"""Information commands: help, look (with the show_* helpers), exits, score, affects, title and prompt.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_info.c, src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import sys

from charm.commands.interp import one_argument
from charm.core.errors import NotPorted
from charm.core.log import bug, log_f
from charm.core.strings import str_cmp
from charm.data import constants as C
from charm.entities import game as game_module
from charm.entities.handler import get_trust, is_name
from charm.net.output import page_to_char, send_to_char

SEPARATOR = "\n\r============================================================\n\r\n\r"


# C: db.c append_file
def append_file(ch, file: str, text: str) -> None:
    if ch.is_npc or text == "":
        return
    path = game_module.c_path(game_module.current, file)
    try:
        with open(path, "a", encoding="latin-1", newline="\n") as f:
            f.write("[%5d] %s: %s\n" % (ch.in_room.vnum if ch.in_room is not None else 0, ch.name, text))
    except OSError as e:
        print(f"{file}: {e.strerror}", file=sys.stderr)
        send_to_char("Could not open the file!\n\r", ch)


# C: act_info.c do_help
def do_help(ch, argument: str) -> None:
    if argument == "":
        argument = "summary"
    argall = ""
    while argument != "":  # "help a b" finds help 'a b'
        argument, argone = one_argument(argument)
        if argall != "":
            argall += " "
        argall += argone
    out, found = [], False
    trust = get_trust(ch)
    for h in game_module.current.index.helps:
        level = -1 * h.level - 1 if h.level < 0 else h.level
        if level > trust:
            continue
        if is_name(argall, h.keyword):
            if found:
                out.append(SEPARATOR)
            if h.level >= 0 and not str_cmp(argall, "imotd"):
                out += [h.keyword, "\n\r"]
            out.append(h.text[1:] if h.text.startswith(".") else h.text)  # a leading '.' allows initial blanks
            found = True
            if ch.desc is not None and ch.desc.connected not in (C.CON_PLAYING, C.CON_GEN_GROUPS):
                break  # "small hack :)"
    if not found:
        send_to_char("No help on that word.\n\r", ch)
        if len(argall) > C.MAX_CMD_LEN:
            argall = argall[:C.MAX_CMD_LEN - 1]
            log_f("Excessive command length: %s requested %s.", ch.name, argall)
            send_to_char("That was rude!\n\r", ch)
        else:
            append_file(ch, C.OHELPS_FILE, argall)
    else:
        page_to_char("".join(out), ch)


# C: act_info.c set_title
def set_title(ch, title: str) -> None:
    if ch.is_npc:
        bug("Set_title: NPC.", 0)
        return
    ch.pcdata.title = title if title[:1] in (".", ",", "!", "?") else " " + title


WHERE_NAME = (
    "<used as light>     ", "<worn on finger>    ", "<worn on finger>    ", "<worn around neck>  ",
    "<worn around neck>  ", "<worn on torso>     ", "<worn on head>      ", "<worn on legs>      ",
    "<worn on feet>      ", "<worn on hands>     ", "<worn on arms>      ", "<worn as shield>    ",
    "<worn about body>   ", "<worn about waist>  ", "<worn around wrist> ", "<worn around wrist> ",
    "<wielded>           ", "<held>              ", "<floating nearby>   ",
)


def _upper_first(s: str) -> str:
    """buf[0] = UPPER (buf[0])."""
    return (chr(ord(s[0]) - 32) + s[1:]) if s and "a" <= s[0] <= "z" else s


# C: act_info.c format_obj_to_char
def format_obj_to_char(obj, ch, f_short: bool) -> str:
    from charm.entities.handler import is_affected, is_obj_stat

    if (f_short and not obj.short_descr) or not obj.description:
        return ""
    buf = ""
    if is_obj_stat(obj, C.ITEM_INVIS):
        buf += "(Invis) "
    if is_affected(ch, C.AFF_DETECT_EVIL) and is_obj_stat(obj, C.ITEM_EVIL):
        buf += "(Red Aura) "
    if is_affected(ch, C.AFF_DETECT_GOOD) and is_obj_stat(obj, C.ITEM_BLESS):
        buf += "(Blue Aura) "
    if is_affected(ch, C.AFF_DETECT_MAGIC) and is_obj_stat(obj, C.ITEM_MAGIC):
        buf += "(Magical) "
    if is_obj_stat(obj, C.ITEM_GLOW):
        buf += "(Glowing) "
    if is_obj_stat(obj, C.ITEM_HUM):
        buf += "(Humming) "
    return buf + (obj.short_descr if f_short else obj.description)


# C: act_info.c show_list_to_char
def show_list_to_char(objs, ch, f_short: bool, f_show_nothing: bool) -> None:
    from charm.entities.handler import can_see_obj

    if ch.desc is None:
        return
    combine = ch.is_npc or bool(ch.comm & C.COMM_COMBINE)
    shown: list[list] = []  # [text, count], in first-seen order
    for obj in objs:
        if obj.wear_loc == C.WEAR_NONE and can_see_obj(ch, obj):
            text = format_obj_to_char(obj, ch, f_short)
            if combine:
                # "Look for duplicates, case sensitive. Matches tend to be near end so run loop backwords."
                for entry in reversed(shown):
                    if entry[0] == text:
                        entry[1] += 1
                        break
                else:
                    shown.append([text, 1])
            else:
                shown.append([text, 1])
    out = []
    for text, count in shown:
        if text == "":
            continue
        if combine:
            out.append("(%2d) " % count if count != 1 else "     ")
        out.append(text + "\n\r")
    if f_show_nothing and not shown:
        if combine:
            send_to_char("     ", ch)
        send_to_char("Nothing.\n\r", ch)
    page_to_char("".join(out), ch)


# C: act_info.c show_char_to_char_0
def show_char_to_char_0(victim, ch) -> None:
    from charm.entities.handler import is_affected, is_evil, is_good, pers

    buf = ""
    if victim.comm & C.COMM_AFK:
        buf += "[AFK] "
    if is_affected(victim, C.AFF_INVISIBLE):
        buf += "(Invis) "
    if victim.invis_level >= C.LEVEL_HERO:
        buf += "(Wizi) "
    if is_affected(victim, C.AFF_HIDE):
        buf += "(Hide) "
    if is_affected(victim, C.AFF_CHARM):
        buf += "(Charmed) "
    if is_affected(victim, C.AFF_PASS_DOOR):
        buf += "(Translucent) "
    if is_affected(victim, C.AFF_FAERIE_FIRE):
        buf += "(Pink Aura) "
    if is_evil(victim) and is_affected(ch, C.AFF_DETECT_EVIL):
        buf += "(Red Aura) "
    if is_good(victim) and is_affected(ch, C.AFF_DETECT_GOOD):
        buf += "(Golden Aura) "
    if is_affected(victim, C.AFF_SANCTUARY):
        buf += "(White Aura) "
    if not victim.is_npc and victim.act & C.PLR_KILLER:
        buf += "(KILLER) "
    if not victim.is_npc and victim.act & C.PLR_THIEF:
        buf += "(THIEF) "
    if victim.position == victim.start_pos and victim.long_descr:
        send_to_char(buf + victim.long_descr, ch)
        return

    buf += pers(victim, ch)
    if (not victim.is_npc and not ch.comm & C.COMM_BRIEF and victim.position == C.POS_STANDING
            and ch.on is None):
        buf += victim.pcdata.title

    def furniture(doing: str, at: int, on: int) -> str:
        if victim.on is None:
            return f" is {doing} here."
        where = "at" if victim.on.value[2] & at else ("on" if victim.on.value[2] & on else "in")
        return f" is {doing} {where} {victim.on.short_descr}."

    pos = victim.position
    if pos == C.POS_DEAD:
        buf += " is DEAD!!"
    elif pos == C.POS_MORTAL:
        buf += " is mortally wounded."
    elif pos == C.POS_INCAP:
        buf += " is incapacitated."
    elif pos == C.POS_STUNNED:
        buf += " is lying here stunned."
    elif pos == C.POS_SLEEPING:
        buf += furniture("sleeping", C.SLEEP_AT, C.SLEEP_ON)
    elif pos == C.POS_RESTING:
        buf += furniture("resting", C.REST_AT, C.REST_ON)
    elif pos == C.POS_SITTING:
        buf += furniture("sitting", C.SIT_AT, C.SIT_ON)
    elif pos == C.POS_STANDING:
        buf += " is here." if victim.on is None else furniture("standing", C.STAND_AT, C.STAND_ON)
    elif pos == C.POS_FIGHTING:
        buf += " is here, fighting "
        if victim.fighting is None:
            buf += "thin air??"
        elif victim.fighting is ch:
            buf += "YOU!"
        elif victim.in_room is victim.fighting.in_room:
            buf += pers(victim.fighting, ch) + "."
        else:
            buf += "someone who left??"
    send_to_char(_upper_first(buf + "\n\r"), ch)


# C: act_info.c show_char_to_char_1
def show_char_to_char_1(victim, ch) -> None:
    from charm.core.cint import c_div
    from charm.core.rng import number_percent
    from charm.entities.handler import can_see, can_see_obj, get_eq_char, get_skill, pers
    from charm.net.act import act
    from charm.systems.skills import check_improve
    from charm.world.lookup import GSN

    if can_see(victim, ch):
        if ch is victim:
            act("$n looks at $mself.", ch, None, None, C.TO_ROOM)
        else:
            act("$n looks at you.", ch, None, victim, C.TO_VICT)
            act("$n looks at $N.", ch, None, victim, C.TO_NOTVICT)
    if victim.description:
        send_to_char(victim.description, ch)
    else:
        act("You see nothing special about $M.", ch, None, victim, C.TO_CHAR)
    percent = c_div(100 * victim.hit, victim.max_hit) if victim.max_hit > 0 else -1
    buf = pers(victim, ch)
    if percent >= 100:
        buf += " is in excellent condition.\n\r"
    elif percent >= 90:
        buf += " has a few scratches.\n\r"
    elif percent >= 75:
        buf += " has some small wounds and bruises.\n\r"
    elif percent >= 50:
        buf += " has quite a few wounds.\n\r"
    elif percent >= 30:
        buf += " has some big nasty wounds and scratches.\n\r"
    elif percent >= 15:
        buf += " looks pretty hurt.\n\r"
    elif percent >= 0:
        buf += " is in awful condition.\n\r"
    else:
        buf += " is bleeding to death.\n\r"
    send_to_char(_upper_first(buf), ch)

    found = False
    for i_wear in range(C.MAX_WEAR):
        obj = get_eq_char(victim, i_wear)
        if obj is not None and can_see_obj(ch, obj):
            if not found:
                send_to_char("\n\r", ch)
                act("$N is using:", ch, None, victim, C.TO_CHAR)
                found = True
            send_to_char(WHERE_NAME[i_wear], ch)
            send_to_char(format_obj_to_char(obj, ch, True), ch)
            send_to_char("\n\r", ch)

    if victim is not ch and not ch.is_npc and number_percent() < get_skill(ch, GSN["gsn_peek"]):
        send_to_char("\n\rYou peek at the inventory:\n\r", ch)
        check_improve(ch, GSN["gsn_peek"], True, 4)
        show_list_to_char(victim.carrying, ch, True, True)


# C: act_info.c show_char_to_char
def show_char_to_char(people, ch) -> None:
    from charm.entities.handler import can_see, get_trust, is_affected, room_is_dark

    for rch in list(people):
        if rch is ch:
            continue
        if get_trust(ch) < rch.invis_level:
            continue
        if can_see(ch, rch):
            show_char_to_char_0(rch, ch)
        elif room_is_dark(ch.in_room) and is_affected(rch, C.AFF_INFRARED):
            send_to_char("You see glowing red eyes watching YOU!\n\r", ch)


# C: act_info.c check_blind
def check_blind(ch) -> bool:
    from charm.entities.handler import is_affected

    if not ch.is_npc and ch.act & C.PLR_HOLYLIGHT:
        return True
    if is_affected(ch, C.AFF_BLIND):
        send_to_char("You can't see a thing!\n\r", ch)
        return False
    return True


_DOORS = {"n": 0, "north": 0, "e": 1, "east": 1, "s": 2, "south": 2, "w": 3, "west": 3, "u": 4, "up": 4,
          "d": 5, "down": 5}


# C: act_info.c do_look
def do_look(ch, argument: str) -> None:
    from charm.commands.interp import number_argument
    from charm.core.cint import c_div
    from charm.core.strings import lower, str_cmp
    from charm.data.items import LIQ_TABLE
    from charm.entities.handler import (can_see_obj, get_char_room, get_extra_descr, get_obj_here, is_builder,
                                        is_immortal, is_name, room_is_dark)
    from charm.net.act import act

    if ch.desc is None:
        return
    if ch.position < C.POS_SLEEPING:
        send_to_char("You can't see anything but stars!\n\r", ch)
        return
    if ch.position == C.POS_SLEEPING:
        send_to_char("You can't see anything, you're sleeping!\n\r", ch)
        return
    if not check_blind(ch):
        return
    room = ch.in_room
    if not ch.is_npc and not ch.act & C.PLR_HOLYLIGHT and room_is_dark(room):
        send_to_char("It is pitch black ... \n\r", ch)
        show_char_to_char(room.people, ch)
        return

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    number, arg3 = number_argument(arg1)
    count = 0

    if arg1 == "" or str_cmp(arg1, "auto"):
        # "'look' or 'look auto'"
        send_to_char("{s", ch)
        send_to_char(room.name, ch)
        send_to_char("{x", ch)
        if (is_immortal(ch) and (ch.is_npc or ch.act & C.PLR_HOLYLIGHT)) or is_builder(ch, room.area):
            send_to_char("{r [{RRoom %d{r]{x" % room.vnum, ch)
        send_to_char("\n\r", ch)
        if arg1 == "" or (not ch.is_npc and not ch.comm & C.COMM_BRIEF):
            send_to_char("  ", ch)
            send_to_char("{S", ch)
            send_to_char(room.description, ch)
            send_to_char("{x", ch)
        if not ch.is_npc and ch.act & C.PLR_AUTOEXIT:
            send_to_char("\n\r", ch)
            do_exits(ch, "auto")
        show_list_to_char(room.contents, ch, False, False)
        show_char_to_char(room.people, ch)
        return

    if str_cmp(arg1, "i") or str_cmp(arg1, "in") or str_cmp(arg1, "on"):
        # "'look in'"
        if arg2 == "":
            send_to_char("Look in what?\n\r", ch)
            return
        obj = get_obj_here(ch, arg2)
        if obj is None:
            send_to_char("You do not see that here.\n\r", ch)
            return
        if obj.item_type == C.ITEM_DRINK_CON:
            if obj.value[1] <= 0:
                send_to_char("It is empty.\n\r", ch)
                return
            v0, v1 = obj.value[0], obj.value[1]
            how = ("less than half-" if v1 < c_div(v0, 4) else
                   "about half-" if v1 < c_div(3 * v0, 4) else "more than half-")
            send_to_char("It's %sfilled with  a %s liquid.\n\r" % (how, LIQ_TABLE[obj.value[2]].liq_color), ch)
        elif obj.item_type in (C.ITEM_CONTAINER, C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC):
            if obj.value[1] & C.CONT_CLOSED:
                send_to_char("It is closed.\n\r", ch)
                return
            act("$p holds:", ch, obj, None, C.TO_CHAR)
            show_list_to_char(obj.contains, ch, True, True)
        else:
            send_to_char("That is not a container.\n\r", ch)
        return

    victim = get_char_room(ch, arg1)
    if victim is not None:
        show_char_to_char_1(victim, ch)
        return

    for obj in list(ch.carrying):
        if can_see_obj(ch, obj):  # "player can see object"
            pdesc = get_extra_descr(arg3, obj.extra_descr)
            if pdesc is not None:
                count += 1
                if count == number:
                    send_to_char(pdesc, ch)
                    return
                continue
            pdesc = get_extra_descr(arg3, obj.index.extra_descr)
            if pdesc is not None:
                count += 1
                if count == number:
                    send_to_char(pdesc, ch)
                    return
                continue
            if is_name(arg3, obj.name):
                count += 1
                if count == number:
                    send_to_char(obj.description, ch)
                    send_to_char("\n\r", ch)
                    return

    # Unlike the carried objects above, a match here doesn't skip to the next object: one object can count
    # two or three times (its own extra description, its prototype's, and its name).
    for obj in list(room.contents):
        if can_see_obj(ch, obj):
            pdesc = get_extra_descr(arg3, obj.extra_descr)
            if pdesc is not None:
                count += 1
                if count == number:
                    send_to_char(pdesc, ch)
                    return
            pdesc = get_extra_descr(arg3, obj.index.extra_descr)
            if pdesc is not None:
                count += 1
                if count == number:
                    send_to_char(pdesc, ch)
                    return
            if is_name(arg3, obj.name):
                count += 1
                if count == number:
                    send_to_char(obj.description, ch)
                    send_to_char("\n\r", ch)
                    return

    pdesc = get_extra_descr(arg3, room.extra_descr)
    if pdesc is not None:
        count += 1
        if count == number:
            send_to_char(pdesc, ch)
            return

    if count > 0 and count != number:
        if count == 1:
            send_to_char("You only see one %s here.\n\r" % arg3, ch)
        else:
            send_to_char("You only see %d of those here.\n\r" % count, ch)
        return

    door = _DOORS.get(lower(arg1))
    if door is None:
        send_to_char("You do not see that here.\n\r", ch)
        return
    # "'look direction'"
    pexit = room.exit[door]
    if pexit is None:
        send_to_char("Nothing special there.\n\r", ch)
        return
    if pexit.description:
        send_to_char(pexit.description, ch)
    else:
        send_to_char("Nothing special there.\n\r", ch)
    if pexit.keyword and pexit.keyword[0] != " ":
        if pexit.exit_info & C.EX_CLOSED:
            act("The $d is closed.", ch, None, pexit.keyword, C.TO_CHAR)
        elif pexit.exit_info & C.EX_ISDOOR:
            act("The $d is open.", ch, None, pexit.keyword, C.TO_CHAR)


# C: act_info.c do_exits
def do_exits(ch, argument: str) -> None:
    from charm.commands.move import DIR_NAME
    from charm.core.strings import str_cmp
    from charm.entities.handler import can_see_room, is_immortal, room_is_dark
    from charm.persist.player import capitalize

    f_auto = str_cmp(argument, "auto")
    if not check_blind(ch):
        return
    if f_auto:
        buf = "{o[Exits:"
    elif is_immortal(ch):
        buf = "Obvious exits from room %d:\n\r" % ch.in_room.vnum
    else:
        buf = "Obvious exits:\n\r"
    found = False
    for door in range(6):
        pexit = ch.in_room.exit[door]
        if (pexit is not None and pexit.to_room is not None and can_see_room(ch, pexit.to_room)
                and not pexit.exit_info & C.EX_CLOSED):
            found = True
            if f_auto:
                buf += " " + DIR_NAME[door]
            else:
                to = pexit.to_room
                buf += "%-5s - %s" % (capitalize(DIR_NAME[door]), "Too dark to tell" if room_is_dark(to) else to.name)
                buf += (" (room %d)\n\r" % to.vnum) if is_immortal(ch) else "\n\r"
    if not found:
        buf += " none" if f_auto else "None.\n\r"
    if f_auto:
        buf += "]{x\n\r"
    send_to_char(buf, ch)


_AC_WORDS = (
    (101, "hopelessly vulnerable to"), (80, "defenseless against"), (60, "barely protected from"),
    (40, "slightly armored against"), (20, "somewhat armored against"), (0, "armored against"),
    (-20, "well-armored against"), (-40, "very well-armored against"), (-60, "heavily armored against"),
    (-80, "superbly armored against"), (-100, "almost invulnerable to"),
)
_ALIGN_WORDS = ((900, "angelic"), (700, "saintly"), (350, "good"), (100, "kind"), (-100, "neutral"),
                (-350, "mean"), (-700, "evil"), (-900, "demonic"))
_POSITION_WORDS = {C.POS_DEAD: "You are DEAD!!\n\r", C.POS_MORTAL: "You are mortally wounded.\n\r",
                   C.POS_INCAP: "You are incapacitated.\n\r", C.POS_STUNNED: "You are stunned.\n\r",
                   C.POS_SLEEPING: "You are sleeping.\n\r", C.POS_RESTING: "You are resting.\n\r",
                   C.POS_SITTING: "You are sitting.\n\r", C.POS_STANDING: "You are standing.\n\r",
                   C.POS_FIGHTING: "You are fighting.\n\r"}


# C: act_info.c do_score
def do_score(ch, argument: str) -> None:
    from charm.core.cint import c_div, int32
    from charm.data.classes import CLASS_TABLE
    from charm.data.races import RACE_TABLE
    from charm.entities.handler import (can_carry_n, can_carry_w, get_ac, get_age, get_carry_weight,
                                        get_curr_stat, get_damroll, get_hitroll, is_immortal)
    from charm.systems.skills import exp_per_level

    game = game_module.current
    title = "" if ch.is_npc else ch.pcdata.title
    hours = c_div(ch.played + int32(game.current_time - ch.logon), 3600)
    send_to_char("You are %s%s, level %d, %d years old (%d hours).\n\r"
                 % (ch.name, title, ch.level, get_age(game, ch), hours), ch)
    if get_trust(ch) != ch.level:
        send_to_char("You are trusted at level %d.\n\r" % get_trust(ch), ch)
    sex = "sexless" if ch.sex == 0 else "male" if ch.sex == 1 else "female"
    send_to_char("Race: %s  Sex: %s  Class: %s\n\r"
                 % (RACE_TABLE[ch.race].name, sex, "mobile" if ch.is_npc else CLASS_TABLE[ch.class_].name), ch)
    send_to_char("You have %d/%d hit, %d/%d mana, %d/%d movement.\n\r"
                 % (ch.hit, ch.max_hit, ch.mana, ch.max_mana, ch.move, ch.max_move), ch)
    send_to_char("You have %d practices and %d training sessions.\n\r" % (ch.practice, ch.train), ch)
    send_to_char("You are carrying %d/%d items with weight %d/%d pounds.\n\r"
                 % (ch.carry_number, can_carry_n(ch), c_div(get_carry_weight(ch), 10), c_div(can_carry_w(ch), 10)),
                 ch)
    stats = []
    for stat in (C.STAT_STR, C.STAT_INT, C.STAT_WIS, C.STAT_DEX, C.STAT_CON):
        stats += [ch.perm_stat[stat], get_curr_stat(ch, stat)]
    send_to_char("Str: %d(%d)  Int: %d(%d)  Wis: %d(%d)  Dex: %d(%d)  Con: %d(%d)\n\r" % tuple(stats), ch)
    send_to_char("You have scored %d exp, and have %d gold and %d silver coins.\n\r"
                 % (ch.exp, ch.gold, ch.silver), ch)
    # "RT shows exp to level"
    if not ch.is_npc and ch.level < C.LEVEL_HERO:
        send_to_char("You need %d exp to level.\n\r"
                     % ((ch.level + 1) * exp_per_level(ch, ch.pcdata.points) - ch.exp), ch)
    send_to_char("Wimpy set to %d hit points.\n\r" % ch.wimpy, ch)
    if not ch.is_npc and ch.pcdata.condition[C.COND_DRUNK] > 10:
        send_to_char("You are drunk.\n\r", ch)
    if not ch.is_npc and ch.pcdata.condition[C.COND_THIRST] == 0:
        send_to_char("You are thirsty.\n\r", ch)
    if not ch.is_npc and ch.pcdata.condition[C.COND_HUNGER] == 0:
        send_to_char("You are hungry.\n\r", ch)
    if ch.position in _POSITION_WORDS:
        send_to_char(_POSITION_WORDS[ch.position], ch)

    # "print AC values"
    if ch.level >= 25:
        send_to_char("Armor: pierce: %d  bash: %d  slash: %d  magic: %d\n\r"
                     % (get_ac(ch, C.AC_PIERCE), get_ac(ch, C.AC_BASH), get_ac(ch, C.AC_SLASH),
                        get_ac(ch, C.AC_EXOTIC)), ch)
    for i, temp in enumerate(("piercing", "bashing", "slashing", "magic")):
        send_to_char("You are ", ch)
        ac = get_ac(ch, i)
        words = next((w for limit, w in _AC_WORDS if ac >= limit), "divinely armored against")
        send_to_char("%s %s.\n\r" % (words, temp), ch)

    # "RT wizinvis and holy light"
    if is_immortal(ch):
        send_to_char("Holy Light: ", ch)
        send_to_char("on" if ch.act & C.PLR_HOLYLIGHT else "off", ch)
        if ch.invis_level:
            send_to_char("  Invisible: level %d" % ch.invis_level, ch)
        if ch.incog_level:
            send_to_char("  Incognito: level %d" % ch.incog_level, ch)
        send_to_char("\n\r", ch)
    if ch.level >= 15:
        send_to_char("Hitroll: %d  Damroll: %d.\n\r" % (get_hitroll(ch), get_damroll(ch)), ch)
    if ch.level >= 10:
        send_to_char("Alignment: %d.  " % ch.alignment, ch)
    send_to_char("You are ", ch)
    word = next((w for limit, w in _ALIGN_WORDS if ch.alignment > limit), "satanic")
    send_to_char(word + ".\n\r", ch)
    if ch.comm & C.COMM_SHOW_AFFECTS:
        do_affects(ch, "")


# C: act_info.c do_affects [partial]
def do_affects(ch, argument: str) -> None:
    """[partial]: from level 20 it names what each affect modifies (affect_loc_name), which isn't ported."""
    from charm.data.skills import SKILL_TABLE

    if not ch.affected:
        send_to_char("You are not affected by any spells.\n\r", ch)
        return
    send_to_char("You are affected by the following spells:\n\r", ch)
    last = None
    for paf in list(ch.affected):
        if last is not None and paf.type == last.type:
            if ch.level >= 20:
                buf = "                      "
            else:
                continue
        else:
            buf = "Spell: %-15s" % SKILL_TABLE[paf.type].name
        send_to_char(buf, ch)
        if ch.level >= 20:
            raise NotPorted("act_info.c do_affects: affect_loc_name (level 20 and up)")
        send_to_char("\n\r", ch)
        last = paf


# C: act_info.c do_title
def do_title(ch, argument: str) -> None:
    from charm.core.strings import smash_tilde

    if ch.is_npc:
        return
    argument = argument[:45]
    i = len(argument)
    # "Drop a lone trailing colour code. Guarded so an empty or one-character title doesn't read before the
    # argument (#9). -- Charm"
    if i > 0 and argument[i - 1] == "{" and (i < 2 or argument[i - 2] != "{"):
        argument = argument[:i - 1]
    if argument == "":
        send_to_char("Change your title to what?\n\r", ch)
        return
    set_title(ch, smash_tilde(argument))
    send_to_char("Ok.\n\r", ch)


# C: act_info.c do_prompt
def do_prompt(ch, argument: str) -> None:
    from charm.core.strings import smash_tilde, str_suffix

    if argument == "":
        if ch.comm & C.COMM_PROMPT:
            send_to_char("You will no longer see prompts.\n\r", ch)
            ch.comm &= ~C.COMM_PROMPT
        else:
            send_to_char("You will now see prompts.\n\r", ch)
            ch.comm |= C.COMM_PROMPT
        return
    if argument == "all":
        buf = "<%hhp %mm %vmv> "
    else:
        buf = smash_tilde(argument[:50])
        if not str_suffix("%c", buf):
            buf += " "
    ch.prompt = buf
    send_to_char("Prompt set to %s\n\r" % ch.prompt, ch)
