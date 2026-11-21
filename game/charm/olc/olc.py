"""olc.c: the online builder's framework. 'edit' (do_olc) and the do_*edit commands put a connection in an editor;
while it's there, every line goes to that editor (run_olc_editor, from the game loop), which runs one of its own
commands or, failing that, the ordinary interpreter. This PR has the area editor; the others raise NotPorted.

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
    elif editor in (ED_ROOM, ED_OBJECT, ED_MOBILE, ED_MPCODE, ED_HELP):
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
            if fun != "do_aedit":
                raise NotPorted(f"olc.c do_olc: {fun}")
            do_aedit(ch, argument)
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
