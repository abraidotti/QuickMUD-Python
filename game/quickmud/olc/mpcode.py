"""olc_mpcode.c: the mob program editor (mpedit), which edits a #MOBPROGS program's code by its vnum.

The C's MPROG_CODE is a vnum and its code, in mprog_list (newest first). The index keeps the code by vnum
(Index.mprog_code, in the order the programs were made), so an MprogCode here is a handle on one entry: reading
or setting its code reads or sets the index's.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/olc_mpcode.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import interpret, is_number, one_argument
from quickmud.core.strings import atoi, smash_tilde, str_cmp, str_prefix
from quickmud.data import constants as C
from quickmud.net.output import page_to_char, send_to_char
from quickmud.olc import ED_MPCODE


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


class MprogCode:
    """MPROG_CODE: a program's vnum, and its code (kept in the index)."""

    def __init__(self, index, vnum: int):
        self.index, self.vnum = index, vnum

    @property
    def code(self) -> str:
        return self.index.mprog_code[self.vnum]

    @code.setter
    def code(self, value: str) -> None:
        self.index.mprog_code[self.vnum] = value


def _table():
    """mpedit_table, in the C's order (it has no "version")."""
    from quickmud.olc import act
    from quickmud.olc.olc import show_commands

    return (("commands", show_commands), ("create", mpedit_create), ("code", mpedit_code), ("show", mpedit_show),
            ("list", mpedit_list), ("?", act.show_help))


# C: olc_mpcode.c mpedit
def mpedit(ch, argument: str) -> None:
    """A line typed in the mob program editor. An empty line shows the program before "done" is looked at."""
    from quickmud.entities.handler import is_builder
    from quickmud.olc.act import get_vnum_area
    from quickmud.olc.olc import edit_done

    argument = smash_tilde(argument)
    arg = argument
    argument, command = one_argument(argument)
    code = ch.desc.pEdit
    if code is not None:
        area = get_vnum_area(code.vnum)
        if area is None:  # "???"
            edit_done(ch)
            return
        if not is_builder(ch, area):
            send_to_char("MPEdit: Insufficient security to modify code.\n\r", ch)
            edit_done(ch)
            return
    if command == "":
        mpedit_show(ch, argument)
        return
    if str_cmp(command, "done"):
        edit_done(ch)
        return
    for name, fun in _table():
        if str_prefix(command, name):
            if fun(ch, argument) and code is not None:
                area = get_vnum_area(code.vnum)
                if area is not None:
                    area.area_flags |= C.AREA_CHANGED
            return
    interpret(ch, arg)


# C: olc_mpcode.c do_mpedit
def do_mpedit(ch, argument: str) -> None:
    """mpedit <vnum> or mpedit create <vnum>. (No IS_NPC check, as in the C: a mob is refused as no builder.)"""
    from quickmud.entities.handler import is_builder
    from quickmud.olc.act import get_vnum_area

    index = _game().index
    argument, command = one_argument(argument)
    if is_number(command):
        vnum = atoi(command)
        if index.get_mprog_index(vnum) is None:
            send_to_char("MPEdit : That vnum does not exist.\n\r", ch)
            return
        area = get_vnum_area(vnum)
        if area is None:
            send_to_char("MPEdit : VNUM no asignado a ningun area.\n\r", ch)
            return
        if not is_builder(ch, area):
            send_to_char("MPEdit : Insuficiente seguridad para editar area.\n\r", ch)
            return
        ch.desc.pEdit = MprogCode(index, vnum)
        ch.desc.editor = ED_MPCODE
        return
    if str_cmp(command, "create"):
        if argument == "":
            send_to_char("Sintaxis : mpedit create [vnum]\n\r", ch)
            return
        mpedit_create(ch, argument)
        return
    send_to_char("Sintaxis : mpedit [vnum]\n\r", ch)
    send_to_char("           mpedit create [vnum]\n\r", ch)


# C: olc_mpcode.c mpedit_create
def mpedit_create(ch, argument: str) -> bool:
    from quickmud.entities.handler import is_builder
    from quickmud.olc.act import get_vnum_area

    index = _game().index
    value = atoi(argument)
    if argument == "" or value < 1:
        send_to_char("Sintaxis : mpedit create [vnum]\n\r", ch)
        return False
    area = get_vnum_area(value)
    if area is None:
        send_to_char("MPEdit : VNUM no asignado a ningun area.\n\r", ch)
        return False
    if not is_builder(ch, area):
        send_to_char("MPEdit : Insuficiente seguridad para crear MobProgs.\n\r", ch)
        return False
    if index.get_mprog_index(value) is not None:
        send_to_char("MPEdit: Code vnum already exists.\n\r", ch)
        return False
    from quickmud.olc.mem import new_mpcode

    new_mpcode(index, value)  # at the head of mprog_list (the newest)
    ch.desc.pEdit = MprogCode(index, value)
    ch.desc.editor = ED_MPCODE
    send_to_char("MobProgram Code Created.\n\r", ch)
    return True


# C: olc_mpcode.c mpedit_show
def mpedit_show(ch, argument: str) -> bool:
    code = ch.desc.pEdit
    send_to_char("Vnum:       [%d]\n\rCode:\n\r%s\n\r" % (code.vnum, code.code), ch)
    return False


# C: olc_mpcode.c mpedit_code
def mpedit_code(ch, argument: str) -> bool:
    from quickmud.olc.strings import string_append

    if argument == "":
        string_append(ch, (ch.desc.pEdit, "code"))
        return True
    send_to_char("Syntax: code\n\r", ch)
    return False


# C: olc_mpcode.c mpedit_list
def mpedit_list(ch, argument: str) -> bool:
    """The programs, newest first: all of them, or those strictly inside this area's vnums (ENTRE leaves out its
    first and last vnum). * marks the ones the builder may edit, ? those in no area."""
    from quickmud.entities.handler import is_builder
    from quickmud.olc.act import get_vnum_area

    index = _game().index
    every = str_cmp(argument, "all")
    area = ch.in_room.area
    out, count = [], 1
    for vnum in reversed(list(index.mprog_code)):
        if every or area.min_vnum < vnum < area.max_vnum:
            ad = get_vnum_area(vnum)
            mark = "?" if ad is None else "*" if is_builder(ch, ad) else " "
            out.append("[%3d] (%s) %5d\n\r" % (count, mark, vnum))
            count += 1
    if count == 1:
        out.append("MobPrograms do not exist!\n\r" if every else "MobPrograms do not exist in this area.\n\r")
    page_to_char("".join(out), ch)
    return False
