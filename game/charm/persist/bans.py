"""Site bans, all of ban.c: the ban list (game.ban_list, head first), ban.txt, check_ban, and the ban, permban
and allow commands.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/ban.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass

from charm.core.strings import lower, str_cmp, str_prefix, str_suffix
from charm.data import constants as C
from charm.entities import game as game_module


@dataclass(eq=False)
class Ban:
    """BAN_DATA."""

    name: str = ""
    level: int = 0
    ban_flags: int = 0


# C: ban.c save_bans
def save_bans(game) -> None:
    """Write the permanent bans to ban.txt, or remove it if there are none."""
    from charm.persist.player import print_flags

    path = game_module.c_path(game, C.BAN_FILE)
    lines = ["%-20s %-2d %s\n" % (b.name, b.level, print_flags(b.ban_flags))
             for b in game.ban_list if b.ban_flags & C.BAN_PERMANENT]
    with open(path, "w", encoding="latin-1", newline="") as f:  # (the C writes to a NULL file if fopen fails)
        f.write("".join(lines))
    if not lines:
        path.unlink()


# C: ban.c load_bans
def load_bans(game) -> None:
    from charm.world.areafile.reader import Reader

    path = game_module.c_path(game, C.BAN_FILE)
    if not path.is_file():
        return
    r = Reader(path.read_bytes().decode("latin-1"), str(path))
    while not r.at_eof:  # feof: true once a read has hit the end, which fread_to_eol does after the last line
        ban = Ban(name=r.read_word(), level=r.read_number(), ban_flags=r.read_flag())
        r.read_to_eol()
        game.ban_list.append(ban)


# C: ban.c check_ban
def check_ban(game, site: str, kind: int) -> bool:
    """Whether site is banned for kind (BAN_ALL, BAN_NEWBIES or BAN_PERMIT)."""
    host = lower(site)  # capitalize, then LOWER of the first letter: all lower case
    for ban in game.ban_list:
        if not ban.ban_flags & kind:
            continue
        flags = ban.ban_flags
        if flags & C.BAN_PREFIX and flags & C.BAN_SUFFIX and host in ban.name:  # sic: the host in the name (#65)
            return True
        if flags & C.BAN_PREFIX and str_suffix(ban.name, host):
            return True
        if flags & C.BAN_SUFFIX and str_prefix(ban.name, host):
            return True
    return False  # sic: a ban with no * never matches (#65)


_TYPE_NAMES = ((C.BAN_NEWBIES, "newbies"), (C.BAN_PERMIT, "permit"), (C.BAN_ALL, "all"))


# C: ban.c ban_site
def ban_site(ch, argument: str, f_perm: bool) -> None:
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_trust
    from charm.entities.things import add_buf, new_buf
    from charm.net.output import page_to_char, send_to_char

    game = game_module.current
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "":
        if not game.ban_list:
            send_to_char("No sites banned at this time.\n\r", ch)
            return
        buffer = new_buf()
        add_buf(buffer, "Banned sites  level  type     status\n\r")
        for ban in game.ban_list:
            buf2 = "%s%s%s" % ("*" if ban.ban_flags & C.BAN_PREFIX else "", ban.name,
                               "*" if ban.ban_flags & C.BAN_SUFFIX else "")
            kind = next((name for bit, name in _TYPE_NAMES if ban.ban_flags & bit), "")
            add_buf(buffer, "%-12s    %-3d  %-7s  %s\n\r"
                    % (buf2, ban.level, kind, "perm" if ban.ban_flags & C.BAN_PERMANENT else "temp"))
        page_to_char(buffer.string, ch)
        return
    if arg2 == "" or str_prefix(arg2, "all"):  # "find out what type of ban"
        kind = C.BAN_ALL
    elif str_prefix(arg2, "newbies"):
        kind = C.BAN_NEWBIES
    elif str_prefix(arg2, "permit"):
        kind = C.BAN_PERMIT
    else:
        send_to_char("Acceptable ban types are all, newbies, and permit.\n\r", ch)
        return
    name = arg1
    prefix = suffix = False
    if name[0] == "*":
        prefix = True
        name = name[1:]
    if (name[-1] if name else arg1[0]) == "*":  # with "*" alone, the C looks at the character before name
        suffix = True
        name = name[:-1]
    if name == "":
        send_to_char("You have to ban SOMETHING.\n\r", ch)
        return
    for i, ban in enumerate(game.ban_list):
        if str_cmp(name, ban.name):
            if ban.level > get_trust(ch):
                send_to_char("That ban was set by a higher power.\n\r", ch)
                return
            del game.ban_list[i]
            # sic: the C frees it and walks on from it into the free list, a use-after-free (#65)
            break
    flags = kind | (C.BAN_PREFIX if prefix else 0) | (C.BAN_SUFFIX if suffix else 0) | (
        C.BAN_PERMANENT if f_perm else 0)
    ban = Ban(name=name, level=get_trust(ch), ban_flags=flags)
    game.ban_list.insert(0, ban)
    save_bans(game)
    send_to_char("%s has been banned.\n\r" % ban.name, ch)


# C: ban.c do_ban
def do_ban(ch, argument: str) -> None:
    ban_site(ch, argument, False)


# C: ban.c do_permban
def do_permban(ch, argument: str) -> None:
    ban_site(ch, argument, True)


# C: ban.c do_allow
def do_allow(ch, argument: str) -> None:
    from charm.commands.interp import one_argument
    from charm.entities.handler import get_trust
    from charm.net.output import send_to_char

    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Remove which site from the ban list?\n\r", ch)
        return
    for i, ban in enumerate(game.ban_list):
        if str_cmp(arg, ban.name):
            if ban.level > get_trust(ch):
                send_to_char("You are not powerful enough to lift that ban.\n\r", ch)
                return
            del game.ban_list[i]
            send_to_char("Ban on %s lifted.\n\r" % arg, ch)
            save_bans(game)
            return
    send_to_char("Site is not banned.\n\r", ch)
