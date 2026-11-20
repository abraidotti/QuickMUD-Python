"""mob_prog.c's triggers that looking, moving and act() reach: which mob program, if any, should run.

The scans are ported whole. Running a program (program_flow, the mob program interpreter) isn't, and raises
NotPorted. No stock area has mob programs, so in the spike a trigger finds nothing and returns.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/mob_prog.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import NotPorted
from charm.core.rng import number_percent
from charm.core.strings import atoi
from charm.data import constants as C


def has_trigger(mob, trig: int) -> bool:
    """HAS_TRIGGER."""
    return bool(mob.index.mprog_flags & trig)


def program_flow(vnum: int, code: str, mob, ch, arg1, arg2) -> None:
    raise NotPorted(f"mob_prog.c program_flow (mob program {vnum})")


# C: mob_prog.c mp_act_trigger
def mp_act_trigger(argument: str, mob, ch, arg1, arg2, kind: int) -> None:
    if not mob.is_npc:
        return
    for prg in mob.index.mprogs:
        if prg.trig_type == kind and prg.trig_phrase in argument:
            program_flow(prg.vnum, prg.code, mob, ch, arg1, arg2)
            break


# C: mob_prog.c mp_percent_trigger
def mp_percent_trigger(mob, ch, arg1, arg2, kind: int) -> bool:
    for prg in mob.index.mprogs:
        if prg.trig_type == kind and number_percent() < atoi(prg.trig_phrase):
            program_flow(prg.vnum, prg.code, mob, ch, arg1, arg2)
            return True
    return False


# C: mob_prog.c mp_greet_trigger
def mp_greet_trigger(ch) -> None:
    from charm.entities.handler import can_see

    for mob in list(ch.in_room.people):
        if mob.is_npc and (has_trigger(mob, C.TRIG_GREET) or has_trigger(mob, C.TRIG_GRALL)):
            # "Greet trigger works only if the mobile is not busy (fighting etc.). If you want to catch all
            # players, use GrAll trigger"
            if has_trigger(mob, C.TRIG_GREET) and mob.position == mob.index.default_pos and can_see(mob, ch):
                mp_percent_trigger(mob, ch, None, None, C.TRIG_GREET)
            elif has_trigger(mob, C.TRIG_GRALL):
                mp_percent_trigger(mob, ch, None, None, C.TRIG_GRALL)


# C: mob_prog.c mp_exit_trigger
def mp_exit_trigger(ch, door: int) -> bool:
    from charm.entities.handler import can_see

    for mob in list(ch.in_room.people):
        if mob.is_npc and (has_trigger(mob, C.TRIG_EXIT) or has_trigger(mob, C.TRIG_EXALL)):
            for prg in mob.index.mprogs:
                # "Exit trigger works only if the mobile is not busy (fighting etc.). If you want to be sure all
                # players are caught, use ExAll trigger"
                if (prg.trig_type == C.TRIG_EXIT and door == atoi(prg.trig_phrase)
                        and mob.position == mob.index.default_pos and can_see(mob, ch)):
                    program_flow(prg.vnum, prg.code, mob, ch, None, None)
                    return True
                elif prg.trig_type == C.TRIG_EXALL and door == atoi(prg.trig_phrase):
                    program_flow(prg.vnum, prg.code, mob, ch, None, None)
                    return True
    return False


# C: mob_prog.c mp_bribe_trigger
def mp_bribe_trigger(mob, ch, amount: int) -> None:
    # "Original MERC 2.2 MOBprograms used to create a money object and give it to the mobile. WFT was that? Funcs
    # in act_obj() handle it just fine."
    for prg in mob.index.mprogs:
        if prg.trig_type == C.TRIG_BRIBE and amount >= atoi(prg.trig_phrase):
            program_flow(prg.vnum, prg.code, mob, ch, None, None)
            break


# C: mob_prog.c mp_give_trigger
def mp_give_trigger(mob, ch, obj) -> None:
    from charm.commands.interp import is_number, one_argument
    from charm.core.strings import str_cmp
    from charm.entities.handler import is_name

    for prg in mob.index.mprogs:
        if prg.trig_type != C.TRIG_GIVE:
            continue
        p = prg.trig_phrase
        if is_number(p):  # "Vnum argument"
            if obj.index.vnum == atoi(p):
                program_flow(prg.vnum, prg.code, mob, ch, obj, None)
                return
        else:  # "Object name argument, e.g. 'sword'"
            while p:
                p, buf = one_argument(p)
                if is_name(buf, obj.name) or str_cmp("all", buf):
                    program_flow(prg.vnum, prg.code, mob, ch, obj, None)
                    return


# C: mob_prog.c mp_hprct_trigger
def mp_hprct_trigger(mob, ch) -> None:
    from charm.core.cint import c_div

    for prg in mob.index.mprogs:
        if prg.trig_type == C.TRIG_HPCNT:
            if mob.max_hit == 0:
                from charm.core.errors import CWouldCrash

                raise CWouldCrash("mob_prog.c mp_hprct_trigger: divides by the mob's max_hit, which is 0")
            if c_div(100 * mob.hit, mob.max_hit) < atoi(prg.trig_phrase):
                program_flow(prg.vnum, prg.code, mob, ch, None, None)
                break
