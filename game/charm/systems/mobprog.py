"""mob_prog.c: the mob program interpreter (program_flow, its if-checks in cmd_eval and its $-codes in expand_arg)
and the triggers that start a program (#74, P4 PR 7).

A program's lines are commands the mob runs through interpret, if-checks (if, or, and, else, endif) that pick
which, break or end, and comments (*). A line starting "mob" is a mob command (mob_cmds.c's mob_interpret, in
charm.systems.mobcmds).

The C's static call_level is Game.mprog_call_level.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mob_prog.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.cint import c_div, int32, sh_int
from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.core.rng import number_percent
from charm.core.strings import atoi, str_cmp
from charm.data import constants as C

# fn_keyword: the if-checks, by number (CHK_RAND is 0 ... CHK_GRPSIZE is 51)
FN_KEYWORD = (
    "rand", "mobhere", "objhere", "mobexists", "objexists", "people", "players", "mobs", "clones", "order", "hour",
    "ispc", "isnpc", "isgood", "isevil", "isneutral", "isimmort", "ischarm", "isfollow", "isactive", "isdelay",
    "isvisible", "hastarget", "istarget", "exists", "affected", "act", "off", "imm", "carries", "wears", "has", "uses",
    "name", "pos", "clan", "race", "class", "objtype", "vnum", "hpcnt", "room", "sex", "level", "align", "money",
    "objval0", "objval1", "objval2", "objval3", "objval4", "grpsize",
)
(CHK_RAND, CHK_MOBHERE, CHK_OBJHERE, CHK_MOBEXISTS, CHK_OBJEXISTS, CHK_PEOPLE, CHK_PLAYERS, CHK_MOBS, CHK_CLONES,
 CHK_ORDER, CHK_HOUR, CHK_ISPC, CHK_ISNPC, CHK_ISGOOD, CHK_ISEVIL, CHK_ISNEUTRAL, CHK_ISIMMORT, CHK_ISCHARM,
 CHK_ISFOLLOW, CHK_ISACTIVE, CHK_ISDELAY, CHK_ISVISIBLE, CHK_HASTARGET, CHK_ISTARGET, CHK_EXISTS, CHK_AFFECTED,
 CHK_ACT, CHK_OFF, CHK_IMM, CHK_CARRIES, CHK_WEARS, CHK_HAS, CHK_USES, CHK_NAME, CHK_POS, CHK_CLAN, CHK_RACE,
 CHK_CLASS, CHK_OBJTYPE, CHK_VNUM, CHK_HPCNT, CHK_ROOM, CHK_SEX, CHK_LEVEL, CHK_ALIGN, CHK_MONEY, CHK_OBJVAL0,
 CHK_OBJVAL1, CHK_OBJVAL2, CHK_OBJVAL3, CHK_OBJVAL4, CHK_GRPSIZE) = range(52)

FN_EVALS = ("==", ">=", "<=", ">", "<", "!=")
EVAL_EQ, EVAL_GE, EVAL_LE, EVAL_GT, EVAL_LT, EVAL_NE = range(6)

MAX_NESTED_LEVEL = 12  # "Maximum nested if-else-endif's (stack size)"
BEGIN_BLOCK, IN_BLOCK, END_BLOCK = 0, -1, -2
MAX_CALL_LEVEL = 5  # "Maximum nested calls"

_WS = " \t\n\r\v\f"  # C isspace


def _game():
    from charm.entities import game as game_module

    return game_module.current


def _char(x, code: str):
    """(CHAR_DATA *) arg2, used: a character, or nothing. Anything else is the C reading an object or a string as a
    character."""
    from charm.entities.things import Char

    if x is None or isinstance(x, Char):
        return x
    raise CWouldCrash(f"mob_prog.c: ${code} is a character, but the trigger's argument isn't one")


def _obj(x, code: str):
    from charm.entities.things import Obj

    if x is None or isinstance(x, Obj):
        return x
    raise CWouldCrash(f"mob_prog.c: ${code} is an object, but the trigger's argument isn't one")


def has_trigger(mob, trig: int) -> bool:
    """HAS_TRIGGER."""
    return bool(mob.index.mprog_flags & trig)


# C: mob_prog.c keyword_lookup
def keyword_lookup(table: tuple, keyword: str) -> int:
    for i, word in enumerate(table):
        if str_cmp(word, keyword):
            return i
    return -1


# C: mob_prog.c num_eval
def num_eval(lval: int, oper: int, rval: int) -> bool:
    if oper == EVAL_EQ:
        return lval == rval
    if oper == EVAL_GE:
        return lval >= rval
    if oper == EVAL_LE:
        return lval <= rval
    if oper == EVAL_NE:
        return lval != rval
    if oper == EVAL_GT:
        return lval > rval
    if oper == EVAL_LT:
        return lval < rval
    bug("num_eval: invalid oper", 0)
    return False


# C: mob_prog.c get_random_char
def get_random_char(mob):
    """"Get a random PC in the room (for $r parameter)": the one who draws the highest number_percent."""
    from charm.entities.handler import can_see

    victim, highest = None, 0
    for vch in list(mob.in_room.people):
        if mob is not vch and not vch.is_npc and can_see(mob, vch):
            now = number_percent()
            if now > highest:
                victim, highest = vch, now
    return victim


# C: mob_prog.c count_people_room
def count_people_room(mob, i_flag: int) -> int:
    """"How many other players / mobs are there in the room. iFlag: 0: all, 1: players, 2: mobiles 3: mobs w/ same
    vnum 4: same group" (that the mob can see)."""
    from charm.commands.comm import is_same_group
    from charm.entities.handler import can_see

    count = 0
    for vch in mob.in_room.people:
        if mob is not vch and (i_flag == 0 or (i_flag == 1 and not vch.is_npc) or (i_flag == 2 and vch.is_npc)
                               or (i_flag == 3 and mob.is_npc and vch.is_npc and mob.index.vnum == vch.index.vnum)
                               or (i_flag == 4 and is_same_group(mob, vch))) and can_see(mob, vch):
            count += 1
    return count


# C: mob_prog.c get_order
def get_order(ch) -> int:
    """Where the mob comes among the mobs of its vnum in the room, from 0."""
    if not ch.is_npc:
        return 0
    i = 0
    for vch in ch.in_room.people:
        if vch is ch:
            return i
        if vch.is_npc and vch.index.vnum == ch.index.vnum:
            i += 1
    return 0


# C: mob_prog.c has_item
def has_item(ch, vnum: int, item_type: int, f_wear: bool) -> bool:
    """Does ch carry an object of that vnum (or any, -1) and type (or any, -1), worn if f_wear?"""
    vnum, item_type = sh_int(vnum), sh_int(item_type)
    for obj in ch.carrying:
        if ((vnum < 0 or obj.index.vnum == vnum) and (item_type < 0 or obj.index.item_type == item_type)
                and (not f_wear or obj.wear_loc != C.WEAR_NONE)):
            return True
    return False


# C: mob_prog.c get_mob_vnum_room
def get_mob_vnum_room(ch, vnum: int) -> bool:
    vnum = sh_int(vnum)
    return any(mob.is_npc and mob.index.vnum == vnum for mob in ch.in_room.people)


# C: mob_prog.c get_obj_vnum_room
def get_obj_vnum_room(ch, vnum: int) -> bool:
    vnum = sh_int(vnum)
    return any(obj.index.vnum == vnum for obj in ch.in_room.contents)


def _syntax(vnum: int, n: str, original: str) -> bool:
    # error(5)'s message has a colon the others don't
    fmt = "Cmd_eval: prog %d syntax error(5): '%s'" if n == "5" else "Cmd_eval: prog %d syntax error(" + n + ") '%s'"
    bug(fmt % (vnum, original), 0)  # format: sprintf
    return False


# C: mob_prog.c cmd_eval
def cmd_eval(vnum: int, line: str, check: int, mob, ch, arg1, arg2, rch) -> bool:
    """One if-check: keyword and value (if rand 30), keyword, comparison and value (if people > 2), keyword and
    actor (if isnpc $n), keyword, actor and value (if carries $n sword), or keyword, actor, comparison and value
    (if level $n >= 10)."""
    from charm.commands.interp import is_number, one_argument
    from charm.data.flags import ACT_FLAGS, AFFECT_FLAGS, IMM_FLAGS, OFF_FLAGS
    from charm.entities.handler import (can_see, can_see_obj, get_char_room, get_char_world, get_obj_carry,
                                        get_obj_here, get_obj_wear, get_obj_world, is_evil, is_good, is_immortal,
                                        is_name)
    from charm.world.lookup import class_lookup, clan_lookup, flag_lookup, item_lookup, position_lookup, race_lookup

    lval_char, lval_obj = mob, None
    lval, rval = 0, -1
    original = line
    line, buf = one_argument(line)
    if buf == "" or mob is None:
        return False

    # "If this mobile has no target, let's assume our victim is the one"
    if mob.mprog_target is None:
        mob.mprog_target = ch

    # Case 1: keyword and value
    if check == CHK_RAND:
        return atoi(buf) < number_percent()  # sic (#87): true when the roll is over the number, not under it
    if check == CHK_MOBHERE:
        if is_number(buf):
            return get_mob_vnum_room(mob, atoi(buf))
        return get_char_room(mob, buf) is not None
    if check == CHK_OBJHERE:
        if is_number(buf):
            return get_obj_vnum_room(mob, atoi(buf))
        return get_obj_here(mob, buf) is not None
    if check == CHK_MOBEXISTS:
        return get_char_world(_game(), mob, buf) is not None
    if check == CHK_OBJEXISTS:
        return get_obj_world(mob, buf) is not None
    # Case 2 begins here: "We sneakily use rval to indicate need for numeric eval..."
    if check == CHK_PEOPLE:
        rval = count_people_room(mob, 0)
    elif check == CHK_PLAYERS:
        rval = count_people_room(mob, 1)
    elif check == CHK_MOBS:
        rval = count_people_room(mob, 2)
    elif check == CHK_CLONES:
        rval = count_people_room(mob, 3)
    elif check == CHK_ORDER:
        rval = get_order(mob)
    elif check == CHK_HOUR:
        rval = _game().time_info.hour

    # "Case 2 continued: evaluate expression"
    if rval >= 0:
        oper = keyword_lookup(FN_EVALS, buf)
        if oper < 0:
            return _syntax(vnum, "2", original)
        _, buf = one_argument(line)
        return num_eval(rval, oper, atoi(buf))

    # "Case 3,4,5: Grab actors from $* codes"
    if len(buf) < 2 or buf[0] != "$":
        return _syntax(vnum, "3", original)
    code = buf[1]
    if code == "i":
        lval_char = mob
    elif code == "n":
        lval_char = ch
    elif code == "t":
        lval_char = _char(arg2, "t")
    elif code == "r":
        lval_char = get_random_char(mob) if rch is None else rch
    elif code == "o":
        lval_obj = _obj(arg1, "o")
    elif code == "p":
        lval_obj = _obj(arg2, "p")
    elif code == "q":
        lval_char = mob.mprog_target
    else:
        return _syntax(vnum, "4", original)
    # "From now on, we need an actor, so if none was found, bail out"
    if lval_char is None and lval_obj is None:
        return False

    # Case 3: keyword and actor
    if check == CHK_ISPC:
        return lval_char is not None and not lval_char.is_npc
    if check == CHK_ISNPC:
        return lval_char is not None and lval_char.is_npc
    if check == CHK_ISGOOD:
        return lval_char is not None and is_good(lval_char)
    if check == CHK_ISEVIL:
        return lval_char is not None and is_evil(lval_char)
    if check == CHK_ISNEUTRAL:
        return lval_char is not None and not is_good(lval_char) and not is_evil(lval_char)
    if check == CHK_ISIMMORT:
        return lval_char is not None and is_immortal(lval_char)
    if check == CHK_ISCHARM:  # "A relic from MERC 2.2 MOBprograms"
        return lval_char is not None and bool(lval_char.affected_by & C.AFF_CHARM)
    if check == CHK_ISFOLLOW:
        return (lval_char is not None and lval_char.master is not None
                and lval_char.master.in_room is lval_char.in_room)
    if check == CHK_ISACTIVE:
        return lval_char is not None and lval_char.position > C.POS_SLEEPING
    if check == CHK_ISDELAY:
        return lval_char is not None and lval_char.mprog_delay > 0
    if check == CHK_ISVISIBLE:
        if code in "op":
            return lval_obj is not None and can_see_obj(mob, lval_obj)
        return lval_char is not None and can_see(mob, lval_char)
    if check == CHK_HASTARGET:
        return (lval_char is not None and lval_char.mprog_target is not None
                and lval_char.in_room is lval_char.mprog_target.in_room)
    if check == CHK_ISTARGET:
        return lval_char is not None and mob.mprog_target is lval_char

    # Case 4: keyword, actor and value
    line, buf = one_argument(line)
    if check == CHK_AFFECTED:
        return lval_char is not None and bool(lval_char.affected_by & flag_lookup(buf, AFFECT_FLAGS))
    if check == CHK_ACT:
        return lval_char is not None and bool(lval_char.act & flag_lookup(buf, ACT_FLAGS))
    if check == CHK_IMM:
        return lval_char is not None and bool(lval_char.imm_flags & flag_lookup(buf, IMM_FLAGS))
    if check == CHK_OFF:
        return lval_char is not None and bool(lval_char.off_flags & flag_lookup(buf, OFF_FLAGS))
    if check == CHK_CARRIES:
        if is_number(buf):
            return lval_char is not None and has_item(lval_char, atoi(buf), -1, False)
        return lval_char is not None and get_obj_carry(lval_char, buf, lval_char) is not None
    if check == CHK_WEARS:
        if is_number(buf):
            return lval_char is not None and has_item(lval_char, atoi(buf), -1, True)
        return lval_char is not None and get_obj_wear(lval_char, buf) is not None
    if check == CHK_HAS:
        return lval_char is not None and has_item(lval_char, -1, item_lookup(buf), False)
    if check == CHK_USES:
        return lval_char is not None and has_item(lval_char, -1, item_lookup(buf), True)
    if check == CHK_NAME:
        if code in "op":
            return lval_obj is not None and is_name(buf, lval_obj.name)
        return lval_char is not None and is_name(buf, lval_char.name)
    if check == CHK_POS:
        return lval_char is not None and lval_char.position == position_lookup(buf)
    if check == CHK_CLAN:
        return lval_char is not None and lval_char.clan == clan_lookup(buf)
    if check == CHK_RACE:
        return lval_char is not None and lval_char.race == race_lookup(buf)
    if check == CHK_CLASS:
        return lval_char is not None and lval_char.class_ == class_lookup(buf)
    if check == CHK_OBJTYPE:
        return lval_obj is not None and lval_obj.item_type == item_lookup(buf)

    # Case 5: keyword, actor, comparison and value
    oper = keyword_lookup(FN_EVALS, buf)
    if oper < 0:
        return _syntax(vnum, "5", original)
    _, buf = one_argument(line)
    rval = atoi(buf)
    if check == CHK_VNUM:
        if code in "op":
            if lval_obj is not None:
                lval = lval_obj.index.vnum
        elif lval_char is not None and lval_char.is_npc:
            lval = lval_char.index.vnum
    elif check == CHK_HPCNT:
        if lval_char is not None:
            lval = c_div(lval_char.hit * 100, max(1, lval_char.max_hit))
    elif check == CHK_ROOM:
        if lval_char is not None and lval_char.in_room is not None:
            lval = lval_char.in_room.vnum
    elif check == CHK_SEX:
        if lval_char is not None:
            lval = lval_char.sex
    elif check == CHK_LEVEL:
        if lval_char is not None:
            lval = lval_char.level
    elif check == CHK_ALIGN:
        if lval_char is not None:
            lval = lval_char.alignment
    elif check == CHK_MONEY:  # "Money is converted to silver..."
        if lval_char is not None:
            lval = int32(lval_char.gold + lval_char.silver * 100)  # sic (#87): the gold, plus the silver times 100
    elif CHK_OBJVAL0 <= check <= CHK_OBJVAL4:
        if lval_obj is not None:
            lval = lval_obj.value[check - CHK_OBJVAL0]
    elif check == CHK_GRPSIZE:
        if lval_char is not None:
            lval = count_people_room(lval_char, 4)
    else:
        return False
    return num_eval(lval, oper, rval)


_HE_SHE, _HIM_HER, _HIS_HER = ("it", "he", "she"), ("it", "him", "her"), ("its", "his", "her")


def _sex(word: tuple, ch) -> str:
    return word[min(max(ch.sex, 0), 2)]  # URANGE (0, sex, 2)


# C: mob_prog.c expand_arg
def expand_arg(fmt: str, mob, ch, arg1, arg2, rch) -> str:
    """"This is a hack of act() in comm.c": a program line with its $-codes filled in, as the mob sees them."""
    from charm.commands.interp import one_argument
    from charm.entities.handler import can_see, can_see_obj
    from charm.persist.player import capitalize

    if not fmt:  # "Discard null and zero-length messages."
        return ""

    def seen(who) -> bool:
        return who is not None and can_see(mob, who)

    def first(name: str) -> str:
        return one_argument(name)[1]

    def named(who) -> str:  # $n, $t, $r, $q: the first name, capitalised, or someone
        return capitalize(first(who.name)) if seen(who) else "someone"

    def short(who) -> str:  # $N, $T, $Q: the short description or the name
        return (who.short_descr if who.is_npc else who.name) if seen(who) else "someone"

    out, k = [], 0
    while k < len(fmt):
        if fmt[k] != "$":
            out.append(fmt[k])
            k += 1
            continue
        k += 1
        if k >= len(fmt):
            raise CWouldCrash("mob_prog.c expand_arg: a $ at the end of a line reads past it")
        code = fmt[k]
        vch = _char(arg2, code) if code in "tTEMS" else None
        if code == "i":
            i = first(mob.name)
        elif code == "I":
            i = mob.short_descr
        elif code == "n":
            i = named(ch)
        elif code == "N":
            i = short(ch)
        elif code == "t":
            i = named(vch)
        elif code == "T":
            i = short(vch)
        elif code == "r":
            if rch is None:
                rch = get_random_char(mob)
            i = named(rch)
        elif code == "R":
            if rch is None:
                rch = get_random_char(mob)
            if seen(rch):
                if ch is None:
                    raise CWouldCrash("mob_prog.c expand_arg: $R reads ch, and there's no ch (#87)")
                i = ch.short_descr if ch.is_npc else ch.name  # sic (#87): ch's name, not the random character's
            else:
                i = "someone"
        elif code == "q":
            i = named(mob.mprog_target)
        elif code == "Q":
            i = short(mob.mprog_target)
        elif code == "j":
            i = _sex(_HE_SHE, mob)
        elif code == "e":
            i = _sex(_HE_SHE, ch) if seen(ch) else "someone"
        elif code == "E":
            i = _sex(_HE_SHE, vch) if seen(vch) else "someone"
        elif code == "J":
            i = _sex(_HE_SHE, rch) if seen(rch) else "someone"  # sic (#87): no random pick, unlike $r, $K and $L
        elif code == "X":
            i = _sex(_HE_SHE, mob.mprog_target) if seen(mob.mprog_target) else "someone"
        elif code == "k":
            i = _sex(_HIM_HER, mob)
        elif code == "m":
            i = _sex(_HIM_HER, ch) if seen(ch) else "someone"
        elif code == "M":
            i = _sex(_HIM_HER, vch) if seen(vch) else "someone"
        elif code == "K":
            if rch is None:
                rch = get_random_char(mob)
            i = _sex(_HIM_HER, rch) if seen(rch) else "someone"
        elif code == "Y":
            i = _sex(_HIM_HER, mob.mprog_target) if seen(mob.mprog_target) else "someone"
        elif code == "l":
            i = _sex(_HIS_HER, mob)
        elif code == "s":
            i = _sex(_HIS_HER, ch) if seen(ch) else "someone's"
        elif code == "S":
            i = _sex(_HIS_HER, vch) if seen(vch) else "someone's"
        elif code == "L":
            if rch is None:
                rch = get_random_char(mob)
            i = _sex(_HIS_HER, rch) if seen(rch) else "someone's"
        elif code == "Z":
            i = _sex(_HIS_HER, mob.mprog_target) if seen(mob.mprog_target) else "someone's"
        elif code in "oO":
            obj1 = _obj(arg1, code)
            visible = obj1 is not None and can_see_obj(mob, obj1)
            i = (first(obj1.name) if code == "o" else obj1.short_descr) if visible else "something"
        elif code in "pP":
            obj2 = _obj(arg2, code)
            visible = obj2 is not None and can_see_obj(mob, obj2)
            i = (first(obj2.name) if code == "p" else obj2.short_descr) if visible else "something"
        else:
            bug("Expand_arg: bad code %d.", ord(code))
            i = " <@@@> "
        k += 1
        out.append(i)
    text = "".join(out)
    if len(text) >= C.MAX_STRING_LENGTH:
        raise CWouldCrash("mob_prog.c expand_arg: the line is past MAX_STRING_LENGTH")
    return text


# C: mob_prog.c program_flow
def program_flow(pvnum: int, source: str, mob, ch, arg1, arg2) -> None:
    """"This is the program driver. It parses the mob program code lines and passes "executable" commands to
    interpret()". A syntax error logs a bug and ends the program, without counting the call off (sic, #87)."""
    from charm.commands.interp import interpret, one_argument

    game = _game()
    rch = None  # sic (#87): never set, so each $r picks again
    mvnum = sh_int(mob.index.vnum)
    game.mprog_call_level += 1
    if game.mprog_call_level > MAX_CALL_LEVEL:
        bug("MOBprogs: MAX_CALL_LEVEL exceeded, vnum %d", mob.index.vnum)
        return  # sic (#87): the level isn't counted back down, so no program runs again

    state = [IN_BLOCK] * MAX_NESTED_LEVEL  # "Reset "stack""
    cond = [True] * MAX_NESTED_LEVEL
    level = 0

    def misplaced(what: str) -> None:
        bug("Mobprog: %s, mob %d prog %d" % (what, mvnum, pvnum), 0)

    k, n = 0, len(source)
    while k < n:
        # "Get a command line. We sneakily get both the control word (if/and/or) and the rest of the line in one
        # pass."
        while k < n and source[k] in _WS:
            k += 1
        start, first_arg, control, data = k, True, [], []
        while k < n and source[k] not in "\n\r":
            c = source[k]
            if c in _WS:
                if first_arg:
                    first_arg = False
                else:
                    data.append(c)
            elif first_arg:
                control.append(c)
            else:
                data.append(c)
            k += 1
        buf, control, data = source[start:k], "".join(control), "".join(data)
        if len(control) >= C.MAX_INPUT_LENGTH or len(buf) >= C.MAX_STRING_LENGTH:
            raise CWouldCrash("mob_prog.c program_flow: a line or its first word overflows its buffer")

        if buf == "":
            break
        if buf[0] == "*":  # "Comment"
            continue

        line = data
        if str_cmp(control, "if"):
            if state[level] == BEGIN_BLOCK:
                misplaced("misplaced if statement")
                return
            state[level] = BEGIN_BLOCK
            level += 1
            if level >= MAX_NESTED_LEVEL:
                misplaced("Max nested level exceeded")
                return
            if level and not cond[level - 1]:
                cond[level] = False
                continue
            line, control = one_argument(line)
            check = keyword_lookup(FN_KEYWORD, control)
            if check < 0:
                misplaced("invalid if_check (if)")
                return
            cond[level] = cmd_eval(pvnum, line, check, mob, ch, arg1, arg2, rch)
            state[level] = END_BLOCK
        elif str_cmp(control, "or") or str_cmp(control, "and"):
            word = "or" if str_cmp(control, "or") else "and"
            if not level or state[level - 1] != BEGIN_BLOCK:
                misplaced(f"{word} without if")
                return
            if level and not cond[level - 1]:
                continue
            line, control = one_argument(line)
            check = keyword_lookup(FN_KEYWORD, control)
            if check < 0:
                misplaced(f"invalid if_check ({word})")
                return
            ev = cmd_eval(pvnum, line, check, mob, ch, arg1, arg2, rch)
            cond[level] = (ev or cond[level]) if word == "or" else (cond[level] and ev)
        elif str_cmp(control, "endif"):
            if not level or state[level - 1] != BEGIN_BLOCK:
                misplaced("endif without if")
                return
            cond[level] = True
            state[level] = IN_BLOCK
            level -= 1
            state[level] = END_BLOCK
        elif str_cmp(control, "else"):
            if not level or state[level - 1] != BEGIN_BLOCK:
                misplaced("else without if")
                return
            if level and not cond[level - 1]:
                continue
            state[level] = IN_BLOCK
            cond[level] = not cond[level]
        elif cond[level] and (str_cmp(control, "break") or str_cmp(control, "end")):
            game.mprog_call_level -= 1
            return
        elif (not level or cond[level]) and buf != "":
            state[level] = IN_BLOCK
            data = expand_arg(buf, mob, ch, arg1, arg2, rch)
            if str_cmp(control, "mob"):
                # "Found a mob restricted command, pass it to mob interpreter"
                from charm.systems.mobcmds import mob_interpret

                mob_interpret(mob, one_argument(data)[0])
                continue
            interpret(mob, data)  # "Found a normal mud command, pass it to interpreter"
    game.mprog_call_level -= 1


# C: mob_prog.c mp_act_trigger
def mp_act_trigger(argument: str, mob, ch, arg1, arg2, kind: int) -> None:
    if not mob.is_npc:
        return
    for prg in mob.index.mprogs:
        if prg.trig_type == kind and prg.trig_phrase in argument:
            program_flow(prg.vnum, prg.code, mob, ch, arg1, arg2)
            break


# C: mob_prog.c mp_percent_trigger
def mp_percent_trigger(mob, ch, arg1, arg2, kind: int) -> bool:
    for prg in mob.index.mprogs:
        if prg.trig_type == kind and number_percent() < atoi(prg.trig_phrase):
            program_flow(prg.vnum, prg.code, mob, ch, arg1, arg2)
            return True
    return False


# C: mob_prog.c mp_greet_trigger
def mp_greet_trigger(ch) -> None:
    from charm.entities.handler import can_see

    for mob in list(ch.in_room.people):
        if mob.is_npc and (has_trigger(mob, C.TRIG_GREET) or has_trigger(mob, C.TRIG_GRALL)):
            # "Greet trigger works only if the mobile is not busy (fighting etc.). If you want to catch all
            # players, use GrAll trigger"
            if has_trigger(mob, C.TRIG_GREET) and mob.position == mob.index.default_pos and can_see(mob, ch):
                mp_percent_trigger(mob, ch, None, None, C.TRIG_GREET)
            elif has_trigger(mob, C.TRIG_GRALL):
                mp_percent_trigger(mob, ch, None, None, C.TRIG_GRALL)


# C: mob_prog.c mp_exit_trigger
def mp_exit_trigger(ch, door: int) -> bool:
    from charm.entities.handler import can_see

    for mob in list(ch.in_room.people):
        if mob.is_npc and (has_trigger(mob, C.TRIG_EXIT) or has_trigger(mob, C.TRIG_EXALL)):
            for prg in mob.index.mprogs:
                # "Exit trigger works only if the mobile is not busy (fighting etc.). If you want to be sure all
                # players are caught, use ExAll trigger"
                if (prg.trig_type == C.TRIG_EXIT and door == atoi(prg.trig_phrase)
                        and mob.position == mob.index.default_pos and can_see(mob, ch)):
                    program_flow(prg.vnum, prg.code, mob, ch, None, None)
                    return True
                elif prg.trig_type == C.TRIG_EXALL and door == atoi(prg.trig_phrase):
                    program_flow(prg.vnum, prg.code, mob, ch, None, None)
                    return True
    return False


# C: mob_prog.c mp_bribe_trigger
def mp_bribe_trigger(mob, ch, amount: int) -> None:
    # "Original MERC 2.2 MOBprograms used to create a money object and give it to the mobile. WFT was that? Funcs
    # in act_obj() handle it just fine."
    for prg in mob.index.mprogs:
        if prg.trig_type == C.TRIG_BRIBE and amount >= atoi(prg.trig_phrase):
            program_flow(prg.vnum, prg.code, mob, ch, None, None)
            break


# C: mob_prog.c mp_give_trigger
def mp_give_trigger(mob, ch, obj) -> None:
    from charm.commands.interp import is_number, one_argument
    from charm.core.strings import str_cmp
    from charm.entities.handler import is_name

    for prg in mob.index.mprogs:
        if prg.trig_type != C.TRIG_GIVE:
            continue
        p = prg.trig_phrase
        if is_number(p):  # "Vnum argument"
            if obj.index.vnum == atoi(p):
                program_flow(prg.vnum, prg.code, mob, ch, obj, None)
                return
        else:  # "Object name argument, e.g. 'sword'"
            while p:
                p, buf = one_argument(p)
                if is_name(buf, obj.name) or str_cmp("all", buf):
                    program_flow(prg.vnum, prg.code, mob, ch, obj, None)
                    return


# C: mob_prog.c mp_hprct_trigger
def mp_hprct_trigger(mob, ch) -> None:
    from charm.core.cint import c_div

    for prg in mob.index.mprogs:
        if prg.trig_type == C.TRIG_HPCNT:
            if mob.max_hit == 0:
                from charm.core.errors import CWouldCrash

                raise CWouldCrash("mob_prog.c mp_hprct_trigger: divides by the mob's max_hit, which is 0")
            if c_div(100 * mob.hit, mob.max_hit) < atoi(prg.trig_phrase):
                program_flow(prg.vnum, prg.code, mob, ch, None, None)
                break
