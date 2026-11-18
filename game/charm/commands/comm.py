"""act_comm.c's save and quit, and the follower helpers that quitting reaches (nuke_pets, die_follower).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import NotPorted
from charm.core.log import bug, log_string
from charm.data import constants as C
from charm.entities import game as game_module
from charm.net.act import act
from charm.net.output import send_to_char
from charm.net.wiznet import wiznet

SAVING = "Saving. Remember that Charm has automatic saving now.\n\r"


def wait_state(ch, npulse: int) -> None:
    """WAIT_STATE: lag of at least npulse pulses."""
    ch.wait = max(ch.wait, npulse)


# C: act_comm.c do_save
def do_save(ch, argument: str) -> None:
    from charm.persist.player import save_char_obj

    if ch.is_npc:
        return
    save_char_obj(game_module.current, ch)
    send_to_char(SAVING, ch)
    wait_state(ch, 4 * C.PULSE_VIOLENCE)


# C: act_comm.c do_quit [partial]
def do_quit(ch, argument: str) -> None:
    """[partial]: a note being written (free_note) raises NotPorted."""
    from charm.entities.handler import extract_char, get_trust
    from charm.net.descriptor import ch_of
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
    if ch.pcdata.in_progress is not None:
        raise NotPorted("act_comm.c do_quit: free_note (a note in progress)")
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
