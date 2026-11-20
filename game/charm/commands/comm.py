"""Talking and groups, all of act_comm.c: the channels, say, tell, reply, emote, pose, following, ordering, groups,
splitting coins, colour settings, delete, save and quit.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import one_argument
from charm.core.errors import CWouldCrash, NotPorted
from charm.core.log import bug, log_string
from charm.core.strings import atoi, str_cmp, upper
from charm.data import constants as C
from charm.entities import game as game_module
from charm.net.act import MOB_TRIGGER, act, act_new
from charm.net.descriptor import ch_of
from charm.net.output import send_to_char, send_to_char_bw
from charm.net.wiznet import wiznet

SAVING = "Saving. Remember that Charm has automatic saving now.\n\r"


def wait_state(ch, npulse: int) -> None:
    """WAIT_STATE: lag of at least npulse pulses."""
    ch.wait = max(ch.wait, npulse)


# C: act_comm.c do_delet
def do_delet(ch, argument: str) -> None:
    send_to_char("You must type the full command to delete yourself.\n\r", ch)


# C: act_comm.c do_delete
def do_delete(ch, argument: str) -> None:
    import os

    from charm.entities.handler import get_trust
    from charm.persist.player import capitalize
    from charm.systems.fight import stop_fighting

    game = game_module.current
    if ch.is_npc:
        return
    if ch.pcdata.confirm_delete:
        if argument != "":
            send_to_char("Delete status removed.\n\r", ch)
            ch.pcdata.confirm_delete = False
            return
        strsave = game_module.c_path(game, C.PLAYER_DIR + capitalize(ch.name))
        wiznet(game, "$N turns $Mself into line noise.", ch, None, 0, 0, 0)
        stop_fighting(game, ch, True)
        do_quit(ch, "")
        try:
            os.remove(strsave)
        except OSError:  # the C ignores what unlink returns
            pass
        return
    if argument != "":
        send_to_char("Just type delete. No argument.\n\r", ch)
        return
    send_to_char("Type delete again to confirm this command.\n\r", ch)
    send_to_char("WARNING: this command is irreversible.\n\r", ch)
    send_to_char("Typing delete with an argument will undo delete status.\n\r", ch)
    ch.pcdata.confirm_delete = True
    wiznet(game, "$N is contemplating deletion.", ch, None, 0, 0, get_trust(ch))


# do_channels' first rows: (label, the flag that turns the channel off).
_CHANNEL_ROWS = (
    ("{dgossip{x         ", C.COMM_NOGOSSIP), ("{aauction{x        ", C.COMM_NOAUCTION),
    ("{emusic{x          ", C.COMM_NOMUSIC), ("{qQ{x/{fA{x            ", C.COMM_NOQUESTION),
    ("{hQuote{x          ", C.COMM_NOQUOTE), ("{tgrats{x          ", C.COMM_NOGRATS),
)


def _on_off(on: bool) -> str:
    return "ON\n\r" if on else "OFF\n\r"


# C: act_comm.c do_channels
def do_channels(ch, argument: str) -> None:
    from charm.entities.handler import is_immortal

    # "lists all channels and their status"
    send_to_char("   channel     status\n\r", ch)
    send_to_char("---------------------\n\r", ch)
    for label, bit in _CHANNEL_ROWS:
        send_to_char(label, ch)
        send_to_char(_on_off(not ch.comm & bit), ch)
    if is_immortal(ch):
        send_to_char("{igod channel{x    ", ch)
        send_to_char(_on_off(not ch.comm & C.COMM_NOWIZ), ch)
    send_to_char("{tshouts{x         ", ch)
    send_to_char(_on_off(not ch.comm & C.COMM_SHOUTSOFF), ch)
    send_to_char("{ktells{x          ", ch)
    send_to_char(_on_off(not ch.comm & C.COMM_DEAF), ch)
    send_to_char("{tquiet mode{x     ", ch)
    send_to_char(_on_off(bool(ch.comm & C.COMM_QUIET)), ch)
    if ch.comm & C.COMM_AFK:
        send_to_char("You are AFK.\n\r", ch)
    if ch.comm & C.COMM_SNOOP_PROOF:
        send_to_char("You are immune to snooping.\n\r", ch)
    if ch.lines != C.PAGELEN:
        if ch.lines:
            send_to_char("You display %d lines of scroll.\n\r" % (ch.lines + 2), ch)
        else:
            send_to_char("Scroll buffering is off.\n\r", ch)
    if ch.prompt is not None:
        send_to_char("Your current prompt is: %s\n\r" % ch.prompt, ch)
    if ch.comm & C.COMM_NOSHOUT:
        send_to_char("You cannot shout.\n\r", ch)
    if ch.comm & C.COMM_NOTELL:
        send_to_char("You cannot use tell.\n\r", ch)
    if ch.comm & C.COMM_NOCHANNELS:
        send_to_char("You cannot use channels.\n\r", ch)
    if ch.comm & C.COMM_NOEMOTE:
        send_to_char("You cannot show emotions.\n\r", ch)


def _toggle(ch, bit: int, when_set: str, when_clear: str) -> None:
    if ch.comm & bit:
        send_to_char(when_set, ch)
        ch.comm &= ~bit
    else:
        send_to_char(when_clear, ch)
        ch.comm |= bit


# C: act_comm.c do_deaf
def do_deaf(ch, argument: str) -> None:
    _toggle(ch, C.COMM_DEAF, "You can now hear tells again.\n\r", "From now on, you won't hear tells.\n\r")


# C: act_comm.c do_quiet
def do_quiet(ch, argument: str) -> None:
    _toggle(ch, C.COMM_QUIET, "Quiet mode removed.\n\r", "From now on, you will only hear says and emotes.\n\r")


# C: act_comm.c do_afk
def do_afk(ch, argument: str) -> None:
    _toggle(ch, C.COMM_AFK, "AFK mode removed. Type 'replay' to see tells.\n\r", "You are now in AFK mode.\n\r")


# C: act_comm.c do_replay
def do_replay(ch, argument: str) -> None:
    from charm.entities.things import clear_buf
    from charm.net.output import page_to_char

    if ch.is_npc:
        send_to_char("You can't replay.\n\r", ch)
        return
    if ch.pcdata.buffer.string == "":
        send_to_char("You have no tells to replay.\n\r", ch)
        return
    page_to_char(ch.pcdata.buffer.string, ch)
    clear_buf(ch.pcdata.buffer)


def _channel(ch, argument: str, bit: int, on: str, off: str, mine: str, theirs: str, min_pos: int,
             empty_is_sent: bool = False) -> None:
    """The public channels: no text toggles the channel; text turns it on and goes to everyone playing who hasn't
    turned it off and isn't in quiet mode. With empty_is_sent (auction), no text toggles and then sends anyway."""
    if argument == "":
        if ch.comm & bit:
            send_to_char(on, ch)
            ch.comm &= ~bit
        else:
            send_to_char(off, ch)
            ch.comm |= bit
        if not empty_is_sent:
            return
    else:
        if ch.comm & C.COMM_QUIET:
            send_to_char("You must turn off quiet mode first.\n\r", ch)
            return
        if ch.comm & C.COMM_NOCHANNELS:
            send_to_char("The gods have revoked your channel priviliges.\n\r", ch)
            return
        ch.comm &= ~bit
    send_to_char(mine % argument, ch)  # format: sprintf
    for d in list(game_module.current.descriptor_list):
        victim = ch_of(d)
        if (d.connected == C.CON_PLAYING and d.character is not ch and not victim.comm & bit
                and not victim.comm & C.COMM_QUIET):
            act_new(theirs, ch, argument, d.character, C.TO_VICT, min_pos)


# C: act_comm.c do_auction
def do_auction(ch, argument: str) -> None:
    # sic: with no text, the C toggles the channel and then auctions the empty text all the same (#50)
    _channel(ch, argument, C.COMM_NOAUCTION, "{aAuction channel is now ON.{x\n\r",
             "{aAuction channel is now OFF.{x\n\r", "{aYou auction '{A%s{a'{x\n\r", "{a$n auctions '{A$t{a'{x",
             C.POS_DEAD, empty_is_sent=True)


# C: act_comm.c do_gossip
def do_gossip(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOGOSSIP, "Gossip channel is now ON.\n\r", "Gossip channel is now OFF.\n\r",
             "{dYou gossip '{9%s{d'{x\n\r", "{d$n gossips '{9$t{d'{x", C.POS_SLEEPING)


# C: act_comm.c do_grats
def do_grats(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOGRATS, "Grats channel is now ON.\n\r", "Grats channel is now OFF.\n\r",
             "{tYou grats '%s'{x\n\r", "{t$n grats '$t'{x", C.POS_SLEEPING)


# C: act_comm.c do_quote
def do_quote(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOQUOTE, "{hQuote channel is now ON.{x\n\r", "{hQuote channel is now OFF.{x\n\r",
             "{hYou quote '{H%s{h'{x\n\r", "{h$n quotes '{H$t{h'{x", C.POS_SLEEPING)


# C: act_comm.c do_question
def do_question(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOQUESTION, "Q/A channel is now ON.\n\r", "Q/A channel is now OFF.\n\r",
             "{qYou question '{Q%s{q'{x\n\r", "{q$n questions '{Q$t{q'{x", C.POS_SLEEPING)


# C: act_comm.c do_answer
def do_answer(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOQUESTION, "Q/A channel is now ON.\n\r", "Q/A channel is now OFF.\n\r",
             "{fYou answer '{F%s{f'{x\n\r", "{f$n answers '{F$t{f'{x", C.POS_SLEEPING)


# C: act_comm.c do_music
def do_music(ch, argument: str) -> None:
    _channel(ch, argument, C.COMM_NOMUSIC, "Music channel is now ON.\n\r", "Music channel is now OFF.\n\r",
             "{eYou MUSIC: '{E%s{e'{x\n\r", "{e$n MUSIC: '{E$t{e'{x", C.POS_SLEEPING)


# C: act_comm.c do_clantalk
def do_clantalk(ch, argument: str) -> None:
    from charm.data.clans import CLAN_TABLE
    from charm.entities.handler import is_clan, is_same_clan

    if not is_clan(ch) or CLAN_TABLE[ch.clan].independent:
        send_to_char("You aren't in a clan.\n\r", ch)
        return
    if argument == "":
        _toggle(ch, C.COMM_NOCLAN, "Clan channel is now ON\n\r", "Clan channel is now OFF\n\r")
        return
    if ch.comm & C.COMM_NOCHANNELS:
        send_to_char("The gods have revoked your channel priviliges.\n\r", ch)
        return
    ch.comm &= ~C.COMM_NOCLAN
    send_to_char("You clan '%s'{x\n\r" % argument, ch)
    for d in list(game_module.current.descriptor_list):
        if (d.connected == C.CON_PLAYING and d.character is not ch and is_same_clan(ch, d.character)
                and not d.character.comm & C.COMM_NOCLAN and not d.character.comm & C.COMM_QUIET):
            act_new("$n clans '$t'{x", ch, argument, d.character, C.TO_VICT, C.POS_DEAD)


# C: act_comm.c do_immtalk
def do_immtalk(ch, argument: str) -> None:
    from charm.entities.handler import is_immortal

    if argument == "":
        _toggle(ch, C.COMM_NOWIZ, "Immortal channel is now ON\n\r", "Immortal channel is now OFF\n\r")
        return
    ch.comm &= ~C.COMM_NOWIZ
    act_new("{i[{I$n{i]: $t{x", ch, argument, None, C.TO_CHAR, C.POS_DEAD)
    for d in list(game_module.current.descriptor_list):
        if d.connected == C.CON_PLAYING and is_immortal(d.character) and not d.character.comm & C.COMM_NOWIZ:
            act_new("{i[{I$n{i]: $t{x", ch, argument, d.character, C.TO_VICT, C.POS_DEAD)


# C: act_comm.c do_say
def do_say(ch, argument: str) -> None:
    from charm.systems.mobprog import has_trigger, mp_act_trigger

    if argument == "":
        send_to_char("Say what?\n\r", ch)
        return
    act("{6$n says '{7$T{6'{x", ch, None, argument, C.TO_ROOM)
    act("{6You say '{7$T{6'{x", ch, None, argument, C.TO_CHAR)
    if not ch.is_npc:
        for mob in list(ch.in_room.people):
            if mob.is_npc and has_trigger(mob, C.TRIG_SPEECH) and mob.position == mob.index.default_pos:
                mp_act_trigger(argument, mob, ch, None, None, C.TRIG_SPEECH)


# C: act_comm.c do_shout
def do_shout(ch, argument: str) -> None:
    if argument == "":
        _toggle(ch, C.COMM_SHOUTSOFF, "You can hear shouts again.\n\r", "You will no longer hear shouts.\n\r")
        return
    if ch.comm & C.COMM_NOSHOUT:
        send_to_char("You can't shout.\n\r", ch)
        return
    ch.comm &= ~C.COMM_SHOUTSOFF
    wait_state(ch, 12)
    act("You shout '$T'", ch, None, argument, C.TO_CHAR)
    for d in list(game_module.current.descriptor_list):
        victim = ch_of(d)
        if (d.connected == C.CON_PLAYING and d.character is not ch and not victim.comm & C.COMM_SHOUTSOFF
                and not victim.comm & C.COMM_QUIET):
            act("$n shouts '$t'", ch, argument, d.character, C.TO_VICT)


def _keep_tell(ch, victim, argument: str) -> None:
    """A tell kept in the victim's buffer for replay."""
    from charm.entities.handler import pers
    from charm.entities.things import add_buf

    buf = "{k%s tells you '{K%s{k'{x\n\r" % (pers(ch, victim), argument)
    buf = upper(buf[0]) + buf[1:]  # the C capitalises the "{", which changes nothing
    add_buf(victim.pcdata.buffer, buf)


# C: act_comm.c do_tell
def do_tell(ch, argument: str) -> None:
    from charm.entities.handler import get_char_world, is_awake, is_immortal
    from charm.systems.mobprog import has_trigger, mp_act_trigger

    if ch.comm & C.COMM_NOTELL or ch.comm & C.COMM_DEAF:
        send_to_char("Your message didn't get through.\n\r", ch)
        return
    if ch.comm & C.COMM_QUIET:
        send_to_char("You must turn off quiet mode first.\n\r", ch)
        return
    if ch.comm & C.COMM_DEAF:  # sic: never true here, as the first test took deaf players (#52)
        send_to_char("You must turn off deaf mode first.\n\r", ch)
        return
    argument, arg = one_argument(argument)
    if arg == "" or argument == "":
        send_to_char("Tell whom what?\n\r", ch)
        return
    # "Can tell to PC's anywhere, but NPC's only in same room. -- Furey"
    victim = get_char_world(game_module.current, ch, arg)
    if victim is None or (victim.is_npc and victim.in_room is not ch.in_room):
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.desc is None and not victim.is_npc:
        act("$N seems to have misplaced $S link...try again later.", ch, None, victim, C.TO_CHAR)
        _keep_tell(ch, victim, argument)
        return
    if not (is_immortal(ch) and ch.level > C.LEVEL_IMMORTAL) and not is_awake(victim):
        act("$E can't hear you.", ch, None, victim, C.TO_CHAR)
        return
    if (victim.comm & C.COMM_QUIET or victim.comm & C.COMM_DEAF) and not is_immortal(ch):
        act("$E is not receiving tells.", ch, None, victim, C.TO_CHAR)
        return
    if victim.comm & C.COMM_AFK:
        if victim.is_npc:
            act("$E is AFK, and not receiving tells.", ch, None, victim, C.TO_CHAR)
            return
        act("$E is AFK, but your tell will go through when $E returns.", ch, None, victim, C.TO_CHAR)
        _keep_tell(ch, victim, argument)
        return
    if victim.desc is None:
        raise CWouldCrash("act_comm.c do_tell: a tell to a mob reads its connection's state, and a mob has no "
                          "connection (NULL dereference) (#49)")
    if C.CON_NOTE_TO <= victim.desc.connected <= C.CON_NOTE_FINISH:
        act("$E is writing a note, but your tell will go through when $E returns.", ch, None, victim, C.TO_CHAR)
        _keep_tell(ch, victim, argument)
        return
    act("{kYou tell $N '{K$t{k'{x", ch, argument, victim, C.TO_CHAR)
    act_new("{k$n tells you '{K$t{k'{x", ch, argument, victim, C.TO_VICT, C.POS_DEAD)
    victim.reply = ch
    if not ch.is_npc and victim.is_npc and has_trigger(victim, C.TRIG_SPEECH):
        mp_act_trigger(argument, victim, ch, None, None, C.TRIG_SPEECH)


# C: act_comm.c do_reply
def do_reply(ch, argument: str) -> None:
    from charm.entities.handler import is_awake, is_immortal

    if ch.comm & C.COMM_NOTELL:
        send_to_char("Your message didn't get through.\n\r", ch)
        return
    victim = ch.reply
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if victim.desc is None and not victim.is_npc:
        act("$N seems to have misplaced $S link...try again later.", ch, None, victim, C.TO_CHAR)
        _keep_tell(ch, victim, argument)
        return
    if not is_immortal(ch) and not is_awake(victim):
        act("$E can't hear you.", ch, None, victim, C.TO_CHAR)
        return
    if ((victim.comm & C.COMM_QUIET or victim.comm & C.COMM_DEAF) and not is_immortal(ch)
            and not is_immortal(victim)):
        act_new("$E is not receiving tells.", ch, None, victim, C.TO_CHAR, C.POS_DEAD)
        return
    if not is_immortal(victim) and not is_awake(ch):
        send_to_char("In your dreams, or what?\n\r", ch)
        return
    if victim.comm & C.COMM_AFK:
        if victim.is_npc:
            act_new("$E is AFK, and not receiving tells.", ch, None, victim, C.TO_CHAR, C.POS_DEAD)
            return
        act_new("$E is AFK, but your tell will go through when $E returns.", ch, None, victim, C.TO_CHAR,
                C.POS_DEAD)
        _keep_tell(ch, victim, argument)
        return
    act_new("{kYou tell $N '{K$t{k'{x", ch, argument, victim, C.TO_CHAR, C.POS_DEAD)
    act_new("{k$n tells you '{K$t{k'{x", ch, argument, victim, C.TO_VICT, C.POS_DEAD)
    victim.reply = ch


# C: act_comm.c do_yell
def do_yell(ch, argument: str) -> None:
    if ch.comm & C.COMM_NOSHOUT:
        send_to_char("You can't yell.\n\r", ch)
        return
    if argument == "":
        send_to_char("Yell what?\n\r", ch)
        return
    act("You yell '$t'", ch, argument, None, C.TO_CHAR)
    for d in list(game_module.current.descriptor_list):
        if (d.connected == C.CON_PLAYING and d.character is not ch and d.character.in_room is not None
                and d.character.in_room.area is ch.in_room.area and not d.character.comm & C.COMM_QUIET):
            act("$n yells '$t'", ch, argument, d.character, C.TO_VICT)


def _isalpha(c: str) -> bool:
    """isalpha in the C locale."""
    return "a" <= c <= "z" or "A" <= c <= "Z"


# C: act_comm.c do_emote
def do_emote(ch, argument: str) -> None:
    if not ch.is_npc and ch.comm & C.COMM_NOEMOTE:
        send_to_char("You can't show your emotions.\n\r", ch)
        return
    if argument == "":
        send_to_char("Emote what?\n\r", ch)
        return
    # "little hack to fix the ',{' bug posted to rom list around 4/16/01 -- JR"
    if not _isalpha(argument[0]):
        send_to_char("Moron!\n\r", ch)
        return
    MOB_TRIGGER[0] = False
    act("$n $T", ch, None, argument, C.TO_ROOM)
    act("$n $T", ch, None, argument, C.TO_CHAR)
    MOB_TRIGGER[0] = True


# C: act_comm.c do_pmote
def do_pmote(ch, argument: str) -> None:
    """An emote that each player in the room sees with their own name turned into "you" (and "Name's" into
    "your")."""
    matches = 0  # sic: once, not for each player, so a partial match runs on into the next one's name (#54)
    if not ch.is_npc and ch.comm & C.COMM_NOEMOTE:
        send_to_char("You can't show your emotions.\n\r", ch)
        return
    if argument == "":
        send_to_char("Emote what?\n\r", ch)
        return
    # "little hack to fix the ',{' bug posted to rom list around 4/16/01 -- JR"
    if not _isalpha(argument[0]):
        send_to_char("Moron!\n\r", ch)
        return
    act("$n $t", ch, argument, None, C.TO_CHAR)
    for vch in list(ch.in_room.people):
        if vch.desc is None or vch is ch:
            continue
        name = vch.name
        at = argument.find(name)
        if at < 0:
            MOB_TRIGGER[0] = False
            act("$N $t", vch, argument, ch, C.TO_CHAR)
            MOB_TRIGGER[0] = True
            continue
        temp, last, n = [argument[:at]], [], 0  # n: where the C's name pointer is in vch->name
        for letter in argument[at:]:
            if letter == "'" and matches == len(name):
                temp.append("r")
                continue
            if letter == "s" and matches == len(name):
                matches = 0
                continue
            if matches == len(name):
                matches = 0
            if n < len(name) and letter == name[n]:  # past the end, the C compares with the NUL
                matches += 1
                n += 1
                if matches == len(name):
                    temp.append("you")
                    last = []
                    n = 0
                    continue
                last.append(letter)
                continue
            matches = 0
            temp += last
            temp.append(letter)
            last = []
            n = 0
        # sic: a partial match left in last at the end is dropped (#54)
        MOB_TRIGGER[0] = False
        act("$N $t", vch, "".join(temp), ch, C.TO_CHAR)
        MOB_TRIGGER[0] = True


# C: act_comm.c do_pose
def do_pose(ch, argument: str) -> None:
    from charm.core.rng import number_range
    from charm.data.classes import POSE_TABLE

    if ch.is_npc:
        return
    level = min(ch.level, len(POSE_TABLE) - 1)
    pose = number_range(0, level)
    act(POSE_TABLE[pose][0][2 * ch.class_ + 0], ch, None, None, C.TO_CHAR)
    act(POSE_TABLE[pose][0][2 * ch.class_ + 1], ch, None, None, C.TO_ROOM)


# C: act_comm.c do_typo
def do_typo(ch, argument: str) -> None:
    from charm.commands.info import append_file

    append_file(ch, C.TYPO_FILE, argument)
    send_to_char("Typo logged.\n\r", ch)


# C: act_comm.c do_rent
def do_rent(ch, argument: str) -> None:
    send_to_char("There is no rent here.  Just save and quit.\n\r", ch)


# C: act_comm.c do_qui
def do_qui(ch, argument: str) -> None:
    # sic: never runs, as "qui" finds quiet first in the command table (#55)
    send_to_char("If you want to QUIT, you have to spell it out.\n\r", ch)


# C: act_comm.c do_quit
def do_quit(ch, argument: str) -> None:
    from charm.entities.handler import extract_char, get_trust
    from charm.net.server import close_socket
    from charm.persist.player import save_char_obj

    game = game_module.current
    if ch.is_npc:
        return
    if ch.position == C.POS_FIGHTING:
        send_to_char("No way! You are fighting.\n\r", ch)
        return
    if ch.position < C.POS_STUNNED:
        send_to_char("You're not DEAD yet.\n\r", ch)
        return
    send_to_char("Alas, all good things must come to an end.\n\r", ch)
    act("$n has left the game.", ch, None, None, C.TO_ROOM)
    log_string(f"{ch.name} has quit.")
    wiznet(game, "$N rejoins the real world.", ch, None, C.WIZ_LOGINS, 0, get_trust(ch))
    # "After extract_char the ch is no longer valid!"
    save_char_obj(game, ch)
    if ch.pcdata.in_progress is not None:  # "Free note that might be there somehow"
        from charm.persist.boards import free_note

        free_note(ch.pcdata.in_progress)
    pid, d = ch.id, ch.desc
    extract_char(game, ch, True)
    if d is not None:
        close_socket(d)
    # "toast evil cheating bastards"
    for d in list(game.descriptor_list):
        tch = ch_of(d)
        if tch is not None and tch.id == pid:
            extract_char(game, tch, True)
            close_socket(d)


# C: act_comm.c do_save
def do_save(ch, argument: str) -> None:
    from charm.persist.player import save_char_obj

    if ch.is_npc:
        return
    save_char_obj(game_module.current, ch)
    send_to_char(SAVING, ch)
    wait_state(ch, 4 * C.PULSE_VIOLENCE)


# C: act_comm.c do_follow
def do_follow(ch, argument: str) -> None:
    from charm.entities.handler import get_char_room, is_affected, is_immortal

    # "RT changed to allow unlimited following and follow the NOFOLLOW rules"
    game = game_module.current
    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Follow whom?\n\r", ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM) and ch.master is not None:
        act("But you'd rather follow $N!", ch, None, ch.master, C.TO_CHAR)
        return
    if victim is ch:
        if ch.master is None:
            send_to_char("You already follow yourself.\n\r", ch)
            return
        stop_follower(game, ch)
        return
    if not victim.is_npc and victim.act & C.PLR_NOFOLLOW and not is_immortal(ch):
        # sic: act adds its own line end, so this sends an empty line after it (#53)
        act("$N doesn't seem to want any followers.\n\r", ch, None, victim, C.TO_CHAR)
        return
    ch.act &= ~C.PLR_NOFOLLOW
    if ch.master is not None:
        stop_follower(game, ch)
    add_follower(game, ch, victim)


# C: act_comm.c add_follower
def add_follower(game, ch, master) -> None:
    from charm.entities.handler import can_see

    if ch.master is not None:
        bug("Add_follower: non-null master.", 0)
        return
    ch.master = master
    ch.leader = None
    if can_see(master, ch):
        act("$n now follows you.", ch, None, master, C.TO_VICT)
    act("You now follow $N.", ch, None, master, C.TO_CHAR)


# C: act_comm.c stop_follower
def stop_follower(game, ch) -> None:
    from charm.entities.handler import affect_strip, can_see, is_affected
    from charm.world.lookup import GSN

    if ch.master is None:
        bug("Stop_follower: null master.", 0)
        return
    if is_affected(ch, C.AFF_CHARM):
        ch.affected_by &= ~C.AFF_CHARM
        affect_strip(ch, GSN["gsn_charm_person"])
    if can_see(ch.master, ch) and ch.in_room is not None:
        act("$n stops following you.", ch, None, ch.master, C.TO_VICT)
        act("You stop following $N.", ch, None, ch.master, C.TO_CHAR)
    if ch.master.pet is ch:
        ch.master.pet = None
    ch.master = None
    ch.leader = None


# C: act_comm.c nuke_pets
def nuke_pets(game, ch) -> None:
    from charm.entities.handler import extract_char

    pet = ch.pet
    if pet is not None:
        stop_follower(game, pet)
        if pet.in_room is not None:
            act("$N slowly fades away.", ch, None, pet, C.TO_NOTVICT)
        extract_char(game, pet, True)
    ch.pet = None


# C: act_comm.c die_follower
def die_follower(game, ch) -> None:
    if ch.master is not None:
        if ch.master.pet is ch:
            ch.master.pet = None
        stop_follower(game, ch)
    ch.leader = None
    for fch in list(game.char_list):
        if fch.master is ch:
            stop_follower(game, fch)
        if fch.leader is ch:
            fch.leader = fch


# C: act_comm.c do_order
def do_order(ch, argument: str) -> None:
    from charm.commands.interp import interpret
    from charm.entities.handler import get_char_room, is_affected, is_immortal

    argument, arg = one_argument(argument)
    _, arg2 = one_argument(argument)
    if str_cmp(arg2, "delete") or str_cmp(arg2, "mob"):
        send_to_char("That will NOT be done.\n\r", ch)
        return
    if arg == "" or argument == "":
        send_to_char("Order whom to do what?\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM):
        send_to_char("You feel like taking, not giving, orders.\n\r", ch)
        return
    if str_cmp(arg, "all"):
        f_all, victim = True, None
    else:
        f_all = False
        victim = get_char_room(ch, arg)
        if victim is None:
            send_to_char("They aren't here.\n\r", ch)
            return
        if victim is ch:
            send_to_char("Aye aye, right away!\n\r", ch)
            return
        if (not is_affected(victim, C.AFF_CHARM) or victim.master is not ch
                or (is_immortal(victim) and victim.trust >= ch.trust)):
            send_to_char("Do it yourself!\n\r", ch)
            return
    found = False
    for och in list(ch.in_room.people):
        if is_affected(och, C.AFF_CHARM) and och.master is ch and (f_all or och is victim):
            found = True
            act("$n orders you to '%s'." % argument, ch, None, och, C.TO_VICT)  # the order's own $ codes too
            interpret(och, argument)
    if found:
        wait_state(ch, C.PULSE_VIOLENCE)
        send_to_char("Ok.\n\r", ch)
    else:
        send_to_char("You have no followers here.\n\r", ch)


# C: act_comm.c do_group
def do_group(ch, argument: str) -> None:
    from charm.data.classes import CLASS_TABLE
    from charm.entities.handler import get_char_room, is_affected, pers
    from charm.persist.player import capitalize

    _, arg = one_argument(argument)
    if arg == "":
        leader = ch.leader if ch.leader is not None else ch
        send_to_char("%s's group:\n\r" % pers(leader, ch), ch)
        for gch in list(game_module.current.char_list):
            if is_same_group(gch, ch):
                send_to_char("[%2d %s] %-16s %4d/%4d hp %4d/%4d mana %4d/%4d mv %5d xp\n\r" % (
                    gch.level, "Mob" if gch.is_npc else CLASS_TABLE[gch.class_].who_name,
                    capitalize(pers(gch, ch)), gch.hit, gch.max_hit, gch.mana, gch.max_mana, gch.move,
                    gch.max_move, gch.exp), ch)
        return
    victim = get_char_room(ch, arg)
    if victim is None:
        send_to_char("They aren't here.\n\r", ch)
        return
    if ch.master is not None or (ch.leader is not None and ch.leader is not ch):
        send_to_char("But you are following someone else!\n\r", ch)
        return
    if victim.master is not ch and ch is not victim:
        act_new("$N isn't following you.", ch, None, victim, C.TO_CHAR, C.POS_SLEEPING)
        return
    if is_affected(victim, C.AFF_CHARM):
        send_to_char("You can't remove charmed mobs from your group.\n\r", ch)
        return
    if is_affected(ch, C.AFF_CHARM):
        act_new("You like your master too much to leave $m!", ch, None, victim, C.TO_VICT, C.POS_SLEEPING)
        return
    if is_same_group(victim, ch) and ch is not victim:
        victim.leader = None
        act_new("$n removes $N from $s group.", ch, None, victim, C.TO_NOTVICT, C.POS_RESTING)
        act_new("$n removes you from $s group.", ch, None, victim, C.TO_VICT, C.POS_SLEEPING)
        act_new("You remove $N from your group.", ch, None, victim, C.TO_CHAR, C.POS_SLEEPING)
        return
    victim.leader = ch
    act_new("$N joins $n's group.", ch, None, victim, C.TO_NOTVICT, C.POS_RESTING)
    act_new("You join $n's group.", ch, None, victim, C.TO_VICT, C.POS_SLEEPING)
    act_new("$N joins your group.", ch, None, victim, C.TO_CHAR, C.POS_SLEEPING)


# C: act_comm.c do_split
def do_split(ch, argument: str) -> None:
    """'Split' originally by Gnort, God of Chaos."""
    from charm.entities.handler import is_affected

    argument, arg1 = one_argument(argument)
    _, arg2 = one_argument(argument)
    if arg1 == "":
        send_to_char("Split how much?\n\r", ch)
        return
    amount_silver = atoi(arg1)
    amount_gold = atoi(arg2) if arg2 != "" else 0
    if amount_gold < 0 or amount_silver < 0:
        send_to_char("Your group wouldn't like that.\n\r", ch)
        return
    if amount_gold == 0 and amount_silver == 0:
        send_to_char("You hand out zero coins, but no one notices.\n\r", ch)
        return
    if ch.gold < amount_gold or ch.silver < amount_silver:
        send_to_char("You don't have that much to split.\n\r", ch)
        return
    members = 0
    for gch in ch.in_room.people:
        if is_same_group(gch, ch) and not is_affected(gch, C.AFF_CHARM):
            members += 1
    if members < 2:
        send_to_char("Just keep it all.\n\r", ch)
        return
    share_silver = amount_silver // members  # non-negative: checked above
    extra_silver = amount_silver % members  # non-negative: checked above
    share_gold = amount_gold // members  # non-negative: checked above
    extra_gold = amount_gold % members  # non-negative: checked above
    if share_gold == 0 and share_silver == 0:
        send_to_char("Don't even bother, cheapskate.\n\r", ch)
        return
    ch.silver -= amount_silver
    ch.silver += share_silver + extra_silver
    ch.gold -= amount_gold
    ch.gold += share_gold + extra_gold
    if share_silver > 0:
        send_to_char("You split %d silver coins. Your share is %d silver.\n\r"
                     % (amount_silver, share_silver + extra_silver), ch)
    if share_gold > 0:
        send_to_char("You split %d gold coins. Your share is %d gold.\n\r" % (amount_gold, share_gold + extra_gold),
                     ch)
    if share_gold == 0:
        buf = "$n splits %d silver coins. Your share is %d silver." % (amount_silver, share_silver)
    elif share_silver == 0:
        buf = "$n splits %d gold coins. Your share is %d gold." % (amount_gold, share_gold)
    else:
        # sic: act adds its own line end, so this sends an empty line after it (#53)
        buf = ("$n splits %d silver and %d gold coins, giving you %d silver and %d gold.\n\r"
               % (amount_silver, amount_gold, share_silver, share_gold))
    for gch in list(ch.in_room.people):
        if gch is not ch and is_same_group(gch, ch) and not is_affected(gch, C.AFF_CHARM):
            act(buf, ch, None, gch, C.TO_VICT)
            gch.gold += share_gold
            gch.silver += share_silver


# C: act_comm.c do_gtell
def do_gtell(ch, argument: str) -> None:
    if argument == "":
        send_to_char("Tell your group what?\n\r", ch)
        return
    if ch.comm & C.COMM_NOTELL:
        send_to_char("Your message didn't get through!\n\r", ch)
        return
    for gch in list(game_module.current.char_list):
        if is_same_group(gch, ch):
            act_new("$n tells the group '$t'", ch, argument, gch, C.TO_VICT, C.POS_SLEEPING)


# C: act_comm.c is_same_group
def is_same_group(ach, bch) -> bool:
    """"It is very important that this be an equivalence relation"."""
    if ach is None or bch is None:
        return False
    if ach.leader is not None:
        ach = ach.leader
    if bch.leader is not None:
        bch = bch.leader
    return ach is bch


# ALTER_COLOUR's words, in its order: (word, (bright, colour)), or (word, beep) for the beep words.
_ALTER_COLOUR = (
    ("red", (C.NORMAL, C.RED)), ("hi-red", (C.BRIGHT, C.RED)), ("green", (C.NORMAL, C.GREEN)),
    ("hi-green", (C.BRIGHT, C.GREEN)), ("yellow", (C.NORMAL, C.YELLOW)), ("hi-yellow", (C.BRIGHT, C.YELLOW)),
    ("blue", (C.NORMAL, C.BLUE)), ("hi-blue", (C.BRIGHT, C.BLUE)), ("magenta", (C.NORMAL, C.MAGENTA)),
    ("hi-magenta", (C.BRIGHT, C.MAGENTA)), ("cyan", (C.NORMAL, C.CYAN)), ("hi-cyan", (C.BRIGHT, C.CYAN)),
    ("white", (C.NORMAL, C.WHITE)), ("hi-white", (C.BRIGHT, C.WHITE)), ("grey", (C.BRIGHT, C.BLACK)),
    ("beep", 1), ("nobeep", 0),
)


def _alter_colour(ch, field: str, argument: str) -> bool:
    """ALTER_COLOUR (merc.h): False, having said so, if the colour isn't one of its words. The word may be cut
    short ("hi-r"), and an empty one is "red"."""
    from charm.core.strings import str_prefix

    setting = ch.pcdata.colours[field]
    for word, value in _ALTER_COLOUR:
        if str_prefix(argument, word):
            if isinstance(value, tuple):
                setting[0], setting[1] = value
            else:
                setting[2] = value
            return True
    send_to_char_bw("Unrecognised colour, unchanged.\n\r", ch)
    return False


# C: act_comm.c do_colour
def do_colour(ch, argument: str) -> None:
    """"ColoUr setting and unsetting, way cool, Ant Oct 94, revised to include config colour, Ant Feb 95"."""
    from charm.entities.handler import all_colour, default_colour
    from charm.entities.things import COLOUR_FIELDS

    if ch.is_npc:
        send_to_char_bw("ColoUr is not ON, Way Moron!\n\r", ch)
        return
    argument, arg = one_argument(argument)
    if arg == "":
        if not ch.act & C.PLR_COLOUR:
            ch.act |= C.PLR_COLOUR
            send_to_char("ColoUr is now ON, Way Cool!\n\r"
                         "Further syntax:\n\r   colour {c<{xfield{c> <{xcolour{c>{x\n\r"
                         "   colour {c<{xfield{c>{x {cbeep{x|{cnobeep{x\n\r"
                         "Type help {ccolour{x and {ccolour2{x for details.\n\r"
                         "ColoUr is brought to you by Lope, ant@solace.mh.se.\n\r", ch)
        else:
            send_to_char_bw("ColoUr is now OFF, <sigh>\n\r", ch)
            ch.act &= ~C.PLR_COLOUR
        return
    if str_cmp(arg, "default"):
        default_colour(ch)
        send_to_char_bw("ColoUr setting set to default values.\n\r", ch)
        return
    if str_cmp(arg, "all"):
        all_colour(ch, argument)
        return
    # "Yes, I know this is ugly and unnessessary repetition, but its old and I can't justify the time to make it
    # pretty. -Lope"
    for field in COLOUR_FIELDS:
        if str_cmp(arg, field):
            if not _alter_colour(ch, field, argument):
                return
            break
    else:
        send_to_char_bw("Unrecognised Colour Parameter Not Set.\n\r", ch)
        return
    send_to_char_bw("New Colour Parameter Set.\n\r", ch)
