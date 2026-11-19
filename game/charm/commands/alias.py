"""alias.c's commands: alias and unalias. Substituting an alias as a line comes in is interp.py's
substitute_alias.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/alias.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.strings import smash_tilde, str_cmp, str_prefix
from charm.data import constants as C
from charm.net.output import send_to_char


def _rch(ch):
    """The character whose aliases these are: the original one, for an immortal switched into a mob."""
    if ch.desc is None:
        return ch
    return ch.desc.original if ch.desc.original is not None else ch


# C: alias.c do_alia
def do_alia(ch, argument: str) -> None:
    send_to_char("I'm sorry, alias must be entered in full.\n\r", ch)


# C: alias.c do_alias
def do_alias(ch, argument: str) -> None:
    argument = smash_tilde(argument)
    rch = _rch(ch)
    if rch.is_npc:
        return
    pc = rch.pcdata
    argument, arg = one_argument(argument)
    if arg == "":
        if pc.alias[0] is None:
            send_to_char("You have no aliases defined.\n\r", ch)
            return
        send_to_char("Your current aliases are:\n\r", ch)
        for pos in range(C.MAX_ALIAS):
            if pc.alias[pos] is None or pc.alias_sub[pos] is None:
                break
            send_to_char("    %s:  %s\n\r" % (pc.alias[pos], pc.alias_sub[pos]), ch)
        return
    if str_prefix("una", arg) or str_cmp("alias", arg):
        send_to_char("Sorry, that word is reserved.\n\r", ch)
        return
    # "More Edwin-inspired fixes. JR -- 10/15/00"
    if " " in arg or '"' in arg or "'" in arg:
        send_to_char("The word to be aliased should not contain a space, a tick or a double-quote.\n\r", ch)
        return
    if argument == "":
        for pos in range(C.MAX_ALIAS):
            if pc.alias[pos] is None or pc.alias_sub[pos] is None:
                break
            if str_cmp(arg, pc.alias[pos]):
                send_to_char("%s aliases to '%s'.\n\r" % (pc.alias[pos], pc.alias_sub[pos]), ch)
                return
        send_to_char("That alias is not defined.\n\r", ch)
        return
    if str_prefix(argument, "delete") or str_prefix(argument, "prefix"):
        send_to_char("That shall not be done!\n\r", ch)
        return
    pos = 0
    while pos < C.MAX_ALIAS:
        if pc.alias[pos] is None:
            break
        if str_cmp(arg, pc.alias[pos]):  # "redefine an alias"
            pc.alias_sub[pos] = argument
            send_to_char("%s is now realiased to '%s'.\n\r" % (arg, argument), ch)
            return
        pos += 1
    if pos >= C.MAX_ALIAS:
        send_to_char("Sorry, you have reached the alias limit.\n\r", ch)
        return
    # "make a new alias"
    pc.alias[pos] = arg
    pc.alias_sub[pos] = argument
    send_to_char("%s is now aliased to '%s'.\n\r" % (arg, argument), ch)


# C: alias.c do_unalias
def do_unalias(ch, argument: str) -> None:
    rch = _rch(ch)
    if rch.is_npc:
        return
    pc = rch.pcdata
    found = False
    argument, arg = one_argument(argument)
    if arg == "":
        send_to_char("Unalias what?\n\r", ch)
        return
    for pos in range(C.MAX_ALIAS):
        if pc.alias[pos] is None:
            break
        if found:
            pc.alias[pos - 1], pc.alias_sub[pos - 1] = pc.alias[pos], pc.alias_sub[pos]
            pc.alias[pos] = pc.alias_sub[pos] = None
            continue
        if arg == pc.alias[pos]:
            send_to_char("Alias removed.\n\r", ch)
            pc.alias[pos] = pc.alias_sub[pos] = None
            found = True
    if not found:
        send_to_char("No alias of that name to remove.\n\r", ch)
