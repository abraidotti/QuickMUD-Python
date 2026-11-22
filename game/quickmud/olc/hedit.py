"""hedit.c: the help editor, and lookup.c's help_lookup and had_lookup.

Helps are in two lists: every help (Index.helps, the C's help_first), and each help file's own (HelpArea.helps,
first and then next_area), which is what asave writes. A help file whose last help is deleted keeps its last
pointer on the freed help, so a help made for it later hangs off that and never joins the file's list: it's shown
by hedit's list area, and never saved (HelpArea.last_gone). The same goes for help_last: once the newest help
is deleted, a help made after it isn't in help_first either, so neither hedit nor help can find it
(Index.help_last_gone).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/hedit.c, src/lookup.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import interpret, is_number, one_argument
from quickmud.core.errors import CWouldCrash
from quickmud.core.log import bugf
from quickmud.core.strings import atoi, smash_tilde, str_cmp, str_prefix
from quickmud.data import constants as C
from quickmud.net.output import page_to_char, printf_to_char, send_to_char
from quickmud.olc import ED_HELP


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


def _table():
    """hedit_table, in the C's order."""
    from quickmud.olc import act
    from quickmud.olc.olc import show_commands

    return (("keyword", hedit_keyword), ("text", hedit_text), ("new", hedit_new), ("level", hedit_level),
            ("commands", show_commands), ("delete", hedit_delete), ("list", hedit_list), ("show", hedit_show),
            ("?", act.show_help))


def _all_words(text: str) -> str:
    """The words of text, each as one_argument takes it (lower-cased, quotes grouping), joined by spaces."""
    words = []
    while text != "":
        text, word = one_argument(text)
        words.append(word)
    return " ".join(words)


# C: lookup.c help_lookup
def help_lookup(keyword: str):
    """The first help (in help_first's order) whose keywords hold every word of keyword."""
    from quickmud.entities.handler import is_name

    argall = _all_words(keyword)
    return next((h for h in _game().index.helps if is_name(argall, h.keyword)), None)


# C: lookup.c had_lookup
def had_lookup(arg: str):
    """The help file named arg."""
    return next((ha for ha in _game().index.had_list if str_cmp(arg, ha.filename)), None)


# C: hedit.c get_help_area
def get_help_area(help):
    return next((ha for ha in _game().index.had_list if any(h is help for h in ha.helps)), None)


# C: hedit.c hedit_show
def hedit_show(ch, argument: str) -> bool:
    help = ch.desc.pEdit
    send_to_char("Keyword : [%s]\n\rLevel   : [%d]\n\rText    :\n\r%s-END-\n\r" % (help.keyword, help.level, help.text),
                 ch)
    return False


# C: hedit.c hedit_level
def hedit_level(ch, argument: str) -> bool:
    if argument == "" or not is_number(argument):
        send_to_char("Syntax: level [-1..MAX_LEVEL]\n\r", ch)
        return False
    lev = atoi(argument)
    if lev < -1 or lev > C.MAX_LEVEL:
        printf_to_char(ch, "HEdit : levels are between -1 and %d inclusive.\n\r", C.MAX_LEVEL)
        return False
    ch.desc.pEdit.level = lev
    send_to_char("Ok.\n\r", ch)
    return True


# C: hedit.c hedit_keyword
def hedit_keyword(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax: keyword [keywords]\n\r", ch)
        return False
    ch.desc.pEdit.keyword = argument
    send_to_char("Ok.\n\r", ch)
    return True


# C: recycle.c new_had
def new_had(filename: str, area):
    from quickmud.world.index import HelpArea

    return HelpArea(filename, area)


# C: recycle.c new_help
def new_help(keyword: str):
    from quickmud.world.index import Help

    return Help(0, keyword, "")


# C: hedit.c hedit_new
def hedit_new(ch, argument: str) -> bool:
    """new [file] name: a new help, in the help file named first (if it's one), or this area's (a new help file
    for it, if it has none). It's then the one being edited. Returns False, whatever happens."""
    index = _game().index
    if argument == "":
        send_to_char("Syntax: new [name]\n\r", ch)
        send_to_char("         new [area] [name]\n\r", ch)
        return False
    fullarg = argument
    argument, arg = one_argument(argument)
    had = had_lookup(arg)
    if had is None:
        had = ch.in_room.area.helps
        argument = fullarg
    if help_lookup(argument) is not None:
        send_to_char("HEdit : help exists.\n\r", ch)
        return False
    if had is None:  # "the area has no helps"
        area = ch.in_room.area
        had = new_had(area.file_name, area)
        had.changed = True
        index.had_list.insert(0, had)
        area.helps = had
        area.area_flags |= C.AREA_CHANGED
    help = new_help(argument)
    if not index.helps:  # help_first = help
        index.helps.append(help)
        index.help_last_gone = False
    elif not index.help_last_gone:  # help_last->next = help
        index.helps.append(help)
    if not had.helps:
        had.helps.append(help)
        had.last_gone = False
    elif not had.last_gone:
        had.helps.append(help)
    ch.desc.pEdit = help
    ch.desc.editor = ED_HELP
    send_to_char("Ok.\n\r", ch)
    return False


# C: hedit.c hedit_text
def hedit_text(ch, argument: str) -> bool:
    from quickmud.olc.strings import string_append

    if argument != "":
        send_to_char("Syntax: text\n\r", ch)
        return False
    string_append(ch, (ch.desc.pEdit, "text"))
    return True


# C: hedit.c hedit
def hedit(ch, argument: str) -> None:
    """A line typed in the help editor. Security 9 is needed, whatever the help file; an edit marks the help file
    changed (not its area). An empty line shows the help before "done" is looked at."""
    from quickmud.olc.olc import edit_done

    argument = smash_tilde(argument)
    arg = argument
    argument, command = one_argument(argument)
    help = ch.desc.pEdit
    had = get_help_area(help)
    if had is None:
        bugf("hedit : had for help %s NULL", help.keyword)
        edit_done(ch)
        return
    if ch.pcdata.security < 9:
        send_to_char("HEdit: Insufficient security to edit helps.\n\r", ch)
        edit_done(ch)
        return
    if command == "":
        hedit_show(ch, argument)
        return
    if str_cmp(command, "done"):
        edit_done(ch)
        return
    for name, fun in _table():
        if str_prefix(command, name):
            if fun(ch, argument):
                had.changed = True
            return
    interpret(ch, arg)


# C: hedit.c do_hedit
def do_hedit(ch, argument: str) -> None:
    """hedit <keywords>: the first help they all name, or hedit new <name>. (The C has no IS_NPC check; a mob that
    names a help crashes it, having no connection.)"""
    arg1 = argument
    if argument != "":
        argall = _all_words(argument)  # "Taken from do_help"
        from quickmud.entities.handler import is_name

        for help in _game().index.helps:
            if is_name(argall, help.keyword):
                if ch.desc is None:
                    raise CWouldCrash("hedit.c do_hedit: a mob names a help, and its desc is NULL")
                ch.desc.pEdit = help
                ch.desc.editor = ED_HELP
                return
    argument, arg1 = one_argument(arg1)
    if str_cmp(arg1, "new"):
        if argument == "":
            send_to_char("Syntax: edit help new [topic]\n\r", ch)
            return
        if ch.desc is None:
            raise CWouldCrash("hedit.c do_hedit: a mob's hedit new, and its desc is NULL")
        if hedit_new(ch, argument):
            ch.desc.editor = ED_HELP
        return
    send_to_char("HEdit:  There is no default help to edit.\n\r", ch)


# C: hedit.c hedit_delete
def hedit_delete(ch, argument: str) -> bool:
    """Delete the help being edited, taking everyone editing it out of the editor."""
    from quickmud.olc.olc import edit_done

    game = _game()
    index = game.index
    help = ch.desc.pEdit
    for d in game.descriptor_list:
        if d.editor == ED_HELP and d.pEdit is help:
            edit_done(d.character)
    if not any(h is help for h in index.helps):
        bugf("hedit_delete : help %s not found in help_first", help.keyword)
        return False
    if len(index.helps) > 1 and index.helps[-1] is help:
        index.help_last_gone = True  # help_last stays on it
    index.helps[:] = [h for h in index.helps if h is not help]
    found = False
    for had in index.had_list:
        if had.helps and had.helps[0] is help:
            found = True
            had.helps.pop(0)  # (had->last stays on it if it was the only one; a new help then starts the list again)
        elif any(h is help for h in had.helps):
            if had.helps[-1] is help:
                had.last_gone = True
            had.helps[:] = [h for h in had.helps if h is not help]
            found = True
            break
    if not found:
        bugf("hedit_delete : help %s not found in had_list", help.keyword)
        return False
    send_to_char("Ok.\n\r", ch)
    return True


def _numbered(helps) -> str:
    out, cnt = [], 0
    for help in helps:
        out.append("%3d. %-14.14s%s" % (cnt, help.keyword, "\n\r" if cnt % 4 == 3 else " "))  # non-negative: a count
        cnt += 1
    if cnt % 4:  # non-negative: a count
        out.append("\n\r")
    return "".join(out)


# C: hedit.c hedit_list
def hedit_list(ch, argument: str) -> bool:
    if str_cmp(argument, "all"):
        page_to_char(_numbered(_game().index.helps), ch)
        return False
    if str_cmp(argument, "area"):
        if ch.in_room.area.helps is None:
            send_to_char("No helps in this area.\n\r", ch)
            return False
        page_to_char(_numbered(ch.in_room.area.helps.helps), ch)
        return False
    if argument == "":
        send_to_char("Syntax: list all\n\r", ch)
        send_to_char("        list area\n\r", ch)
    return False
