"""The command interpreter: interpret, check_social and substitute_alias, and the argument helpers.

A command whose function isn't ported yet raises NotPorted, which stops the game (#32, decision 3).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/interp.c, src/alias.c, src/olc.c.
Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.data import constants as C

SPACE = " \t\n\v\f\r"  # isspace in the C locale


def _lower(c: str) -> str:
    return chr(ord(c) + 32) if "A" <= c <= "Z" else c


# C: interp.c one_argument
def one_argument(argument: str) -> tuple[str, str]:
    """(the rest, the first argument lower-cased). A quote (' or ") at the start groups words up to the matching
    quote."""
    i, n = 0, len(argument)
    while i < n and argument[i] in SPACE:
        i += 1
    end = " "
    if i < n and argument[i] in "'\"":
        end = argument[i]
        i += 1
    out = []
    while i < n:
        if argument[i] == end:
            i += 1
            break
        out.append(_lower(argument[i]))
        i += 1
    while i < n and argument[i] in SPACE:
        i += 1
    return argument[i:], "".join(out)


# C: interp.c is_number
def is_number(arg: str) -> bool:
    if arg == "":
        return False
    if arg[0] in "+-":
        arg = arg[1:]
    return all("0" <= c <= "9" for c in arg)


# C: interp.c number_argument
def number_argument(argument: str) -> tuple[int, str]:
    """(the number, the rest): "2.sword" is (2, "sword"); with no dot, (1, argument). The number is atoi's, so
    "x.sword" is (0, "sword")."""
    from charm.core.strings import atoi

    dot = argument.find(".")
    if dot < 0:
        return 1, argument
    return atoi(argument[:dot]), argument[dot + 1:]


# C: interp.c mult_argument
def mult_argument(argument: str) -> tuple[int, str]:
    """(the number, the rest): "3*bread" is (3, "bread"); with no star, (1, argument). The number is atoi's."""
    from charm.core.strings import atoi

    star = argument.find("*")
    if star < 0:
        return 1, argument
    return atoi(argument[:star]), argument[star + 1:]


LOG_NORMAL, LOG_ALWAYS, LOG_NEVER = 0, 1, 2  # interp.c
_SENTINEL_LOG = LOG_NORMAL  # the closing row's: interpret reads it when no command matched


def _commands() -> dict:
    """The do_* functions ported so far, by the C name the command table gives."""
    from charm.commands import alias, comm, healer, info, move, obj, wiz
    from charm.persist import bans, boards
    from charm.systems import fight, magic, mobcmds, music
    from charm.systems.skills import do_gain, do_groups, do_skills, do_spells

    found = {name: getattr(mod, name) for mod in (alias, comm, healer, info, move, obj, wiz, fight, magic, music)
             for name in dir(mod)
             if name.startswith("do_") and name not in wiz.NOT_COMMANDS}
    found.update(do_board=boards.do_board, do_note=boards.do_note, do_ban=bans.do_ban,
                 do_permban=bans.do_permban, do_allow=bans.do_allow, do_groups=do_groups, do_skills=do_skills,
                 do_gain=do_gain, do_spells=do_spells,
                 # mob_cmds.c's: only these are commands; the rest are mob_interpret's
                 do_mob=mobcmds.do_mob, do_mpstat=mobcmds.do_mpstat, do_mpdump=mobcmds.do_mpdump)
    return found


_COMMANDS: dict = {}


def command_function(name: str):
    """The Python function for a command table entry's do_fun, or None if it isn't ported."""
    if not _COMMANDS:
        _COMMANDS.update(_commands())
    return _COMMANDS.get(name)


def _isalpha(c: str) -> bool:
    return "a" <= c <= "z" or "A" <= c <= "Z"


_POSITION_REFUSALS = {
    C.POS_DEAD: "Lie still; you are DEAD.\n\r",
    C.POS_MORTAL: "You are hurt far too bad for that.\n\r",
    C.POS_INCAP: "You are hurt far too bad for that.\n\r",
    C.POS_STUNNED: "You are too stunned to do that.\n\r",
    C.POS_SLEEPING: "In your dreams, or what?\n\r",
    C.POS_RESTING: "Nah... You feel too relaxed...\n\r",
    C.POS_SITTING: "Better stand up first.\n\r",
    C.POS_FIGHTING: "No way!  You are still fighting!\n\r",
}


# C: interp.c interpret
def interpret(ch, argument: str) -> None:
    from charm.core.errors import NotPorted
    from charm.core.log import log_string
    from charm.core.strings import smash_dollar, str_prefix
    from charm.data.commands import CMD_TABLE
    from charm.entities import game as game_module
    from charm.entities.handler import get_trust
    from charm.net.output import send_to_char, write_to_buffer
    from charm.net.wiznet import wiznet

    # "Strip leading spaces."
    i = 0
    while i < len(argument) and argument[i] in SPACE:
        i += 1
    argument = argument[i:]
    if argument == "":
        return
    ch.affected_by &= ~C.AFF_HIDE  # "No hiding."
    # "Implement freeze command."
    if not ch.is_npc and ch.act & C.PLR_FREEZE:
        send_to_char("You're totally frozen!\n\r", ch)
        return

    # "Grab the command word. Special parsing so ' can be a command, also no spaces needed after punctuation."
    logline = argument
    if not _isalpha(argument[0]) and not ("0" <= argument[0] <= "9"):
        command = argument[0]
        argument = argument[1:]
        i = 0
        while i < len(argument) and argument[i] in SPACE:
            i += 1
        argument = argument[i:]
    else:
        argument, command = one_argument(argument)

    # "Look for command in command table."
    trust = get_trust(ch)
    entry = None
    for cmd in CMD_TABLE:
        if command[:1] == cmd.name[0] and str_prefix(command, cmd.name) and cmd.level <= trust:
            entry = cmd
            break

    # "Log and snoop."
    logline = smash_dollar(logline)
    log = entry.log if entry is not None else _SENTINEL_LOG
    if log == LOG_NEVER:
        logline = ""
    if (not ch.is_npc and ch.act & C.PLR_LOG) or game_module.current.log_all or log == LOG_ALWAYS:
        log_buf = f"Log {ch.name}: {logline}"
        # "Make sure that was is displayed is what is typed"
        shown = log_buf.replace("$", "$$").replace("{", "{{")
        wiznet(game_module.current, shown, ch, None, C.WIZ_SECURE, 0, get_trust(ch))
        log_string(log_buf)
    if ch.desc is not None and ch.desc.snoop_by is not None:
        write_to_buffer(ch.desc.snoop_by, "% ", 2)
        write_to_buffer(ch.desc.snoop_by, logline, 0)
        write_to_buffer(ch.desc.snoop_by, "\n\r", 2)

    if entry is None:
        # "Look for command in socials table."
        if not check_social(ch, command, argument):
            send_to_char("Huh?\n\r", ch)
        return

    # "Character not in position for command?"
    if ch.position < entry.position:
        if ch.position in _POSITION_REFUSALS:
            send_to_char(_POSITION_REFUSALS[ch.position], ch)
        return

    # "Dispatch the command."
    fn = command_function(entry.do_fun)
    if fn is None:
        raise NotPorted(f"interp.c interpret: {entry.do_fun} (the '{entry.name}' command)")
    fn(ch, argument)


# C: interp.c check_social
def check_social(ch, command: str, argument: str) -> bool:
    from charm.core.rng import number_bits
    from charm.core.strings import str_cmp, str_prefix
    from charm.entities import game as game_module
    from charm.entities.handler import get_char_room, is_affected
    from charm.net.act import act
    from charm.net.output import send_to_char

    social = None
    for s in game_module.current.index.socials:
        if command[:1] == s.name[:1] and str_prefix(command, s.name):
            social = s
            break
    if social is None:
        return False
    if not ch.is_npc and ch.comm & C.COMM_NOEMOTE:
        send_to_char("You are anti-social!\n\r", ch)
        return True
    pos = ch.position
    if pos == C.POS_DEAD:
        send_to_char("Lie still; you are DEAD.\n\r", ch)
        return True
    if pos in (C.POS_INCAP, C.POS_MORTAL):
        send_to_char("You are hurt far too bad for that.\n\r", ch)
        return True
    if pos == C.POS_STUNNED:
        send_to_char("You are too stunned to do that.\n\r", ch)
        return True
    if pos == C.POS_SLEEPING and not str_cmp(social.name, "snore"):
        # "I just know this is the path to a 12" 'if' statement.  :( But two players asked for it already!"
        send_to_char("In your dreams, or what?\n\r", ch)
        return True

    (char_no_arg, others_no_arg, char_found, others_found, vict_found, _char_not_found, char_auto,
     others_auto) = social.messages
    _, arg = one_argument(argument)
    if arg == "":
        act(others_no_arg, ch, None, None, C.TO_ROOM)
        act(char_no_arg, ch, None, None, C.TO_CHAR)
        return True
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
    elif victim is ch:
        act(others_auto, ch, None, victim, C.TO_ROOM)
        act(char_auto, ch, None, victim, C.TO_CHAR)
    else:
        act(others_found, ch, None, victim, C.TO_NOTVICT)
        act(char_found, ch, None, victim, C.TO_CHAR)
        act(vict_found, ch, None, victim, C.TO_VICT)
        if (not ch.is_npc and victim.is_npc and not is_affected(victim, C.AFF_CHARM)
                and victim.position > C.POS_SLEEPING and victim.desc is None):
            roll = number_bits(4)
            if roll <= 8:
                act(others_found, victim, None, ch, C.TO_NOTVICT)
                act(char_found, victim, None, ch, C.TO_CHAR)
                act(vict_found, victim, None, ch, C.TO_VICT)
            elif roll <= 12:
                act("$n slaps $N.", victim, None, ch, C.TO_NOTVICT)
                act("You slap $N.", victim, None, ch, C.TO_CHAR)
                act("$n slaps you.", victim, None, ch, C.TO_VICT)
    return True


# C: alias.c substitute_alias
def substitute_alias(d, argument: str) -> None:
    from charm.core.strings import str_prefix
    from charm.net.descriptor import ch_of
    from charm.net.output import send_to_char

    ch = ch_of(d)
    # "check for prefix"
    if ch.prefix != "" and not str_prefix("prefix", argument):
        if len(ch.prefix) + len(argument) > C.MAX_INPUT_LENGTH - 2:
            send_to_char("Line to long, prefix not processed.\r\n", ch)
        else:
            argument = f"{ch.prefix} {argument}"
    if (ch.is_npc or ch.pcdata.alias[0] is None or str_prefix("alias", argument) or str_prefix("una", argument)
            or str_prefix("prefix", argument)):
        interpret(d.character, argument)
        return
    buf = argument
    for alias, sub in zip(ch.pcdata.alias, ch.pcdata.alias_sub):  # "go through the aliases"
        if alias is None:
            break
        if str_prefix(alias, argument):
            point, name = one_argument(argument)
            if alias == name:
                buf = sub + (" " + point if point else "")
                if len(buf) > C.MAX_INPUT_LENGTH - 1:
                    send_to_char("Alias substitution too long. Truncated.\r\n", ch)
                    buf = buf[:C.MAX_INPUT_LENGTH - 1]
                break
    interpret(d.character, buf)


# C: olc.c run_olc_editor [partial]
def run_olc_editor(d) -> bool:
    """[partial]: every editor (aedit, redit, oedit, medit, mpedit, hedit) raises NotPorted."""
    from charm.core.errors import NotPorted

    if d.editor == 0:
        return False
    raise NotPorted(f"olc.c run_olc_editor: editor {d.editor}")
