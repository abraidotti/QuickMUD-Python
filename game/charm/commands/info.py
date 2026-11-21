"""Information commands, all of act_info.c: look (with the show_* helpers), examine, exits, score, affects, help,
who, where, inventory, equipment, compare, consider, practice, time and weather, the auto toggles and the other
settings (title, description, prompt, scroll, wimpy, password).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_info.c, src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import sys

from charm.commands.interp import one_argument
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


# C: act_info.c do_affects
def do_affects(ch, argument: str) -> None:
    from charm.data.skills import SKILL_TABLE
    from charm.entities.handler import affect_loc_name

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
            send_to_char(": modifies %s by %d " % (affect_loc_name(paf.location), paf.modifier), ch)
            send_to_char("permanently" if paf.duration == -1 else "for %d hours" % paf.duration, ch)
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


# C: act_info.c do_scroll
def do_scroll(ch, argument: str) -> None:
    from charm.commands.interp import is_number
    from charm.core.strings import atoi

    _, arg = one_argument(argument)
    if arg == "":
        if ch.lines == 0:
            send_to_char("You do not page long messages.\n\r", ch)
        else:
            send_to_char("You currently display %d lines per page.\n\r" % (ch.lines + 2), ch)
        return
    if not is_number(arg):
        send_to_char("You must provide a number.\n\r", ch)
        return
    lines = atoi(arg)
    if lines == 0:
        send_to_char("Paging disabled.\n\r", ch)
        ch.lines = 0
        return
    if lines < 10 or lines > 100:
        send_to_char("You must provide a reasonable number.\n\r", ch)
        return
    send_to_char("Scroll set to %d lines.\n\r" % lines, ch)
    ch.lines = lines - 2


# C: act_info.c do_socials
def do_socials(ch, argument: str) -> None:
    col = 0
    for social in game_module.current.index.socials:
        send_to_char("%-12s" % social.name, ch)
        col += 1
        if col % 6 == 0:  # non-negative: a count
            send_to_char("\n\r", ch)
    if col % 6 != 0:  # non-negative: a count
        send_to_char("\n\r", ch)


# C: act_info.c do_motd
def do_motd(ch, argument: str) -> None:
    do_help(ch, "motd")


# C: act_info.c do_imotd
def do_imotd(ch, argument: str) -> None:
    do_help(ch, "imotd")


# C: act_info.c do_rules
def do_rules(ch, argument: str) -> None:
    do_help(ch, "rules")


# C: act_info.c do_story
def do_story(ch, argument: str) -> None:
    do_help(ch, "story")


# C: act_info.c do_wizlist
def do_wizlist(ch, argument: str) -> None:
    do_help(ch, "wizlist")


def _on_off(ch, label: str, on: bool) -> None:
    send_to_char(label, ch)
    send_to_char("{GON{x\n\r" if on else "{ROFF{x\n\r", ch)


# C: act_info.c do_autolist
def do_autolist(ch, argument: str) -> None:
    # "lists most player flags"
    if ch.is_npc:
        return
    send_to_char("   action     status\n\r", ch)
    send_to_char("---------------------\n\r", ch)
    _on_off(ch, "autoassist     ", ch.act & C.PLR_AUTOASSIST)
    _on_off(ch, "autoexit       ", ch.act & C.PLR_AUTOEXIT)
    _on_off(ch, "autogold       ", ch.act & C.PLR_AUTOGOLD)
    _on_off(ch, "autoloot       ", ch.act & C.PLR_AUTOLOOT)
    _on_off(ch, "autosac        ", ch.act & C.PLR_AUTOSAC)
    _on_off(ch, "autosplit      ", ch.act & C.PLR_AUTOSPLIT)
    _on_off(ch, "telnetga       ", ch.comm & C.COMM_TELNET_GA)
    _on_off(ch, "compact mode   ", ch.comm & C.COMM_COMPACT)
    _on_off(ch, "prompt         ", ch.comm & C.COMM_PROMPT)
    _on_off(ch, "combine items  ", ch.comm & C.COMM_COMBINE)
    if not ch.act & C.PLR_CANLOOT:
        send_to_char("Your corpse is safe from thieves.\n\r", ch)
    else:
        send_to_char("Your corpse may be looted.\n\r", ch)
    if ch.act & C.PLR_NOSUMMON:
        send_to_char("You cannot be summoned.\n\r", ch)
    else:
        send_to_char("You can be summoned.\n\r", ch)
    if ch.act & C.PLR_NOFOLLOW:
        send_to_char("You do not welcome followers.\n\r", ch)
    else:
        send_to_char("You accept followers.\n\r", ch)


def _toggle_act(ch, bit: int, off: str, on: str) -> None:
    """The auto commands' shape: a player flag turned off (saying off) or on (saying on)."""
    if ch.is_npc:
        return
    if ch.act & bit:
        send_to_char(off, ch)
        ch.act &= ~bit
    else:
        send_to_char(on, ch)
        ch.act |= bit


def _toggle_comm(ch, bit: int, off: str, on: str) -> None:
    """The same for a comm flag, which NPCs can toggle too."""
    if ch.comm & bit:
        send_to_char(off, ch)
        ch.comm &= ~bit
    else:
        send_to_char(on, ch)
        ch.comm |= bit


# C: act_info.c do_autoassist
def do_autoassist(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOASSIST, "Autoassist removed.\n\r", "You will now assist when needed.\n\r")


# C: act_info.c do_autoexit
def do_autoexit(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOEXIT, "Exits will no longer be displayed.\n\r", "Exits will now be displayed.\n\r")


# C: act_info.c do_autogold
def do_autogold(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOGOLD, "Autogold removed.\n\r", "Automatic gold looting set.\n\r")


# C: act_info.c do_autoloot
def do_autoloot(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOLOOT, "Autolooting removed.\n\r", "Automatic corpse looting set.\n\r")


# C: act_info.c do_autosac
def do_autosac(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOSAC, "Autosacrificing removed.\n\r", "Automatic corpse sacrificing set.\n\r")


# C: act_info.c do_autosplit
def do_autosplit(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_AUTOSPLIT, "Autosplitting removed.\n\r", "Automatic gold splitting set.\n\r")


_AUTOS = (C.PLR_AUTOASSIST | C.PLR_AUTOEXIT | C.PLR_AUTOGOLD | C.PLR_AUTOLOOT | C.PLR_AUTOSAC
          | C.PLR_AUTOSPLIT)


# C: act_info.c do_autoall
def do_autoall(ch, argument: str) -> None:
    if ch.is_npc:
        return
    if argument == "on":  # strcmp: case matters, and the whole argument
        ch.act |= _AUTOS
        send_to_char("All autos turned on.\n\r", ch)
    elif argument == "off":
        ch.act &= ~_AUTOS
        send_to_char("All autos turned off.\n\r", ch)
    else:
        send_to_char("Usage: autoall [on|off]\n\r", ch)


# C: act_info.c do_brief
def do_brief(ch, argument: str) -> None:
    _toggle_comm(ch, C.COMM_BRIEF, "Full descriptions activated.\n\r", "Short descriptions activated.\n\r")


# C: act_info.c do_compact
def do_compact(ch, argument: str) -> None:
    _toggle_comm(ch, C.COMM_COMPACT, "Compact mode removed.\n\r", "Compact mode set.\n\r")


# C: act_info.c do_show
def do_show(ch, argument: str) -> None:
    _toggle_comm(ch, C.COMM_SHOW_AFFECTS, "Affects will no longer be shown in score.\n\r",
                 "Affects will now be shown in score.\n\r")


# C: act_info.c do_combine
def do_combine(ch, argument: str) -> None:
    _toggle_comm(ch, C.COMM_COMBINE, "Long inventory selected.\n\r", "Combined inventory selected.\n\r")


# C: act_info.c do_noloot
def do_noloot(ch, argument: str) -> None:
    _toggle_act(ch, C.PLR_CANLOOT, "Your corpse is now safe from thieves.\n\r", "Your corpse may now be looted.\n\r")


# C: act_info.c do_nofollow
def do_nofollow(ch, argument: str) -> None:
    from charm.commands.comm import die_follower

    if ch.is_npc:
        return
    if ch.act & C.PLR_NOFOLLOW:
        send_to_char("You now accept followers.\n\r", ch)
        ch.act &= ~C.PLR_NOFOLLOW
    else:
        send_to_char("You no longer accept followers.\n\r", ch)
        ch.act |= C.PLR_NOFOLLOW
        die_follower(game_module.current, ch)


# C: act_info.c do_nosummon
def do_nosummon(ch, argument: str) -> None:
    off, on = "You are no longer immune to summon.\n\r", "You are now immune to summoning.\n\r"
    if ch.is_npc:
        if ch.imm_flags & C.IMM_SUMMON:
            send_to_char(off, ch)
            ch.imm_flags &= ~C.IMM_SUMMON
        else:
            send_to_char(on, ch)
            ch.imm_flags |= C.IMM_SUMMON
    else:
        _toggle_act(ch, C.PLR_NOSUMMON, off, on)


# C: act_info.c do_read
def do_read(ch, argument: str) -> None:
    do_look(ch, argument)


# C: act_info.c do_examine
def do_examine(ch, argument: str) -> None:
    from charm.entities.handler import get_obj_here

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Examine what?\n\r", ch)
        return
    do_look(ch, arg)
    obj = get_obj_here(ch, arg)
    if obj is None:
        return
    if obj.item_type == C.ITEM_JUKEBOX:
        from charm.systems.music import do_play

        do_play(ch, "list")
    elif obj.item_type == C.ITEM_MONEY:
        silver, gold = obj.value[0], obj.value[1]
        if silver == 0:
            if gold == 0:
                buf = "Odd...there's no coins in the pile.\n\r"
            elif gold == 1:
                buf = "Wow. One gold coin.\n\r"
            else:
                buf = "There are %d gold coins in the pile.\n\r" % gold
        elif gold == 0:
            if silver == 1:
                buf = "Wow. One silver coin.\n\r"
            else:
                buf = "There are %d silver coins in the pile.\n\r" % silver
        else:
            buf = "There are %d gold and %d silver coins in the pile.\n\r" % (gold, silver)
        send_to_char(buf, ch)
    elif obj.item_type in (C.ITEM_DRINK_CON, C.ITEM_CONTAINER, C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC):
        do_look(ch, "in %s" % argument)  # the whole argument, not just its first word


# C: act_info.c do_worth
def do_worth(ch, argument: str) -> None:
    from charm.systems.skills import exp_per_level

    if ch.is_npc:
        send_to_char("You have %d gold and %d silver.\n\r" % (ch.gold, ch.silver), ch)
        return
    send_to_char("You have %d gold, %d silver, and %d experience (%d exp to level).\n\r"
                 % (ch.gold, ch.silver, ch.exp, (ch.level + 1) * exp_per_level(ch, ch.pcdata.points) - ch.exp), ch)


DAY_NAME = ("the Moon", "the Bull", "Deception", "Thunder", "Freedom", "the Great Gods", "the Sun")
MONTH_NAME = (
    "Winter", "the Winter Wolf", "the Frost Giant", "the Old Forces", "the Grand Struggle", "the Spring", "Nature",
    "Futility", "the Dragon", "the Sun", "the Heat", "the Battle", "the Dark Shades", "the Shadows",
    "the Long Shadows", "the Ancient Darkness", "the Great Evil",
)


# C: act_info.c do_time
def do_time(ch, argument: str) -> None:
    from charm.core.log import ctime

    game = game_module.current
    t = game.time_info
    day = t.day + 1
    if 4 < day < 20:
        suf = "th"
    elif day % 10 == 1:  # non-negative: a day of the month
        suf = "st"
    elif day % 10 == 2:  # non-negative: a day of the month
        suf = "nd"
    elif day % 10 == 3:  # non-negative: a day of the month
        suf = "rd"
    else:
        suf = "th"
    hour = 12 if t.hour % 12 == 0 else t.hour % 12  # non-negative: an hour of the day
    send_to_char("It is %d o'clock %s, Day of %s, %d%s the Month of %s.\n\r"
                 % (hour, "pm" if t.hour >= 12 else "am", DAY_NAME[day % 7], day, suf,  # non-negative: a day
                    MONTH_NAME[t.month]), ch)
    send_to_char("Charm started up at %s\n\rThe system time is %s.\n\r"
                 % (game.str_boot_time, ctime(game.current_time)), ch)


_SKY_LOOK = ("cloudless", "cloudy", "rainy", "lit by flashes of lightning")


# C: act_info.c do_weather
def do_weather(ch, argument: str) -> None:
    if ch.in_room.room_flags & C.ROOM_INDOORS:  # !IS_OUTSIDE
        send_to_char("You can't see the weather indoors.\n\r", ch)
        return
    w = game_module.current.weather_info
    send_to_char("The sky is %s and %s.\n\r"
                 % (_SKY_LOOK[w.sky], "a warm southerly breeze blows" if w.change >= 0
                    else "a cold northern gust blows"), ch)


def _who_class(wch) -> str:
    """The class column of who and whois: the class's, or the immortal rank at the top nine levels."""
    from charm.data.classes import CLASS_TABLE

    ranks = ("IMP", "CRE", "SUP", "DEI", "GOD", "IMM", "DEM", "ANG", "AVA")
    below = C.MAX_LEVEL - wch.level
    return ranks[below] if 0 <= below < len(ranks) else CLASS_TABLE[wch.class_].who_name


def _who_line(wch) -> str:
    from charm.data.clans import CLAN_TABLE
    from charm.data.races import PC_RACE_TABLE

    return "[%2d %6s %s] %s%s%s%s%s%s%s%s\n\r" % (
        wch.level, PC_RACE_TABLE[wch.race].who_name if wch.race < C.MAX_PC_RACE else "     ", _who_class(wch),
        "(Incog) " if wch.incog_level >= C.LEVEL_HERO else "", "(Wizi) " if wch.invis_level >= C.LEVEL_HERO else "",
        CLAN_TABLE[wch.clan].who_name, "[AFK] " if wch.comm & C.COMM_AFK else "",
        "(KILLER) " if wch.act & C.PLR_KILLER else "", "(THIEF) " if wch.act & C.PLR_THIEF else "",
        wch.name, "" if wch.is_npc else wch.pcdata.title)


# C: act_info.c do_whois
def do_whois(ch, argument: str) -> None:
    from charm.core.strings import str_prefix
    from charm.entities.handler import can_see

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("You must provide a name.\n\r", ch)
        return
    output = []
    for d in list(game_module.current.descriptor_list):
        if d.connected != C.CON_PLAYING or not can_see(ch, d.character):
            continue
        wch = d.original if d.original is not None else d.character
        if not can_see(ch, wch):
            continue
        if str_prefix(arg, wch.name):
            output.append(_who_line(wch))
    if not output:
        send_to_char("No one of that name is playing.\n\r", ch)
        return
    page_to_char("".join(output), ch)


# C: act_info.c do_who
def do_who(ch, argument: str) -> None:
    from charm.commands.interp import is_number
    from charm.core.strings import atoi, str_prefix
    from charm.entities.handler import can_see, is_clan
    from charm.world.lookup import clan_lookup, class_lookup, race_lookup

    level_lower, level_upper = 0, C.MAX_LEVEL
    classes, races, clans = set(), set(), set()
    f_clan = f_immortal_only = False
    n_number = 0
    while True:
        argument, arg = one_argument(argument)
        if arg == "":
            break
        if is_number(arg):
            n_number += 1
            if n_number == 1:
                level_lower = atoi(arg)
            elif n_number == 2:
                level_upper = atoi(arg)
            else:
                send_to_char("Only two level numbers allowed.\n\r", ch)
                return
        elif str_prefix(arg, "immortals"):
            f_immortal_only = True
        else:
            i_class = class_lookup(arg)
            if i_class != -1:
                classes.add(i_class)
                continue
            i_race = race_lookup(arg)
            if i_race != 0 and i_race < C.MAX_PC_RACE:
                races.add(i_race)
                continue
            if str_prefix(arg, "clan"):
                f_clan = True
                continue
            i_clan = clan_lookup(arg)
            if not i_clan:
                send_to_char("That's not a valid race, class, or clan.\n\r", ch)
                return
            clans.add(i_clan)

    output, n_match = [], 0
    for d in list(game_module.current.descriptor_list):
        # "Check for match against restrictions. Don't use trust as that exposes trusted mortals."
        if d.connected != C.CON_PLAYING or not can_see(ch, d.character):
            continue
        wch = d.original if d.original is not None else d.character
        if not can_see(ch, wch):
            continue
        if (wch.level < level_lower or wch.level > level_upper
                or (f_immortal_only and wch.level < C.LEVEL_IMMORTAL)
                or (classes and wch.class_ not in classes)
                or (races and wch.race not in races)
                or (f_clan and not is_clan(wch))
                or (clans and wch.clan not in clans)):
            continue
        n_match += 1
        output.append(_who_line(wch))
    output.append("\n\rPlayers found: %d\n\r" % n_match)
    page_to_char("".join(output), ch)


# C: act_info.c do_count
def do_count(ch, argument: str) -> None:
    from charm.entities.handler import can_see

    game = game_module.current
    count = sum(1 for d in game.descriptor_list if d.connected == C.CON_PLAYING and can_see(ch, d.character))
    game.max_on = max(count, game.max_on)
    if game.max_on == count:
        send_to_char("There are %d characters on, the most so far today.\n\r" % count, ch)
    else:
        send_to_char("There are %d characters on, the most on today was %d.\n\r" % (count, game.max_on), ch)


# C: act_info.c do_inventory
def do_inventory(ch, argument: str) -> None:
    send_to_char("You are carrying:\n\r", ch)
    show_list_to_char(ch.carrying, ch, True, True)


# C: act_info.c do_equipment
def do_equipment(ch, argument: str) -> None:
    from charm.entities.handler import can_see_obj, get_eq_char

    send_to_char("You are using:\n\r", ch)
    found = False
    for i_wear in range(C.MAX_WEAR):
        obj = get_eq_char(ch, i_wear)
        if obj is None:
            continue
        send_to_char(WHERE_NAME[i_wear], ch)
        if can_see_obj(ch, obj):
            send_to_char(format_obj_to_char(obj, ch, True), ch)
            send_to_char("\n\r", ch)
        else:
            send_to_char("something.\n\r", ch)
        found = True
    if not found:
        send_to_char("Nothing.\n\r", ch)


def _compare_value(obj) -> int:
    if obj.item_type == C.ITEM_ARMOR:
        return obj.value[0] + obj.value[1] + obj.value[2]
    if obj.index.new_format:
        return (1 + obj.value[2]) * obj.value[1]
    return obj.value[1] + obj.value[2]


# C: act_info.c do_compare
def do_compare(ch, argument: str) -> None:
    from charm.entities.handler import can_see_obj, get_obj_carry
    from charm.net.act import act

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "":
        send_to_char("Compare what to what?\n\r", ch)
        return
    obj1 = get_obj_carry(ch, arg1, ch)
    if obj1 is None:
        send_to_char("You do not have that item.\n\r", ch)
        return
    if arg2 == "":
        obj2 = next((o for o in ch.carrying
                     if o.wear_loc != C.WEAR_NONE and can_see_obj(ch, o) and obj1.item_type == o.item_type
                     and obj1.wear_flags & o.wear_flags & ~C.ITEM_TAKE), None)
        if obj2 is None:
            send_to_char("You aren't wearing anything comparable.\n\r", ch)
            return
    else:
        obj2 = get_obj_carry(ch, arg2, ch)
        if obj2 is None:
            send_to_char("You do not have that item.\n\r", ch)
            return
    msg = None
    value1 = value2 = 0
    if obj1 is obj2:
        msg = "You compare $p to itself.  It looks about the same."
    elif obj1.item_type != obj2.item_type or obj1.item_type not in (C.ITEM_ARMOR, C.ITEM_WEAPON):
        msg = "You can't compare $p and $P."
    else:
        value1, value2 = _compare_value(obj1), _compare_value(obj2)
    if msg is None:
        if value1 == value2:
            msg = "$p and $P look about the same."
        elif value1 > value2:
            msg = "$p looks better than $P."
        else:
            msg = "$p looks worse than $P."
    act(msg, ch, obj1, obj2, C.TO_CHAR)


# C: act_info.c do_credits
def do_credits(ch, argument: str) -> None:
    do_help(ch, "diku")


# C: act_info.c do_where
def do_where(ch, argument: str) -> None:
    from charm.entities.handler import can_see, is_affected, is_name, is_room_owner, pers, room_is_private
    from charm.net.act import act

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Players near you:\n\r", ch)
        found = False
        for d in list(game.descriptor_list):
            victim = d.character
            if (d.connected == C.CON_PLAYING and victim is not None and not victim.is_npc
                    and victim.in_room is not None and not victim.in_room.room_flags & C.ROOM_NOWHERE
                    and (is_room_owner(ch, victim.in_room) or not room_is_private(victim.in_room))
                    and victim.in_room.area is ch.in_room.area and can_see(ch, victim)):
                found = True
                send_to_char("%-28s %s\n\r" % (victim.name, victim.in_room.name), ch)
        if not found:
            send_to_char("None\n\r", ch)
        return
    for victim in list(game.char_list):
        if (victim.in_room is not None and victim.in_room.area is ch.in_room.area
                and not is_affected(victim, C.AFF_HIDE) and not is_affected(victim, C.AFF_SNEAK)
                and can_see(ch, victim) and is_name(arg, victim.name)):
            send_to_char("%-28s %s\n\r" % (pers(victim, ch), victim.in_room.name), ch)
            return
    act("You didn't find any $T.", ch, None, arg, C.TO_CHAR)


# C: act_info.c do_consider
def do_consider(ch, argument: str) -> None:
    from charm.entities.handler import get_char_room
    from charm.net.act import act
    from charm.systems.fight import is_safe

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Consider killing whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They're not here.\n\r", ch)
        return
    if is_safe(ch, victim):
        send_to_char("Don't even think about it.\n\r", ch)
        return
    diff = victim.level - ch.level
    if diff <= -10:
        msg = "You can kill $N naked and weaponless."
    elif diff <= -5:
        msg = "$N is no match for you."
    elif diff <= -2:
        msg = "$N looks like an easy kill."
    elif diff <= 1:
        msg = "The perfect match!"
    elif diff <= 4:
        msg = "$N says 'Do you feel lucky, punk?'."
    elif diff <= 9:
        msg = "$N laughs at you mercilessly."
    else:
        msg = "Death will thank you for your gift."
    act(msg, ch, None, victim, C.TO_CHAR)


# C: act_info.c do_description
def do_description(ch, argument: str) -> None:
    from charm.commands.interp import SPACE
    from charm.core.strings import smash_tilde

    if argument != "":
        buf = ""
        # sic: smashed before the '-' test, so a leading "~" becomes "-" and takes a line off (#46)
        argument = smash_tilde(argument)
        if argument[0] == "-":
            if not ch.description:
                send_to_char("No lines left to remove.\n\r", ch)
                return
            buf = ch.description
            found = False
            i = len(buf)  # the C starts at the terminating NUL, and never looks at buf[0]
            while i > 0:
                if i < len(buf) and buf[i] == "\r":
                    if not found:  # "back it up"
                        i -= 1
                        found = True
                    else:  # "found the second one"
                        ch.description = buf[:i + 1]
                        send_to_char("Your description is:\n\r", ch)
                        send_to_char(ch.description, ch)
                        return
                i -= 1
            ch.description = ""
            send_to_char("Description cleared.\n\r", ch)
            return
        if argument[0] == "+":
            buf += ch.description
            argument = argument[1:].lstrip(SPACE)
        if len(buf) >= 1024:
            send_to_char("Description too long.\n\r", ch)
            return
        ch.description = buf + argument + "\n\r"
    send_to_char("Your description is:\n\r", ch)
    send_to_char(ch.description, ch)  # the C's "(None)." is for a NULL description, which str_dup never makes


# C: act_info.c do_report
def do_report(ch, argument: str) -> None:
    from charm.net.act import act

    points = (ch.hit, ch.max_hit, ch.mana, ch.max_mana, ch.move, ch.max_move, ch.exp)
    send_to_char("You say 'I have %d/%d hp %d/%d mana %d/%d mv %d xp.'\n\r" % points, ch)
    act("$n says 'I have %d/%d hp %d/%d mana %d/%d mv %d xp.'" % points, ch, None, None, C.TO_ROOM)


# C: act_info.c do_practice
def do_practice(ch, argument: str) -> None:
    from charm.core.cint import c_div
    from charm.data.attributes import INT_APP
    from charm.data.classes import CLASS_TABLE
    from charm.data.skills import SKILL_TABLE
    from charm.entities.handler import get_curr_stat, is_awake
    from charm.net.act import act
    from charm.world.lookup import find_spell

    if ch.is_npc:
        return
    learned = ch.pcdata.learned
    if argument == "":
        col = 0
        for sn, skill in enumerate(SKILL_TABLE[:C.MAX_SKILL]):
            if ch.level < skill.skill_level[ch.class_] or learned[sn] < 1:  # "skill is not known"
                continue
            send_to_char("%-18s %3d%%  " % (skill.name, learned[sn]), ch)
            col += 1
            if col % 3 == 0:  # non-negative: a count
                send_to_char("\n\r", ch)
        if col % 3 != 0:  # non-negative: a count
            send_to_char("\n\r", ch)
        send_to_char("You have %d practice sessions left.\n\r" % ch.practice, ch)
        return

    if not is_awake(ch):
        send_to_char("In your dreams, or what?\n\r", ch)
        return
    if not any(mob.is_npc and mob.act & C.ACT_PRACTICE for mob in ch.in_room.people):
        send_to_char("You can't do that here.\n\r", ch)
        return
    if ch.practice <= 0:
        send_to_char("You have no practice sessions left.\n\r", ch)
        return
    sn = find_spell(ch, argument)
    if sn < 0 or (not ch.is_npc and (ch.level < SKILL_TABLE[sn].skill_level[ch.class_] or learned[sn] < 1
                                     or SKILL_TABLE[sn].rating[ch.class_] == 0)):
        send_to_char("You can't practice that.\n\r", ch)
        return
    adept = 100 if ch.is_npc else CLASS_TABLE[ch.class_].skill_adept
    name = SKILL_TABLE[sn].name
    if learned[sn] >= adept:
        send_to_char("You are already learned at %s.\n\r" % name, ch)
        return
    ch.practice -= 1
    learned[sn] += c_div(INT_APP[get_curr_stat(ch, C.STAT_INT)].learn, SKILL_TABLE[sn].rating[ch.class_])
    if learned[sn] < adept:
        act("You practice $T.", ch, None, name, C.TO_CHAR)
        act("$n practices $T.", ch, None, name, C.TO_ROOM)
    else:
        learned[sn] = adept
        act("You are now learned at $T.", ch, None, name, C.TO_CHAR)
        act("$n is now learned at $T.", ch, None, name, C.TO_ROOM)


# C: act_info.c do_wimpy
def do_wimpy(ch, argument: str) -> None:
    from charm.core.cint import c_div
    from charm.core.strings import atoi

    _, arg = one_argument(argument)
    wimpy = c_div(ch.max_hit, 5) if arg == "" else atoi(arg)  # sic: no is_number check, so "foo" is 0 (#47)
    if wimpy < 0:
        send_to_char("Your courage exceeds your wisdom.\n\r", ch)
        return
    if wimpy > c_div(ch.max_hit, 2):
        send_to_char("Such cowardice ill becomes you.\n\r", ch)
        return
    ch.wimpy = wimpy
    send_to_char("Wimpy set to %d hit points.\n\r" % wimpy, ch)


def _password_argument(argument: str) -> tuple[str, str]:
    """one_argument without lower-casing: "Can't use one_argument here because it smashes case." (the rest, the
    argument). Unlike one_argument, it skips the spaces before the argument, not after it."""
    from charm.commands.interp import SPACE

    i, n = 0, len(argument)
    while i < n and argument[i] in SPACE:
        i += 1
    end = " "
    if i < n and argument[i] in "'\"":
        end = argument[i]
        i += 1
    start = i
    while i < n:
        if argument[i] == end:
            return argument[i + 1:], argument[start:i]
        i += 1
    return "", argument[start:]


# C: act_info.c do_password
def do_password(ch, argument: str) -> None:
    from charm.commands.comm import wait_state
    from charm.core.crypt import crypt
    from charm.persist.player import save_char_obj

    if ch.is_npc:
        return
    argument, arg1 = _password_argument(argument)
    argument, arg2 = _password_argument(argument)
    if arg1 == "" or arg2 == "":
        send_to_char("Syntax: password <old> <new>.\n\r", ch)
        return
    if crypt(arg1, ch.pcdata.pwd) != ch.pcdata.pwd:
        wait_state(ch, 40)
        send_to_char("Wrong password.  Wait 10 seconds.\n\r", ch)
        return
    if len(arg2) < 5:
        send_to_char("New password must be at least five characters long.\n\r", ch)
        return
    # "No tilde allowed because of player file format."
    pwdnew = crypt(arg2, ch.name)
    if "~" in pwdnew:
        send_to_char("New password not acceptable, try again.\n\r", ch)
        return
    ch.pcdata.pwd = pwdnew
    save_char_obj(game_module.current, ch)
    send_to_char("Ok.\n\r", ch)


# C: act_info.c do_telnetga
def do_telnetga(ch, argument: str) -> None:
    if ch.is_npc:
        return
    _toggle_comm(ch, C.COMM_TELNET_GA, "Telnet GA removed.\n\r", "Telnet GA enabled.\n\r")


# C: db.c do_areas
def do_areas(ch, argument: str) -> None:
    """The areas' credits in two columns: the first half of the area list, then the second beside it."""
    from charm.entities import game as game_module
    from charm.olc.save import _s

    if argument != "":
        send_to_char("No argument is used with this command.\n\r", ch)
        return
    areas = game_module.current.index.areas
    half = (len(areas) + 1) // 2  # non-negative: a count
    for k in range(half):
        right = areas[k + half] if k + half < len(areas) else None
        send_to_char("%-39s%-39s\n\r" % (_s(areas[k].credits), _s(right.credits) if right is not None else ""), ch)


def _python_blocks() -> tuple[int, int]:
    """Python's own figures for memory's "Perms" line, a difference kept on purpose (#91, decision 6): the objects
    the garbage collector knows of, and their sizes. The C counts its alloc_perm blocks, which Python has none of."""
    import gc

    objects = gc.get_objects()
    return len(objects), sum(sys.getsizeof(o) for o in objects)


# C: db.c do_memory
def do_memory(ch, argument: str) -> None:
    """The world's allocation counts, as the C keeps them (Game.top), the boot's string space, and (kept
    different) Python's objects in the Perms line."""
    from charm.entities import game as game_module

    game = game_module.current
    t = game.top
    for label, value in (("Affects", t.affects), ("Areas", t.areas), ("ExDes", t.extra_descr), ("Exits", t.exits),
                         ("Helps", t.helps), ("Socials", t.socials)):
        send_to_char("%-7s %5d\n\r" % (label, value), ch)
    send_to_char("Mobs    %5d(%d new format)\n\r" % (t.mobs, t.mobs_new), ch)
    send_to_char("(in use)%5d\n\r" % game.mobile_count, ch)
    send_to_char("Objs    %5d(%d new format)\n\r" % (t.objects, t.objects_new), ch)
    for label, value in (("Resets", t.resets), ("Rooms", t.rooms), ("Shops", t.shops)):
        send_to_char("%-7s %5d\n\r" % (label, value), ch)
    send_to_char("Strings %5d strings of %7d bytes (max %d).\n\r" % (t.strings, t.string_bytes, 1413120), ch)
    send_to_char("Perms   %5d blocks  of %7d bytes.\n\r" % _python_blocks(), ch)


# C: db.c do_dump
def do_dump(ch, argument: str) -> None:
    """mem.dmp, mob.dmp and obj.dmp, and nothing said. mob.dmp and obj.dmp are as the C writes them. mem.dmp has
    the C's counts, but its byte figures are Python's (a count times one object's size) and its free lists are
    empty: a difference kept on purpose (#91, decision 6), as the C's come from sizeof and its free lists."""
    from charm.core.errors import CWouldCrash
    from charm.entities import game as game_module
    from charm.entities.game import c_path

    game = game_module.current
    index = game.index

    def write(name: str, text: str) -> None:
        try:
            c_path(game, name).write_bytes(text.encode("latin-1"))
        except OSError:
            raise CWouldCrash(f"db.c do_dump: can't open {name}, and fprintf gets a NULL file") from None

    def size(things) -> int:
        return sys.getsizeof(things[0]) if things else 0

    chars, protos, objs = game.char_list, list(index.objs.values()), game.object_list
    pcs = sum(1 for c in chars if c.pcdata is not None)
    affects = (sum(len(c.affected) for c in chars) + sum(len(p.affected) for p in protos)
               + sum(len(o.affected) for o in objs))
    all_affects = ([a for c in chars for a in c.affected] + [a for p in protos for a in p.affected]
                   + [a for o in objs for a in o.affected])
    mobs = list(index.mobs.values())
    rooms = list(index.rooms.values())
    exits = [e for r in rooms for e in r.exit if e is not None]
    pcdata = [c.pcdata for c in chars if c.pcdata is not None]
    out = ["MobProt    %4d (%8d bytes)\n" % (game.top.mobs, game.top.mobs * size(mobs)),
           "Mobs    %4d (%8d bytes), %2d free (%d bytes)\n" % (len(chars), len(chars) * size(chars), 0, 0),
           "Pcdata    %4d (%8d bytes), %2d free (%d bytes)\n" % (pcs, pcs * size(pcdata), 0, 0),
           "Descs    %4d (%8d bytes), %2d free (%d bytes)\n" % (len(game.descriptor_list), len(game.descriptor_list)
                                                              * size(game.descriptor_list), 0, 0),
           "ObjProt    %4d (%8d bytes)\n" % (game.top.objects, game.top.objects * size(protos)),
           "Objs    %4d (%8d bytes), %2d free (%d bytes)\n" % (len(objs), len(objs) * size(objs), 0, 0),
           "Affects    %4d (%8d bytes), %2d free (%d bytes)\n" % (affects, affects * size(all_affects), 0, 0),
           "Rooms    %4d (%8d bytes)\n" % (game.top.rooms, game.top.rooms * size(rooms)),
           "Exits    %4d (%8d bytes)\n" % (game.top.exits, game.top.exits * size(exits))]
    write("mem.dmp", "".join(out))
    # "start printing out mobile data": every prototype, by vnum
    write("mob.dmp", "\nMobile Analysis\n---------------\n" + "".join(
        "#%-4d %3d active %3d killed     %s\n" % (p.vnum, p.count, p.killed, p.short_descr)
        for _, p in sorted(index.mobs.items())))
    write("obj.dmp", "\nObject Analysis\n---------------\n" + "".join(
        "#%-4d %3d active %3d reset      %s\n" % (p.vnum, p.count, p.reset_num, p.short_descr)
        for _, p in sorted(index.objs.items())))
