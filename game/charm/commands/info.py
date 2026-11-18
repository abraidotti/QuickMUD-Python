"""Information commands. So far what login uses: do_help, and set_title. do_look and the rest come in spike PR 5.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_info.c, src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import sys

from charm.commands.interp import one_argument
from charm.core.errors import NotPorted
from charm.core.log import bug, log_f
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
            if h.level >= 0 and argall.lower() != "imotd":
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


def do_look(ch, argument: str) -> None:
    """act_info.c do_look: spike PR 5."""
    raise NotPorted("act_info.c do_look (spike PR 5)")
