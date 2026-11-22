"""special.c: the mobs' special procedures, which mobile_update runs for each mob that has one (#74, P4 PR 5).

A mob's spec_fun holds the C function's name, as the area file gives it; SPECIALS finds the function by that name.
Each returns whether it did something, as the C's do. spec_lookup and spec_name are in quickmud.world.lookup.

spec_mayor's static variables (the path, the place on it, and whether he's walking) are the Game's mayor_path,
mayor_pos and mayor_move.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/special.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div
from quickmud.core.rng import number_bits, number_percent, number_range
from quickmud.data import constants as C
from quickmud.entities.handler import can_see, get_eq_char, is_awake
from quickmud.net.act import act
from quickmud.net.output import send_to_char
from quickmud.world.lookup import GSN, skill_lookup


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


def _affected(ch, bit: int) -> bool:
    return bool(ch.affected_by & bit)


def _multi_hit(ch, victim) -> None:
    from quickmud.systems.fight import multi_hit

    multi_hit(ch, victim, C.TYPE_UNDEFINED)


def _cast(sn: int, level: int, ch, victim) -> None:
    """(*skill_table[sn].spell_fun) (sn, level, ch, victim, TARGET_CHAR)."""
    from quickmud.systems.magic import cast_spell

    cast_spell(sn, level, ch, victim, C.TARGET_CHAR)


def _gang(ch, rival_group: int, messages: tuple) -> bool:
    """spec_troll_member and spec_ogre_member: find a rival to beat up (but not with the patrolman about), say
    something, and attack."""
    from quickmud.systems.fight import is_safe

    if (not is_awake(ch) or _affected(ch, C.AFF_CALM) or ch.in_room is None or _affected(ch, C.AFF_CHARM)
            or ch.fighting is not None):
        return False
    victim, count = None, 0
    for vch in list(ch.in_room.people):
        if not vch.is_npc or ch is vch:
            continue
        if vch.index.vnum == C.MOB_VNUM_PATROLMAN:
            return False
        if vch.index.group == rival_group and ch.level > vch.level - 2 and not is_safe(ch, vch):
            if number_range(0, count) == 0:
                victim = vch
            count += 1
    if victim is None:
        return False
    message = messages[number_range(0, 6)]
    if message is not None:
        act(message, ch, None, victim, C.TO_ALL)
    _multi_hit(ch, victim)
    return True


# C: special.c spec_troll_member
def spec_troll_member(ch) -> bool:
    return _gang(ch, C.GROUP_VNUM_OGRES, (
        "$n yells 'I've been looking for you, punk!'",
        "With a scream of rage, $n attacks $N.",
        "$n says 'What's slimy Ogre trash like you doing around here?'",
        "$n cracks his knuckles and says 'Do ya feel lucky?'",
        "$n says 'There's no cops to save you this time!'",
        "$n says 'Time to join your brother, spud.'",
        "$n says 'Let's rock.'",
    ))


# C: special.c spec_ogre_member
def spec_ogre_member(ch) -> bool:
    return _gang(ch, C.GROUP_VNUM_TROLLS, (
        "$n yells 'I've been looking for you, punk!'",
        "With a scream of rage, $n attacks $N.'",  # sic (#83): a stray quote
        "$n says 'What's Troll filth like you doing around here?'",
        "$n cracks his knuckles and says 'Do ya feel lucky?'",
        "$n says 'There's no cops to save you this time!'",
        "$n says 'Time to join your brother, spud.'",
        "$n says 'Let's rock.'",
    ))


# C: special.c spec_patrolman
def spec_patrolman(ch) -> bool:
    if (not is_awake(ch) or _affected(ch, C.AFF_CALM) or ch.in_room is None or _affected(ch, C.AFF_CHARM)
            or ch.fighting is not None):
        return False
    victim, count = None, 0
    for vch in list(ch.in_room.people):
        if vch is ch:
            continue
        if vch.fighting is not None:  # "break it up!"
            if number_range(0, count) == 0:
                victim = vch if vch.level > vch.fighting.level else vch.fighting
            count += 1
    if victim is None or (victim.is_npc and victim.spec_fun == ch.spec_fun):
        return False

    obj = get_eq_char(ch, C.WEAR_NECK_1)
    if obj is None or obj.index.vnum != C.OBJ_VNUM_WHISTLE:
        obj = get_eq_char(ch, C.WEAR_NECK_2)
        if obj is not None and obj.index.vnum != C.OBJ_VNUM_WHISTLE:
            obj = None
    if obj is not None:
        act("You blow down hard on $p.", ch, obj, None, C.TO_CHAR)
        act("$n blows on $p, ***WHEEEEEEEEEEEET***", ch, obj, None, C.TO_ROOM)
        for vch in list(_game().char_list):
            if vch.in_room is None:
                continue
            if vch.in_room is not ch.in_room and vch.in_room.area is ch.in_room.area:
                send_to_char("You hear a shrill whistling sound.\n\r", vch)

    message = (
        "$n yells 'All roit! All roit! break it up!'",
        "$n says 'Society's to blame, but what's a bloke to do?'",
        "$n mumbles 'bloody kids will be the death of us all.'",
        "$n shouts 'Stop that! Stop that!' and attacks.",
        "$n pulls out his billy and goes to work.",
        "$n sighs in resignation and proceeds to break up the fight.",
        "$n says 'Settle down, you hooligans!'",
    )[number_range(0, 6)]
    act(message, ch, None, None, C.TO_ALL)
    _multi_hit(ch, victim)
    return True


# C: special.c spec_nasty
def spec_nasty(ch) -> bool:
    from quickmud.systems.fight import do_backstab, do_flee, do_murder

    if not is_awake(ch):
        return False
    if ch.position != C.POS_FIGHTING:
        for victim in list(ch.in_room.people):
            if not victim.is_npc and ch.level < victim.level < ch.level + 10:
                do_backstab(ch, victim.name)
                if ch.position != C.POS_FIGHTING:
                    do_murder(ch, victim.name)
                return True  # "should steal some coins right away? :)"
        return False  # "No one to attack"

    # "okay, we must be fighting.... steal some coins and flee"
    victim = ch.fighting
    if victim is None:
        return False  # "let's be paranoid...."
    roll = number_bits(2)
    if roll == 0:
        act("$n rips apart your coin purse, spilling your gold!", ch, None, victim, C.TO_VICT)
        act("You slash apart $N's coin purse and gather his gold.", ch, None, victim, C.TO_CHAR)
        act("$N's coin purse is ripped apart!", ch, None, victim, C.TO_NOTVICT)
        gold = c_div(victim.gold, 10)  # "steal 10% of his gold"
        victim.gold -= gold
        ch.gold += gold
        return True
    if roll == 1:
        do_flee(ch, "")
        return True
    return False


# C: special.c dragon
def dragon(ch, spell_name: str) -> bool:
    """"Core procedure for dragons": breathe on someone fighting the mob, one in eight in turn."""
    if ch.position != C.POS_FIGHTING:
        return False
    for victim in list(ch.in_room.people):
        if victim.fighting is ch and number_bits(3) == 0:
            break
    else:
        return False
    sn = skill_lookup(spell_name)
    if sn < 0:
        return False
    _cast(sn, ch.level, ch, victim)
    return True


# C: special.c spec_breath_any
def spec_breath_any(ch) -> bool:
    if ch.position != C.POS_FIGHTING:
        return False
    roll = number_bits(3)
    if roll == 0:
        return spec_breath_fire(ch)
    if roll in (1, 2):
        return spec_breath_lightning(ch)
    if roll == 3:
        return spec_breath_gas(ch)
    if roll == 4:
        return spec_breath_acid(ch)
    return spec_breath_frost(ch)  # 5, 6 and 7


# C: special.c spec_breath_acid
def spec_breath_acid(ch) -> bool:
    return dragon(ch, "acid breath")


# C: special.c spec_breath_fire
def spec_breath_fire(ch) -> bool:
    return dragon(ch, "fire breath")


# C: special.c spec_breath_frost
def spec_breath_frost(ch) -> bool:
    return dragon(ch, "frost breath")


# C: special.c spec_breath_gas
def spec_breath_gas(ch) -> bool:
    if ch.position != C.POS_FIGHTING:
        return False
    sn = skill_lookup("gas breath")
    if sn < 0:
        return False
    _cast(sn, ch.level, ch, None)
    return True


# C: special.c spec_breath_lightning
def spec_breath_lightning(ch) -> bool:
    return dragon(ch, "lightning breath")


# C: special.c spec_cast_adept
def spec_cast_adept(ch) -> bool:
    from quickmud.systems import spells as S

    if not is_awake(ch):
        return False
    for victim in list(ch.in_room.people):
        if (victim is not ch and can_see(ch, victim) and number_bits(1) == 0 and not victim.is_npc
                and victim.level < 11):
            break
    else:
        return False

    roll = number_bits(4)
    if roll == 0:
        act("$n utters the word 'abrazak'.", ch, None, None, C.TO_ROOM)
        S.spell_armor(skill_lookup("armor"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 1:
        act("$n utters the word 'fido'.", ch, None, None, C.TO_ROOM)
        S.spell_bless(skill_lookup("bless"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 2:
        act("$n utters the words 'judicandus noselacri'.", ch, None, None, C.TO_ROOM)
        S.spell_cure_blindness(skill_lookup("cure blindness"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 3:
        act("$n utters the words 'judicandus dies'.", ch, None, None, C.TO_ROOM)
        S.spell_cure_light(skill_lookup("cure light"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 4:
        act("$n utters the words 'judicandus sausabru'.", ch, None, None, C.TO_ROOM)
        S.spell_cure_poison(skill_lookup("cure poison"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 5:
        act("$n utters the word 'candusima'.", ch, None, None, C.TO_ROOM)
        S.spell_refresh(skill_lookup("refresh"), ch.level, ch, victim, C.TARGET_CHAR)
        return True
    if roll == 6:
        act("$n utters the words 'judicandus eugzagz'.", ch, None, None, C.TO_ROOM)
        S.spell_cure_disease(skill_lookup("cure disease"), ch.level, ch, victim, C.TARGET_CHAR)
        # sic (#83): no return TRUE, so this one says it did nothing
    return False


def _caster(ch, spells: tuple) -> bool:
    """spec_cast_cleric, spec_cast_mage and spec_cast_undead: pick someone fighting the mob (one in four in turn),
    then roll for a spell until one is at or under the mob's level. spells holds (min_level, spell) for rolls 0 to
    15."""
    if ch.position != C.POS_FIGHTING:
        return False
    for victim in list(ch.in_room.people):
        if victim.fighting is ch and number_bits(2) == 0:
            break
    else:
        return False
    while True:
        min_level, spell = spells[number_bits(4)]
        if ch.level >= min_level:
            break
    sn = skill_lookup(spell)
    if sn < 0:
        return False
    _cast(sn, ch.level, ch, victim)
    return True


_CLERIC = ((0, "blindness"), (3, "cause serious"), (7, "earthquake"), (9, "cause critical"), (10, "dispel evil"),
           (12, "curse"), (12, "change sex"), (13, "flamestrike"), (15, "harm"), (15, "harm"), (15, "harm"),
           (15, "plague")) + ((16, "dispel magic"),) * 4

_MAGE = ((0, "blindness"), (3, "chill touch"), (7, "weaken"), (8, "teleport"), (11, "colour spray"),
         (12, "change sex"), (13, "energy drain"), (15, "fireball"), (15, "fireball"), (15, "fireball"),
         (20, "plague")) + ((20, "acid blast"),) * 5

_UNDEAD = ((0, "curse"), (3, "weaken"), (6, "chill touch"), (9, "blindness"), (12, "poison"), (15, "energy drain"),
           (18, "harm"), (21, "teleport"), (20, "plague")) + ((18, "harm"),) * 7


# C: special.c spec_cast_cleric
def spec_cast_cleric(ch) -> bool:
    return _caster(ch, _CLERIC)


# C: special.c spec_cast_judge
def spec_cast_judge(ch) -> bool:
    if ch.position != C.POS_FIGHTING:
        return False
    for victim in list(ch.in_room.people):
        if victim.fighting is ch and number_bits(2) == 0:
            break
    else:
        return False
    sn = skill_lookup("high explosive")
    if sn < 0:
        return False
    _cast(sn, ch.level, ch, victim)
    return True


# C: special.c spec_cast_mage
def spec_cast_mage(ch) -> bool:
    return _caster(ch, _MAGE)


# C: special.c spec_cast_undead
def spec_cast_undead(ch) -> bool:
    return _caster(ch, _UNDEAD)


def _criminal(ch):
    """spec_executioner's and spec_guard's search: the first player in the room, in order, who's a killer or a
    thief the mob can see, and the crime. It also gives spec_guard the most evil fighter it passed on the way."""
    max_evil, ech = 300, None
    for victim in list(ch.in_room.people):
        if not victim.is_npc and victim.act & C.PLR_KILLER and can_see(ch, victim):
            return victim, "KILLER", ech
        if not victim.is_npc and victim.act & C.PLR_THIEF and can_see(ch, victim):
            return victim, "THIEF", ech
        if victim.fighting is not None and victim.fighting is not ch and victim.alignment < max_evil:
            max_evil = victim.alignment
            ech = victim
    return None, "", ech


# C: special.c spec_executioner
def spec_executioner(ch) -> bool:
    from quickmud.commands.comm import do_yell

    if not is_awake(ch) or ch.fighting is not None:
        return False
    victim, crime, _ = _criminal(ch)
    if victim is None:
        return False
    buf = "%s is a %s!  PROTECT THE INNOCENT!  MORE BLOOOOD!!!" % (victim.name, crime)
    ch.comm &= ~C.COMM_NOSHOUT
    do_yell(ch, buf)
    _multi_hit(ch, victim)
    return True


# C: special.c spec_fido
def spec_fido(ch) -> bool:
    from quickmud.entities.handler import extract_obj, obj_from_obj, obj_to_room

    if not is_awake(ch):
        return False
    for corpse in list(ch.in_room.contents):
        if corpse.item_type != C.ITEM_CORPSE_NPC:
            continue
        act("$n savagely devours a corpse.", ch, None, None, C.TO_ROOM)
        for obj in list(corpse.contains):
            obj_from_obj(obj)
            obj_to_room(obj, ch.in_room)
        extract_obj(_game(), corpse)
        return True
    return False


# C: special.c spec_guard
def spec_guard(ch) -> bool:
    from quickmud.commands.comm import do_yell

    if not is_awake(ch) or ch.fighting is not None:
        return False
    victim, crime, ech = _criminal(ch)
    if victim is not None:
        buf = "%s is a %s!  PROTECT THE INNOCENT!!  BANZAI!!" % (victim.name, crime)
        ch.comm &= ~C.COMM_NOSHOUT
        do_yell(ch, buf)
        _multi_hit(ch, victim)
        return True
    if ech is not None:
        act("$n screams 'PROTECT THE INNOCENT!!  BANZAI!!", ch, None, None, C.TO_ROOM)  # sic (#83): no closing quote
        _multi_hit(ch, ech)
        return True
    return False


# C: special.c spec_janitor
def spec_janitor(ch) -> bool:
    from quickmud.commands.obj import can_loot
    from quickmud.entities.handler import obj_from_room, obj_to_char

    if not is_awake(ch):
        return False
    for trash in list(ch.in_room.contents):
        if not trash.wear_flags & C.ITEM_TAKE or not can_loot(ch, trash):
            continue
        if trash.item_type in (C.ITEM_DRINK_CON, C.ITEM_TRASH) or trash.cost < 10:
            act("$n picks up some trash.", ch, None, None, C.TO_ROOM)
            obj_from_room(trash)
            obj_to_char(trash, ch)
            return True
    return False


_OPEN_PATH = "W3a3003b33000c111d0d111Oe333333Oe22c222112212111a1S."
_CLOSE_PATH = "W3a3003b33000c111d0d111CE333333CE22c222112212111a1S."

_MAYOR_SAYS = {
    "a": "$n says 'Hello Honey!'",
    "b": "$n says 'What a view!  I must do something about that dump!'",
    "c": "$n says 'Vandals!  Youngsters have no respect for anything!'",
    "d": "$n says 'Good day, citizens!'",
    "e": "$n says 'I hereby declare the city of Midgaard open!'",
    "E": "$n says 'I hereby declare the city of Midgaard closed!'",
}


# C: special.c spec_mayor
def spec_mayor(ch) -> bool:
    """The mayor's walk: at 6 he opens the city gates, at 20 he closes them, a step of the path each call."""
    from quickmud.commands.move import do_close, do_open, move_char

    game = _game()
    if not game.mayor_move:
        if game.time_info.hour == 6:
            game.mayor_path, game.mayor_move, game.mayor_pos = _OPEN_PATH, True, 0
        if game.time_info.hour == 20:
            game.mayor_path, game.mayor_move, game.mayor_pos = _CLOSE_PATH, True, 0

    if ch.fighting is not None:
        return spec_cast_mage(ch)
    if not game.mayor_move or ch.position < C.POS_SLEEPING:
        return False

    step = game.mayor_path[game.mayor_pos]
    if step in "0123":
        move_char(ch, ord(step) - ord("0"), False)
    elif step == "W":
        ch.position = C.POS_STANDING
        act("$n awakens and groans loudly.", ch, None, None, C.TO_ROOM)
    elif step == "S":
        ch.position = C.POS_SLEEPING
        act("$n lies down and falls asleep.", ch, None, None, C.TO_ROOM)
    elif step in _MAYOR_SAYS:
        act(_MAYOR_SAYS[step], ch, None, None, C.TO_ROOM)
    elif step == "O":
        do_open(ch, "gate")
    elif step == "C":
        do_close(ch, "gate")
    elif step == ".":
        game.mayor_move = False
    game.mayor_pos += 1
    return False


# C: special.c spec_poison
def spec_poison(ch) -> bool:
    from quickmud.systems.spells import spell_poison

    victim = ch.fighting
    if ch.position != C.POS_FIGHTING or victim is None or number_percent() > 2 * ch.level:
        return False
    act("You bite $N!", ch, None, victim, C.TO_CHAR)
    act("$n bites $N!", ch, None, victim, C.TO_NOTVICT)
    act("$n bites you!", ch, None, victim, C.TO_VICT)
    spell_poison(GSN["gsn_poison"], ch.level, ch, victim, C.TARGET_CHAR)
    return True


def _share(level: int) -> int:
    """UMIN (number_range (1, 20), ch->level / 2): sic (#83), the macro rolls again when the roll is the smaller."""
    if number_range(1, 20) < c_div(level, 2):
        return number_range(1, 20)
    return c_div(level, 2)


# C: special.c spec_thief
def spec_thief(ch) -> bool:
    if ch.position != C.POS_STANDING:
        return False
    for victim in list(ch.in_room.people):
        if (victim.is_npc or victim.level >= C.LEVEL_IMMORTAL or number_bits(5) != 0
                or not can_see(ch, victim)):
            continue
        if is_awake(victim) and number_range(0, ch.level) == 0:
            act("You discover $n's hands in your wallet!", ch, None, victim, C.TO_VICT)
            act("$N discovers $n's hands in $S wallet!", ch, None, victim, C.TO_NOTVICT)
            return True
        gold = c_div(victim.gold * _share(ch.level), 100)
        gold = min(gold, ch.level * ch.level * 10)
        ch.gold += gold
        victim.gold -= gold
        silver = c_div(victim.silver * _share(ch.level), 100)
        silver = min(silver, ch.level * ch.level * 25)
        ch.silver += silver
        victim.silver -= silver
        return True
    return False


SPECIALS = {name: fn for name, fn in globals().items() if name.startswith("spec_") and callable(fn)}
