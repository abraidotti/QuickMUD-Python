"""olc.c: the online builder's framework. 'edit' (do_olc) and the do_*edit commands put a connection in an editor;
while it's there, every line goes to that editor (run_olc_editor, from the game loop), which runs one of its own
commands or, failing that, the ordinary interpreter. The area and room editors are here, with the reset commands;
the others raise NotPorted.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/olc.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import interpret, is_number, one_argument
from charm.core.errors import NotPorted
from charm.core.strings import atoi, smash_tilde, str_cmp, str_prefix
from charm.data import constants as C
from charm.data import flags as F
from charm.net.output import send_to_char
from charm.olc import ED_AREA, ED_HELP, ED_MOBILE, ED_MPCODE, ED_OBJECT, ED_ROOM, act
from charm.olc.bits import flag_value


def _aedit_table():
    """aedit_table, in the C's order: the first command the word is a prefix of runs."""
    return (("age", act.aedit_age), ("builder", act.aedit_builder), ("commands", show_commands),
            ("create", act.aedit_create), ("filename", act.aedit_file), ("name", act.aedit_name),
            ("reset", act.aedit_reset), ("security", act.aedit_security), ("show", act.aedit_show),
            ("vnum", act.aedit_vnum), ("lvnum", act.aedit_lvnum), ("uvnum", act.aedit_uvnum),
            ("credits", act.aedit_credits), ("?", act.show_help), ("version", act.show_version))


def _redit_table():
    """redit_table, in the C's order."""
    return (("commands", show_commands), ("create", act.redit_create), ("desc", act.redit_desc),
            ("ed", act.redit_ed), ("format", act.redit_format), ("name", act.redit_name),
            ("show", act.redit_show), ("heal", act.redit_heal), ("mana", act.redit_mana), ("clan", act.redit_clan),
            ("north", act.redit_north), ("south", act.redit_south), ("east", act.redit_east),
            ("west", act.redit_west), ("up", act.redit_up), ("down", act.redit_down),
            # "New reset commands."
            ("mreset", act.redit_mreset), ("oreset", act.redit_oreset), ("mlist", act.redit_mlist),
            ("rlist", act.redit_rlist), ("olist", act.redit_olist), ("mshow", act.redit_mshow),
            ("oshow", act.redit_oshow), ("owner", act.redit_owner), ("room", act.redit_room),
            ("sector", act.redit_sector), ("?", act.show_help), ("version", act.show_version))


# C: olc.c olc_ed_name
def olc_ed_name(ch) -> str:
    """The prompt's %o."""
    return {ED_AREA: "AEdit", ED_ROOM: "REdit", ED_OBJECT: "OEdit", ED_MOBILE: "MEdit", ED_MPCODE: "MPEdit",
            ED_HELP: "HEdit"}.get(ch.desc.editor, " ")


# C: olc.c olc_ed_vnum
def olc_ed_vnum(ch) -> str:
    """The prompt's %O: what's being edited, by vnum (a help by its keyword)."""
    d = ch.desc
    if d.editor == ED_ROOM:
        return "%d" % (ch.in_room.vnum if ch.in_room is not None else 0)
    if d.editor == ED_HELP:
        return "%s" % (d.pEdit.keyword if d.pEdit is not None else "")
    if d.editor in (ED_AREA, ED_OBJECT, ED_MOBILE, ED_MPCODE):
        return "%d" % (d.pEdit.vnum if d.pEdit is not None else 0)
    return " "


# C: olc.c show_olc_cmds
def show_olc_cmds(ch, olc_table) -> None:
    send_to_char(act._columns([name for name, _ in olc_table], "%-15.15s", 5), ch)


# C: olc.c show_commands
def show_commands(ch, argument: str) -> bool:
    editor = ch.desc.editor
    if editor == ED_AREA:
        show_olc_cmds(ch, _aedit_table())
    elif editor == ED_ROOM:
        show_olc_cmds(ch, _redit_table())
    elif editor in (ED_OBJECT, ED_MOBILE, ED_MPCODE, ED_HELP):
        raise NotPorted(f"olc.c show_commands: editor {editor}")
    return False


# C: olc.c edit_done
def edit_done(ch) -> bool:
    ch.desc.pEdit = None
    ch.desc.editor = 0
    return False


# C: olc.c aedit
def aedit(ch, argument: str) -> None:
    """A line typed in the area editor. A word that's a prefix of an area flag's name toggles it before any
    command is looked at, so "c" toggles changed, "a" added and "n" none (bit 0: no change, "Flag toggled.")."""
    from charm.entities.handler import is_builder

    area = ch.desc.pEdit
    argument = smash_tilde(argument)
    arg = argument
    argument, command = one_argument(argument)
    if not is_builder(ch, area):
        send_to_char("AEdit:  Insufficient security to modify area.\n\r", ch)
        edit_done(ch)
        return
    if str_cmp(command, "done"):
        edit_done(ch)
        return
    if command == "":
        act.aedit_show(ch, argument)
        return
    value = flag_value(F.AREA_FLAGS, command)
    if value != C.NO_FLAG:
        area.area_flags ^= value
        send_to_char("Flag toggled.\n\r", ch)
        return
    for name, fun in _aedit_table():  # "Search Table and Dispatch Command."
        if str_prefix(command, name):
            if fun(ch, argument):
                area.area_flags |= C.AREA_CHANGED
            return
    interpret(ch, arg)  # "Default to Standard Interpreter."


# C: olc.c do_olc
def do_olc(ch, argument: str) -> None:
    from charm.commands.info import do_help

    if ch.is_npc:
        return
    argument, command = one_argument(argument)
    if command == "":
        do_help(ch, "olc")
        return
    for name, fun in (("area", "do_aedit"), ("room", "do_redit"), ("object", "do_oedit"), ("mobile", "do_medit"),
                      ("mpcode", "do_mpedit"), ("hedit", "do_hedit")):  # editor_table
        if str_prefix(command, name):
            if fun == "do_aedit":
                do_aedit(ch, argument)
            elif fun == "do_redit":
                do_redit(ch, argument)
            else:
                raise NotPorted(f"olc.c do_olc: {fun}")
            return
    do_help(ch, "olc")  # "Invalid command, send help."


# C: olc.c do_aedit
def do_aedit(ch, argument: str) -> None:
    from charm.entities.handler import is_builder
    from charm.olc.save import get_area_data

    if ch.is_npc:
        return
    area = ch.in_room.area
    argument, arg = one_argument(argument)
    if is_number(arg):
        area = get_area_data(atoi(arg))
        if area is None:
            send_to_char("That area vnum does not exist.\n\r", ch)
            return
    elif str_cmp(arg, "create"):
        if ch.pcdata.security < 9:
            send_to_char("AEdit : Insufficient security to create area.\n\r", ch)
            return
        act.aedit_create(ch, "")
        ch.desc.editor = ED_AREA
        return
    if not is_builder(ch, area):
        send_to_char("Insufficient security to edit areas.\n\r", ch)
        return
    ch.desc.pEdit = area
    ch.desc.editor = ED_AREA


# C: olc.c do_alist
def do_alist(ch, argument: str) -> None:
    from charm.olc.save import _s

    if ch.is_npc:
        return
    out = ["[%3s] [%-27s] (%-5s-%5s) [%-10s] %3s [%-10s]\n\r" % ("Num", "Area Name", "lvnum", "uvnum", "Filename",
                                                                  "Sec", "Builders")]
    for area in _game().index.areas:
        out.append("[%3d] %-29.29s (%-5d-%5d) %-12.12s [%d] [%-10.10s]\n\r"
                   % (area.vnum, _s(area.name), area.min_vnum, area.max_vnum, _s(area.file_name), area.security,
                      _s(area.builders)))
    send_to_char("".join(out), ch)


def _game():
    from charm.entities import game as game_module

    return game_module.current


# C: olc.c redit
def redit(ch, argument: str) -> None:
    """A line typed in the room editor, which edits the room the builder is in."""
    from charm.entities.handler import is_builder

    room = ch.in_room
    area = room.area
    argument = smash_tilde(argument)
    arg = argument
    argument, command = one_argument(argument)
    if not is_builder(ch, area):
        send_to_char("REdit:  Insufficient security to modify room.\n\r", ch)
        edit_done(ch)
        return
    if str_cmp(command, "done"):
        edit_done(ch)
        return
    if command == "":
        act.redit_show(ch, argument)
        return
    for name, fun in _redit_table():  # "Search Table and Dispatch Command."
        if str_prefix(command, name):
            if fun(ch, argument):
                area.area_flags |= C.AREA_CHANGED
            return
    interpret(ch, arg)  # "Default to Standard Interpreter."


# C: olc.c do_redit
def do_redit(ch, argument: str) -> None:
    from charm.entities.handler import char_from_room, char_to_room, is_builder
    from charm.entities.resets import reset_room

    if ch.is_npc:
        return
    game = _game()
    argument, arg1 = one_argument(argument)
    room = ch.in_room
    if str_cmp(arg1, "reset"):  # "redit reset"
        if not is_builder(ch, room.area):
            send_to_char("Insufficient security to modify room.\n\r", ch)
            return
        reset_room(game, room)
        send_to_char("Room reset.\n\r", ch)
        return
    if str_cmp(arg1, "create"):  # "redit create <vnum>"
        if argument == "" or atoi(argument) == 0:
            send_to_char("Syntax:  edit room create [vnum]\n\r", ch)
            return
        if act.redit_create(ch, argument):  # "pEdit == nuevo cuarto"
            ch.desc.editor = ED_ROOM
            char_from_room(ch)
            char_to_room(ch, ch.desc.pEdit)
            ch.desc.pEdit.area.area_flags |= C.AREA_CHANGED
        return
    if arg1 != "":  # "redit <vnum>"
        room = game.index.get_room_index(atoi(arg1))
        if room is None:
            send_to_char("REdit : Nonexistant room.\n\r", ch)
            return
        if not is_builder(ch, room.area):
            send_to_char("REdit : Insufficient security to modify room.\n\r", ch)
            return
        char_from_room(ch)
        char_to_room(ch, room)
    if not is_builder(ch, room.area):
        send_to_char("REdit : Insufficient security to modify room.\n\r", ch)
        return
    ch.desc.pEdit = room
    ch.desc.editor = ED_ROOM


# C: olc.c display_resets
def display_resets(ch) -> None:
    """The room's resets, numbered. A reset naming something that isn't there makes its line, which is then never
    sent (the C's continue skips the send); a give or equip names the last mob loaded."""
    from charm.commands.move import DIR_NAME
    from charm.core.errors import CWouldCrash
    from charm.olc.bits import flag_string
    from charm.olc.save import _s
    from charm.persist.player import capitalize

    index = _game().index
    room = ch.in_room
    mob = None
    send_to_char(" No.  Loads    Description       Location         Vnum   Mx Mn Description\n\r"
                 "==== ======== ============= =================== ======== ===== ===========\n\r", ch)
    for n, rs in enumerate(room.resets, 1):
        final = "[%2d] " % n
        c = rs.command
        if c == "M":
            p = index.get_mob_index(rs.arg1)
            to = index.get_room_index(rs.arg3) if p is not None else None
            if p is None or to is None:
                continue
            mob = p
            final += "M[%5d] %-13.13s in room             R[%5d] %2d-%2d %-15.15s\n\r" % (
                rs.arg1, _s(mob.short_descr), rs.arg3, rs.arg2, rs.arg4, _s(to.name))
            prev = index.get_room_index(to.vnum - 1)  # "Check for pet shop."
            if prev is not None and prev.room_flags & C.ROOM_PET_SHOP:
                final = final[:5] + "P" + final[6:]
        elif c == "O":
            p = index.get_obj_index(rs.arg1)
            to = index.get_room_index(rs.arg3) if p is not None else None
            if p is None or to is None:
                continue
            final += "O[%5d] %-13.13s in room             R[%5d]       %-15.15s\n\r" % (
                rs.arg1, _s(p.short_descr), rs.arg3, _s(to.name))
        elif c == "P":
            p = index.get_obj_index(rs.arg1)
            into = index.get_obj_index(rs.arg3) if p is not None else None
            if p is None or into is None:
                continue
            final += "O[%5d] %-13.13s inside              O[%5d] %2d-%2d %-15.15s\n\r" % (
                rs.arg1, _s(p.short_descr), rs.arg3, rs.arg2, rs.arg4, _s(into.short_descr))
        elif c in ("G", "E"):
            p = index.get_obj_index(rs.arg1)
            if p is None:
                continue
            if mob is None:
                final += "Give/Equip Object - No Previous Mobile\n\r"
            elif mob.shop is not None:
                final += "O[%5d] %-13.13s in the inventory of S[%5d]       %-15.15s\n\r" % (
                    rs.arg1, _s(p.short_descr), mob.vnum, _s(mob.short_descr))
            else:
                where = flag_string(F.WEAR_LOC_STRINGS, C.WEAR_NONE if c == "G" else rs.arg3)
                final += "O[%5d] %-13.13s %-19.19s M[%5d]       %-15.15s\n\r" % (
                    rs.arg1, _s(p.short_descr), where, mob.vnum, _s(mob.short_descr))
        elif c == "D":  # never stored on a room, by the loader or by OLC
            to = index.get_room_index(rs.arg1)
            if to is None:
                raise CWouldCrash("olc.c display_resets: a door reset in a room that isn't there")
            final += "R[%5d] %s door of %-19.19s reset to %s\n\r" % (
                rs.arg1, capitalize(DIR_NAME[rs.arg2]), _s(to.name), flag_string(F.DOOR_RESETS, rs.arg3))
        elif c == "R":
            to = index.get_room_index(rs.arg1)
            if to is None:
                continue
            final += "R[%5d] Exits are randomized in %s\n\r" % (rs.arg1, _s(to.name))
        else:
            final += "Bad reset command: %s." % c
        send_to_char(final, ch)


# C: olc.c add_reset
def add_reset(room, reset, index: int) -> None:
    """Put reset in slot `index` (1 is the first); 0, a negative slot or one past the end puts it last."""
    resets = room.resets
    if not resets:
        resets.append(reset)
        return
    index -= 1
    if index == 0:  # "First slot (1) selected."
        resets.insert(0, reset)
        return
    resets.insert(index if 1 <= index < len(resets) else len(resets), reset)


# C: olc.c do_resets
def do_resets(ch, argument: str) -> None:
    """resets: list the room's resets, or (with a slot number) delete one, or add a mob, object or random-exits
    reset. A missing wear location counts as "inside" (an empty word is a prefix of every word), with object 1
    as the container unless one is given."""
    from charm.core.errors import CWouldCrash
    from charm.entities.handler import is_builder
    from charm.olc.mem import new_reset_data

    index = _game().index
    args = []
    for _ in range(7):
        argument, a = one_argument(argument)
        args.append(a)
    arg1, arg2, arg3, arg4, arg5, arg6, arg7 = args
    room = ch.in_room
    if not is_builder(ch, room.area):
        send_to_char("Resets: Invalid security for editing this area.\n\r", ch)
        return
    if arg1 == "":  # "Display resets in current room."
        if room.resets:
            send_to_char("Resets: M = mobile, R = room, O = object, P = pet, S = shopkeeper\n\r", ch)
            display_resets(ch)
        else:
            send_to_char("No resets in this room.\n\r", ch)
    if not is_number(arg1):
        return
    if str_cmp(arg2, "delete"):  # "Delete a reset."
        insert_loc = atoi(arg1)
        if not room.resets:
            send_to_char("No resets in this area.\n\r", ch)
            return
        if insert_loc - 1 <= 0:
            room.resets.pop(0)
        elif insert_loc > len(room.resets):
            send_to_char("Reset not found.\n\r", ch)
            return
        else:
            room.resets.pop(insert_loc - 1)
        send_to_char("Reset deleted.\n\r", ch)
    elif (str_cmp(arg2, "mob") or str_cmp(arg2, "obj")) and is_number(arg3):  # "Add a reset."
        rs = new_reset_data()
        if str_cmp(arg2, "mob"):
            if index.get_mob_index(atoi(arg3)) is None:
                send_to_char("Mob doesn't exist.\n\r", ch)
                return
            rs.command, rs.arg1 = "M", atoi(arg3)
            rs.arg2 = atoi(arg4) if is_number(arg4) else 1  # "Max #"
            rs.arg3 = room.vnum
            rs.arg4 = atoi(arg5) if is_number(arg5) else 1  # "Min #"
        else:
            rs.arg1 = atoi(arg3)
            if str_prefix(arg4, "inside"):  # "Inside another object."
                temp = index.get_obj_index(atoi(arg5) if is_number(arg5) else 1)
                if temp is None:
                    raise CWouldCrash("olc.c do_resets: the container named isn't there (temp is NULL)")
                if temp.item_type not in (C.ITEM_CONTAINER, C.ITEM_CORPSE_NPC):
                    send_to_char("Object 2 is not a container.\n\r", ch)
                    return
                rs.command = "P"
                rs.arg2 = atoi(arg6) if is_number(arg6) else 1
                rs.arg3 = atoi(arg5) if is_number(arg5) else 1
                rs.arg4 = atoi(arg7) if is_number(arg7) else 1
            elif str_cmp(arg4, "room"):  # "Inside the room."
                if index.get_obj_index(atoi(arg3)) is None:
                    send_to_char("Vnum doesn't exist.\n\r", ch)
                    return
                rs.command, rs.arg2, rs.arg3, rs.arg4 = "O", 0, room.vnum, 0
            else:  # "Into a Mobile's inventory."
                wear = flag_value(F.WEAR_LOC_FLAGS, arg4)
                if wear == C.NO_FLAG:
                    send_to_char("Resets: '? wear-loc'\n\r", ch)
                    return
                if index.get_obj_index(atoi(arg3)) is None:
                    send_to_char("Vnum doesn't exist.\n\r", ch)
                    return
                rs.arg1, rs.arg3 = atoi(arg3), wear
                rs.command = "G" if wear == C.WEAR_NONE else "E"
        add_reset(room, rs, atoi(arg1))
        room.area.area_flags |= C.AREA_CHANGED
        send_to_char("Reset added.\n\r", ch)
    elif str_cmp(arg2, "random") and is_number(arg3):
        if atoi(arg3) < 1 or atoi(arg3) > 6:
            send_to_char("Invalid argument.\n\r", ch)
            return
        rs = new_reset_data()
        rs.command, rs.arg1, rs.arg2 = "R", room.vnum, atoi(arg3)
        add_reset(room, rs, atoi(arg1))
        room.area.area_flags |= C.AREA_CHANGED
        send_to_char("Random exits reset added.\n\r", ch)
    else:
        send_to_char("Syntax: RESET <number> OBJ <vnum> <wear_loc>\n\r", ch)
        send_to_char("        RESET <number> OBJ <vnum> inside <vnum> [limit] [count]\n\r", ch)
        send_to_char("        RESET <number> OBJ <vnum> room\n\r", ch)
        send_to_char("        RESET <number> MOB <vnum> [max #x area] [max #x room]\n\r", ch)
        send_to_char("        RESET <number> DELETE\n\r", ch)
        send_to_char("        RESET <number> RANDOM [#x exits]\n\r", ch)
