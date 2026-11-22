"""flags.c: the immortals' flag command, which sets, adds, removes or toggles a character's flags by name.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/flags.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import one_argument
from quickmud.core.strings import str_prefix
from quickmud.data import constants as C
from quickmud.data import flags as F
from quickmud.net.output import send_to_char

# field word: (attribute, the table its flags are named from, "npc" or "pc" if only for those, refusal)
_FIELDS = (("act", "act", F.ACT_FLAGS, "npc", "Use plr for PCs.\n\r"),
           ("plr", "act", F.PLR_FLAGS, "pc", "Use act for NPCs.\n\r"),
           ("aff", "affected_by", F.AFFECT_FLAGS, None, None),
           ("immunity", "imm_flags", F.IMM_FLAGS, None, None),
           ("resist", "res_flags", F.IMM_FLAGS, None, None),  # (named from the immunity table, as the C does)
           ("vuln", "vuln_flags", F.IMM_FLAGS, None, None),
           ("form", "form", F.FORM_FLAGS, "npc", "Form can't be set on PCs.\n\r"),
           ("parts", "parts", F.PART_FLAGS, "npc", "Parts can't be set on PCs.\n\r"),
           ("comm", "comm", F.COMM_FLAGS, "pc", "Comm can't be set on NPCs.\n\r"))


# C: flags.c do_flag
def do_flag(ch, argument: str) -> None:
    """flag mob|char <name> <field> [+|-|=] <flags>. The sign is the first character of the fourth word, and that
    whole word is taken away: "+ holylight" adds it, "+holylight" leaves nothing to add. It says nothing when it
    works. (The C also clears victim->zone, which nothing ever sets.)"""
    from quickmud.entities import game as game_module
    from quickmud.entities.handler import get_char_world
    from quickmud.world.lookup import flag_lookup

    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    argument, arg3 = one_argument(argument)
    kind = argument[:1]
    if kind in ("=", "-", "+"):
        argument, _ = one_argument(argument)
    if arg1 == "":
        for line in ("Syntax:\n\r", "  flag mob  <name> <field> <flags>\n\r", "  flag char <name> <field> <flags>\n\r",
                     "  mob  flags: act,aff,off,imm,res,vuln,form,part\n\r",
                     "  char flags: plr,comm,aff,imm,res,vuln,\n\r",
                     "  +: add flag, -: remove flag, = set equal to\n\r",
                     "  otherwise flag toggles the flags listed.\n\r"):
            send_to_char(line, ch)
        return
    if arg2 == "":
        send_to_char("What do you wish to set flags on?\n\r", ch)
        return
    if arg3 == "":
        send_to_char("You need to specify a flag to set.\n\r", ch)
        return
    if argument == "":
        send_to_char("Which flags do you wish to change?\n\r", ch)
        return
    if not (str_prefix(arg1, "mob") or str_prefix(arg1, "char")):
        return
    victim = get_char_world(game_module.current, ch, arg2)
    if victim is None:
        send_to_char("You can't find them.\n\r", ch)
        return
    for word, field, table, only, refusal in _FIELDS:  # "select a flag to set"
        if str_prefix(arg3, word):
            if (only == "npc" and not victim.is_npc) or (only == "pc" and victim.is_npc):
                send_to_char(refusal, ch)
                return
            break
    else:
        send_to_char("That's not an acceptable flag.\n\r", ch)
        return
    old = getattr(victim, field)
    new = 0 if kind == "=" else old
    marked = 0
    while True:  # "mark the words"
        argument, word = one_argument(argument)
        if word == "":
            break
        pos = flag_lookup(word, table)
        if pos == C.NO_FLAG:
            send_to_char("That flag doesn't exist!\n\r", ch)
            return
        marked |= pos
    for flag in table:
        if not flag.settable and old & flag.bit:
            new |= flag.bit
            continue
        if marked & flag.bit:
            if kind in ("=", "+"):
                new |= flag.bit
            elif kind == "-":
                new &= ~flag.bit
            else:
                new ^= flag.bit
    setattr(victim, field, new)
