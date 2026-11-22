"""Skills and skill groups: what a new character knows and may buy, and the experience a level costs.

Ported from skills.c. The C's sprintf formats are kept as Python's % formatting, which pads the same way.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/skills.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import is_number, one_argument
from quickmud.core.cint import c_div
from quickmud.core.errors import CWouldCrash
from quickmud.core.strings import atoi, str_cmp, str_prefix
from quickmud.data import constants as C
from quickmud.data.races import PC_RACE_TABLE
from quickmud.data.skills import GROUP_TABLE, SKILL_TABLE
from quickmud.net.output import page_to_char, send_to_char
from quickmud.world.areafile.lookups import prefix_lookup
from quickmud.world.lookup import skill_lookup

_GROUPS = [g.name for g in GROUP_TABLE]


def _spell_null(sn: int) -> bool:
    return SKILL_TABLE[sn].spell_fun == "spell_null"


# C: skills.c exp_per_level
def exp_per_level(ch, points: int) -> int:
    if ch.is_npc:
        return 1000
    expl, inc = 1000, 500
    mult = PC_RACE_TABLE[ch.race].class_mult[ch.class_]
    if points < 40:
        return 1000 * (c_div(mult, 100) if mult else 1)  # a multiplier of 150 counts as 1 here
    points -= 40
    while points > 9:
        expl += inc
        points -= 10
        if points > 9:
            expl += inc
            inc *= 2
            points -= 10
    expl += c_div(points * inc, 10)
    return c_div(expl * mult, 100)


# C: skills.c group_lookup
def group_lookup(name: str) -> int:
    return prefix_lookup(name, _GROUPS)


# C: skills.c gn_add
def gn_add(ch, gn: int) -> None:
    ch.pcdata.group_known[gn] = True
    for spell in GROUP_TABLE[gn].spells:
        if spell is None:
            break
        group_add(ch, spell, False)


# C: skills.c gn_remove
def gn_remove(ch, gn: int) -> None:
    ch.pcdata.group_known[gn] = False
    for spell in GROUP_TABLE[gn].spells:
        if spell is None:
            break
        group_remove(ch, spell)


# C: skills.c group_add
def group_add(ch, name: str, deduct: bool) -> None:
    if ch.is_npc:  # NPCs do not have skills
        return
    sn = skill_lookup(name)
    if sn != -1:
        if ch.pcdata.learned[sn] == 0:  # i.e. not known
            ch.pcdata.learned[sn] = 1
            if deduct:
                ch.pcdata.points += SKILL_TABLE[sn].rating[ch.class_]
        return
    gn = group_lookup(name)
    if gn != -1:
        if not ch.pcdata.group_known[gn]:
            ch.pcdata.group_known[gn] = True
            if deduct:
                ch.pcdata.points += GROUP_TABLE[gn].rating[ch.class_]
        gn_add(ch, gn)  # make sure all skills in the group are known


# C: skills.c group_remove
def group_remove(ch, name: str) -> None:
    sn = skill_lookup(name)
    if sn != -1:
        ch.pcdata.learned[sn] = 0
        return
    gn = group_lookup(name)
    if gn != -1 and ch.pcdata.group_known[gn]:
        ch.pcdata.group_known[gn] = False
        gn_remove(ch, gn)


def _columns(ch, entries: list[str]) -> None:
    col = 0
    for text in entries:
        send_to_char(text, ch)
        col += 1
        if col % 3 == 0:  # non-negative: a count
            send_to_char("\n\r", ch)
    if col % 3 != 0:  # non-negative: a count
        send_to_char("\n\r", ch)


# C: skills.c list_group_costs
def list_group_costs(ch) -> None:
    if ch.is_npc:
        return
    gen, pc, cls = ch.gen_data, ch.pcdata, ch.class_
    send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s\n\r" % ("group", "cp", "group", "cp", "group", "cp"), ch)
    _columns(ch, ["%-18s %-5d " % (g.name, g.rating[cls]) for gn, g in enumerate(GROUP_TABLE)
                  if not gen.group_chosen[gn] and not pc.group_known[gn] and g.rating[cls] > 0])
    send_to_char("\n\r", ch)
    send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s\n\r" % ("skill", "cp", "skill", "cp", "skill", "cp"), ch)
    _columns(ch, ["%-18s %-5d " % (s.name, s.rating[cls]) for sn, s in enumerate(SKILL_TABLE)
                  if not gen.skill_chosen[sn] and pc.learned[sn] == 0 and _spell_null(sn) and s.rating[cls] > 0])
    send_to_char("\n\r", ch)
    send_to_char("Creation points: %d\n\r" % pc.points, ch)
    send_to_char("Experience per level: %d\n\r" % exp_per_level(ch, gen.points_chosen), ch)


# C: skills.c list_group_chosen
def list_group_chosen(ch) -> None:
    if ch.is_npc:
        return
    gen, cls = ch.gen_data, ch.class_
    send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s" % ("group", "cp", "group", "cp", "group", "cp\n\r"), ch)
    _columns(ch, ["%-18s %-5d " % (g.name, g.rating[cls]) for gn, g in enumerate(GROUP_TABLE)
                  if gen.group_chosen[gn] and g.rating[cls] > 0])
    send_to_char("\n\r", ch)
    send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s" % ("skill", "cp", "skill", "cp", "skill", "cp\n\r"), ch)
    _columns(ch, ["%-18s %-5d " % (s.name, s.rating[cls]) for sn, s in enumerate(SKILL_TABLE)
                  if gen.skill_chosen[sn] and s.rating[cls] > 0])
    send_to_char("\n\r", ch)
    send_to_char("Creation points: %d\n\r" % gen.points_chosen, ch)
    send_to_char("Experience per level: %d\n\r" % exp_per_level(ch, gen.points_chosen), ch)


# C: skills.c parse_gen_groups
def parse_gen_groups(ch, argument: str) -> bool:
    from quickmud.commands.info import do_help

    if argument == "":
        return False
    argument, arg = one_argument(argument)
    gen, pc, cls = ch.gen_data, ch.pcdata, ch.class_

    if str_prefix(arg, "help"):
        do_help(ch, "group help" if argument == "" else argument)
        return True

    if str_prefix(arg, "add"):
        if argument == "":
            send_to_char("You must provide a skill name.\n\r", ch)
            return True
        gn = group_lookup(argument)
        if gn != -1:
            rating = GROUP_TABLE[gn].rating[cls]
            if gen.group_chosen[gn] or pc.group_known[gn]:
                send_to_char("You already know that group!\n\r", ch)
            elif rating < 1:
                send_to_char("That group is not available.\n\r", ch)
            elif gen.points_chosen + rating > 300:  # "Close security hole"
                send_to_char("You cannot take more than 300 creation points.\n\r", ch)
            else:
                send_to_char("%s group added\n\r" % GROUP_TABLE[gn].name, ch)
                gen.group_chosen[gn] = True
                gen.points_chosen += rating
                gn_add(ch, gn)
                pc.points += rating
            return True
        sn = skill_lookup(argument)
        if sn != -1:
            rating = SKILL_TABLE[sn].rating[cls]
            if gen.skill_chosen[sn] or pc.learned[sn] > 0:
                send_to_char("You already know that skill!\n\r", ch)
            elif rating < 1 or not _spell_null(sn):
                send_to_char("That skill is not available.\n\r", ch)
            elif gen.points_chosen + rating > 300:
                send_to_char("You cannot take more than 300 creation points.\n\r", ch)
            else:
                send_to_char("%s skill added\n\r" % SKILL_TABLE[sn].name, ch)
                gen.skill_chosen[sn] = True
                gen.points_chosen += rating
                pc.learned[sn] = 1
                pc.points += rating
            return True
        send_to_char("No skills or groups by that name...\n\r", ch)
        return True

    if arg == "drop":
        if argument == "":
            send_to_char("You must provide a skill to drop.\n\r", ch)
            return True
        gn = group_lookup(argument)
        if gn != -1 and gen.group_chosen[gn]:
            send_to_char("Group dropped.\n\r", ch)
            gen.group_chosen[gn] = False
            gen.points_chosen -= GROUP_TABLE[gn].rating[cls]
            gn_remove(ch, gn)
            for _ in range(C.MAX_GROUP):  # the C tests group_chosen[gn], just cleared, not [i]: this never adds
                if gen.group_chosen[gn]:
                    gn_add(ch, gn)
            pc.points -= GROUP_TABLE[gn].rating[cls]
            return True
        sn = skill_lookup(argument)
        if sn != -1 and gen.skill_chosen[sn]:
            send_to_char("Skill dropped.\n\r", ch)
            gen.skill_chosen[sn] = False
            gen.points_chosen -= SKILL_TABLE[sn].rating[cls]
            pc.learned[sn] = 0
            pc.points -= SKILL_TABLE[sn].rating[cls]
            return True
        send_to_char("You haven't bought any such skill or group.\n\r", ch)
        return True

    if str_prefix(arg, "premise"):
        do_help(ch, "premise")
        return True
    if str_prefix(arg, "list"):
        list_group_costs(ch)
        return True
    if str_prefix(arg, "learned"):
        list_group_chosen(ch)
        return True
    if str_prefix(arg, "info"):
        do_groups(ch, argument)
        return True
    return False


# C: skills.c do_skills
def do_skills(ch, argument: str) -> None:
    if ch.is_npc:
        return
    fall, min_lev, max_lev = False, 1, C.LEVEL_HERO
    if argument != "":
        fall = True
        if not str_prefix(argument, "all"):
            argument, arg = one_argument(argument)
            if not is_number(arg):
                send_to_char("Arguments must be numerical or all.\n\r", ch)
                return
            max_lev = atoi(arg)
            if max_lev < 1 or max_lev > C.LEVEL_HERO:
                send_to_char("Levels must be between 1 and %d.\n\r" % C.LEVEL_HERO, ch)
                return
            if argument != "":
                argument, arg = one_argument(argument)
                if not is_number(arg):
                    send_to_char("Arguments must be numerical or all.\n\r", ch)
                    return
                min_lev, max_lev = max_lev, atoi(arg)
                if max_lev < 1 or max_lev > C.LEVEL_HERO:
                    send_to_char("Levels must be between 1 and %d.\n\r" % C.LEVEL_HERO, ch)
                    return
                if min_lev > max_lev:
                    send_to_char("That would be silly.\n\r", ch)
                    return
    lists = [""] * (C.LEVEL_HERO + 1)
    columns = [0] * (C.LEVEL_HERO + 1)
    found = False
    for sn, s in enumerate(SKILL_TABLE):
        level = s.skill_level[ch.class_]
        if (level < C.LEVEL_HERO + 1 and (fall or level <= ch.level) and min_lev <= level <= max_lev
                and _spell_null(sn) and ch.pcdata.learned[sn] > 0):
            found = True
            if ch.level < level:
                buf = "%-18s n/a      " % s.name
            else:
                buf = "%-18s %3d%%      " % (s.name, ch.pcdata.learned[sn])
            if lists[level] == "":
                lists[level] = "\n\rLevel %2d: %s" % (level, buf)
            else:
                columns[level] += 1
                if columns[level] % 2 == 0:  # non-negative: a count
                    lists[level] += "\n\r          "
                lists[level] += buf
    if not found:
        send_to_char("No skills found.\n\r", ch)
        return
    page_to_char("".join(x for x in lists if x) + "\n\r", ch)


# C: skills.c do_groups
def do_groups(ch, argument: str) -> None:
    if ch.is_npc:
        return
    if argument == "":  # show all groups
        _columns(ch, ["%-20s " % g.name for gn, g in enumerate(GROUP_TABLE) if ch.pcdata.group_known[gn]])
        send_to_char("Creation points: %d\n\r" % ch.pcdata.points, ch)
        return
    if str_cmp(argument, "all"):
        _columns(ch, ["%-20s " % g.name for g in GROUP_TABLE])
        return
    gn = group_lookup(argument)
    if gn == -1:
        send_to_char("No group of that name exist.\n\r", ch)
        send_to_char("Type 'groups all' or 'info all' for a full listing.\n\r", ch)
        return
    _columns(ch, ["%-20s " % s for s in GROUP_TABLE[gn].spells if s is not None])


# C: skills.c check_improve
def check_improve(ch, sn: int, success: bool, multiplier: int) -> None:
    from quickmud.core.rng import number_percent, number_range
    from quickmud.data.attributes import INT_APP
    from quickmud.entities.handler import get_curr_stat
    from quickmud.systems.update import gain_exp

    if ch.is_npc:
        return
    # No caller passes -1 today (#104). Python's [-1] would read the last skill, where the C reads before the array.
    if sn < 0:
        raise CWouldCrash("skills.c check_improve: sn -1 reads skill_table[-1] and learned[-1]")
    sk, learned = SKILL_TABLE[sn], ch.pcdata.learned
    if (ch.level < sk.skill_level[ch.class_] or sk.rating[ch.class_] == 0
            or learned[sn] == 0 or learned[sn] == 100):
        return  # "skill is not known"
    # "check to see if the character has a chance to learn"
    chance = 10 * INT_APP[get_curr_stat(ch, C.STAT_INT)].learn
    chance = c_div(chance, multiplier * sk.rating[ch.class_] * 4)
    chance += ch.level
    if number_range(1, 1000) > chance:
        return
    # "now that the character has a CHANCE to learn, see if they really have"
    if success:
        chance = max(5, min(100 - learned[sn], 95))  # URANGE(5, 100 - learned, 95)
        if number_percent() < chance:
            send_to_char("You have become better at %s!\n\r" % sk.name, ch)
            learned[sn] += 1
            gain_exp(ch, 2 * sk.rating[ch.class_])
    else:
        chance = max(5, min(c_div(learned[sn], 2), 30))
        if number_percent() < chance:
            send_to_char("You learn from your mistakes, and your %s skill improves.\n\r" % sk.name, ch)
            learned[sn] += number_range(1, 3)
            learned[sn] = min(learned[sn], 100)
            gain_exp(ch, 2 * sk.rating[ch.class_])


# C: skills.c do_gain
def do_gain(ch, argument: str) -> None:
    """Buying groups and skills from a trainer with trains, converting practices to trains, and trains to a
    creation point less."""
    from quickmud.commands.comm import do_say
    from quickmud.entities.handler import can_see
    from quickmud.net.act import act

    if ch.is_npc:
        return
    trainer = next((t for t in ch.in_room.people if t.is_npc and t.act & C.ACT_GAIN), None)  # "find a trainer"
    if trainer is None or not can_see(ch, trainer):
        send_to_char("You can't do that here.\n\r", ch)
        return

    _, arg = one_argument(argument)
    if arg == "":
        do_say(trainer, "Pardon me?")
        return

    if str_prefix(arg, "list"):
        send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s\n\r" % ("group", "cost", "group", "cost", "group", "cost"), ch)
        col = 0
        for gn, g in enumerate(GROUP_TABLE):
            if not ch.pcdata.group_known[gn] and g.rating[ch.class_] > 0:
                send_to_char("%-18s %-5d " % (g.name, g.rating[ch.class_]), ch)
                col += 1
                if col % 3 == 0:  # non-negative: a count
                    send_to_char("\n\r", ch)
        if col % 3 != 0:  # non-negative: a count
            send_to_char("\n\r", ch)
        send_to_char("\n\r", ch)
        send_to_char("%-18s %-5s %-18s %-5s %-18s %-5s\n\r" % ("skill", "cost", "skill", "cost", "skill", "cost"), ch)
        col = 0
        for sn, s in enumerate(SKILL_TABLE):
            if not ch.pcdata.learned[sn] and s.rating[ch.class_] > 0 and _spell_null(sn):
                send_to_char("%-18s %-5d " % (s.name, s.rating[ch.class_]), ch)
                col += 1
                if col % 3 == 0:  # non-negative: a count
                    send_to_char("\n\r", ch)
        if col % 3 != 0:  # non-negative: a count
            send_to_char("\n\r", ch)
        return

    if str_prefix(arg, "convert"):
        if ch.practice < 10:
            act("$N tells you 'You are not yet ready.'", ch, None, trainer, C.TO_CHAR)
            return
        act("$N helps you apply your practice to training", ch, None, trainer, C.TO_CHAR)
        ch.practice -= 10
        ch.train += 1
        return

    if str_prefix(arg, "points"):
        if ch.train < 2:
            act("$N tells you 'You are not yet ready.'", ch, None, trainer, C.TO_CHAR)
            return
        if ch.pcdata.points <= 40:
            act("$N tells you 'There would be no point in that.'", ch, None, trainer, C.TO_CHAR)
            return
        act("$N trains you, and you feel more at ease with your skills.", ch, None, trainer, C.TO_CHAR)
        ch.train -= 2
        ch.pcdata.points -= 1
        ch.exp = exp_per_level(ch, ch.pcdata.points) * ch.level
        return

    # "else add a group/skill": by the whole argument, not the first word
    gn = group_lookup(argument)
    if gn > 0:  # group 0, rom basics, every class has
        g = GROUP_TABLE[gn]
        if ch.pcdata.group_known[gn]:
            act("$N tells you 'You already know that group!'", ch, None, trainer, C.TO_CHAR)
            return
        if g.rating[ch.class_] <= 0:
            act("$N tells you 'That group is beyond your powers.'", ch, None, trainer, C.TO_CHAR)
            return
        if ch.train < g.rating[ch.class_]:
            act("$N tells you 'You are not yet ready for that group.'", ch, None, trainer, C.TO_CHAR)
            return
        gn_add(ch, gn)  # "add the group"
        act("$N trains you in the art of $t", ch, g.name, trainer, C.TO_CHAR)
        ch.train -= g.rating[ch.class_]
        return

    sn = skill_lookup(argument)
    if sn > -1:
        s = SKILL_TABLE[sn]
        if not _spell_null(sn):
            act("$N tells you 'You must learn the full group.'", ch, None, trainer, C.TO_CHAR)
            return
        if ch.pcdata.learned[sn]:
            act("$N tells you 'You already know that skill!'", ch, None, trainer, C.TO_CHAR)
            return
        if s.rating[ch.class_] <= 0:
            act("$N tells you 'That skill is beyond your powers.'", ch, None, trainer, C.TO_CHAR)
            return
        if ch.train < s.rating[ch.class_]:
            act("$N tells you 'You are not yet ready for that skill.'", ch, None, trainer, C.TO_CHAR)
            return
        ch.pcdata.learned[sn] = 1  # "add the skill"
        act("$N trains you in the art of $t", ch, s.name, trainer, C.TO_CHAR)
        ch.train -= s.rating[ch.class_]
        return

    act("$N tells you 'I do not understand...'", ch, None, trainer, C.TO_CHAR)


# C: skills.c do_spells
def do_spells(ch, argument: str) -> None:
    """"RT spells and skills show the players spells (or skills)": as do_skills, with each spell's mana."""
    if ch.is_npc:
        return
    fall, min_lev, max_lev = False, 1, C.LEVEL_HERO
    if argument != "":
        fall = True
        if not str_prefix(argument, "all"):
            argument, arg = one_argument(argument)
            if not is_number(arg):
                send_to_char("Arguments must be numerical or all.\n\r", ch)
                return
            max_lev = atoi(arg)
            if max_lev < 1 or max_lev > C.LEVEL_HERO:
                send_to_char("Levels must be between 1 and %d.\n\r" % C.LEVEL_HERO, ch)
                return
            if argument != "":
                argument, arg = one_argument(argument)
                if not is_number(arg):
                    send_to_char("Arguments must be numerical or all.\n\r", ch)
                    return
                min_lev, max_lev = max_lev, atoi(arg)
                if max_lev < 1 or max_lev > C.LEVEL_HERO:
                    send_to_char("Levels must be between 1 and %d.\n\r" % C.LEVEL_HERO, ch)
                    return
                if min_lev > max_lev:
                    send_to_char("That would be silly.\n\r", ch)
                    return
    lists = [""] * (C.LEVEL_HERO + 1)
    columns = [0] * (C.LEVEL_HERO + 1)
    found = False
    for sn, s in enumerate(SKILL_TABLE):
        level = s.skill_level[ch.class_]
        if (level < C.LEVEL_HERO + 1 and (fall or level <= ch.level) and min_lev <= level <= max_lev
                and not _spell_null(sn) and ch.pcdata.learned[sn] > 0):
            found = True
            if ch.level < level:
                buf = "%-18s n/a      " % s.name
            else:
                mana = max(s.min_mana, c_div(100, 2 + ch.level - level))
                buf = "%-18s  %3d mana  " % (s.name, mana)
            if lists[level] == "":
                lists[level] = "\n\rLevel %2d: %s" % (level, buf)
            else:
                columns[level] += 1
                if columns[level] % 2 == 0:  # non-negative: a count
                    lists[level] += "\n\r          "
                lists[level] += buf
    if not found:
        send_to_char("No spells found.\n\r", ch)
        return
    page_to_char("".join(x for x in lists if x) + "\n\r", ch)
