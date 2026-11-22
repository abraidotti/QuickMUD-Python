"""update.c: the game's clockwork. update_handler runs once a pulse (a quarter of a second) and calls each update
on its own pulse: area_update, song_update (music.c), mobile_update, violence_update (fight.c), and on each tick
weather_update, char_update and obj_update; aggr_update every pulse. Also the gains a tick brings (hit_gain,
mana_gain, move_gain), gain_condition, advance_level and gain_exp.

QUICKMUD_UPDATES names the updates that run, in both games (#74): area, song, mobile, violence, weather, char, obj and
aggr, comma-separated, or all. Unset, everything runs.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/update.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div, sh_int
from quickmud.core.rng import dice, number_bits, number_percent, number_range
from quickmud.data import constants as C
from quickmud.entities.resets import area_update
from quickmud.net.act import act
from quickmud.net.output import send_to_char
from quickmud.net.wiznet import wiznet

NOT_RUNNING: tuple = ()  # every update is ported (#28's list is empty now)

UPDATES = ("area", "song", "mobile", "violence", "weather", "char", "obj", "aggr")  # QUICKMUD_UPDATES's names
PORTED = frozenset(UPDATES)


# C: update.c update_runs
def updates_named(value: str | None) -> frozenset[str]:
    """The updates QUICKMUD_UPDATES names, as update.c's update_runs reads it: None (unset) is all of them."""
    from quickmud.core.log import bug
    from quickmud.core.strings import str_cmp

    if value is None:
        return frozenset(UPDATES)
    on: set[str] = set()
    for name in value[:C.MAX_INPUT_LENGTH - 1].split(","):
        if name == "":
            continue  # strtok skips empty fields
        if str_cmp(name, "all"):
            on.update(UPDATES)
            continue
        found = next((u for u in UPDATES if str_cmp(name, u)), None)
        if found is None:
            bug("QUICKMUD_UPDATES: no update called that", 0)
        else:
            on.add(found)
    return frozenset(on)


# C: update.c hit_gain
def hit_gain(ch) -> int:
    from quickmud.data.classes import CLASS_TABLE
    from quickmud.entities.handler import get_curr_stat, get_skill, is_affected
    from quickmud.systems.skills import check_improve
    from quickmud.world.lookup import GSN

    if ch.in_room is None:
        return 0
    if ch.is_npc:
        gain = 5 + ch.level
        if is_affected(ch, C.AFF_REGENERATION):
            gain *= 2
        gain = _npc_position_gain(ch, gain)
    else:
        gain = max(3, get_curr_stat(ch, C.STAT_CON) - 3 + c_div(ch.level, 2))
        gain += CLASS_TABLE[ch.class_].hp_max - 10
        number = number_percent()
        if number < get_skill(ch, GSN["gsn_fast_healing"]):
            gain += c_div(number * gain, 100)
            if ch.hit < ch.max_hit:
                check_improve(ch, GSN["gsn_fast_healing"], True, 8)
        gain = _pc_position_gain(ch, gain)
        gain = _hungry_thirsty(ch, gain)
    gain = c_div(gain * ch.in_room.heal_rate, 100)
    if ch.on is not None and ch.on.item_type == C.ITEM_FURNITURE:
        gain = c_div(gain * ch.on.value[3], 100)
    gain = _afflicted(ch, gain)
    return min(gain, ch.max_hit - ch.hit)


def _npc_position_gain(ch, gain: int) -> int:
    if ch.position == C.POS_SLEEPING:
        return c_div(3 * gain, 2)
    if ch.position == C.POS_RESTING:
        return gain
    if ch.position == C.POS_FIGHTING:
        return c_div(gain, 3)
    return c_div(gain, 2)


def _pc_position_gain(ch, gain: int) -> int:
    if ch.position == C.POS_SLEEPING:
        return gain
    if ch.position == C.POS_RESTING:
        return c_div(gain, 2)
    if ch.position == C.POS_FIGHTING:
        return c_div(gain, 6)
    return c_div(gain, 4)


def _hungry_thirsty(ch, gain: int) -> int:
    if ch.pcdata.condition[C.COND_HUNGER] == 0:
        gain = c_div(gain, 2)
    if ch.pcdata.condition[C.COND_THIRST] == 0:
        gain = c_div(gain, 2)
    return gain


def _afflicted(ch, gain: int) -> int:
    from quickmud.entities.handler import is_affected

    if is_affected(ch, C.AFF_POISON):
        gain = c_div(gain, 4)
    if is_affected(ch, C.AFF_PLAGUE):
        gain = c_div(gain, 8)
    if is_affected(ch, C.AFF_HASTE) or is_affected(ch, C.AFF_SLOW):
        gain = c_div(gain, 2)
    return gain


# C: update.c mana_gain
def mana_gain(ch) -> int:
    from quickmud.data.classes import CLASS_TABLE
    from quickmud.entities.handler import get_curr_stat, get_skill
    from quickmud.systems.skills import check_improve
    from quickmud.world.lookup import GSN

    if ch.in_room is None:
        return 0
    if ch.is_npc:
        gain = _npc_position_gain(ch, 5 + ch.level)
    else:
        gain = c_div(get_curr_stat(ch, C.STAT_WIS) + get_curr_stat(ch, C.STAT_INT) + ch.level, 2)
        number = number_percent()
        if number < get_skill(ch, GSN["gsn_meditation"]):
            gain += c_div(number * gain, 100)
            if ch.mana < ch.max_mana:
                check_improve(ch, GSN["gsn_meditation"], True, 8)
        if not CLASS_TABLE[ch.class_].fMana:
            gain = c_div(gain, 2)
        gain = _pc_position_gain(ch, gain)
        gain = _hungry_thirsty(ch, gain)
    gain = c_div(gain * ch.in_room.mana_rate, 100)
    if ch.on is not None and ch.on.item_type == C.ITEM_FURNITURE:
        gain = c_div(gain * ch.on.value[4], 100)
    gain = _afflicted(ch, gain)
    return min(gain, ch.max_mana - ch.mana)


# C: update.c move_gain
def move_gain(ch) -> int:
    from quickmud.entities.handler import get_curr_stat

    if ch.in_room is None:
        return 0
    if ch.is_npc:
        gain = ch.level
    else:
        gain = max(15, ch.level)
        if ch.position == C.POS_SLEEPING:
            gain += get_curr_stat(ch, C.STAT_DEX)
        elif ch.position == C.POS_RESTING:
            gain += c_div(get_curr_stat(ch, C.STAT_DEX), 2)
        gain = _hungry_thirsty(ch, gain)
    gain = c_div(gain * ch.in_room.heal_rate, 100)
    if ch.on is not None and ch.on.item_type == C.ITEM_FURNITURE:
        gain = c_div(gain * ch.on.value[3], 100)
    gain = _afflicted(ch, gain)
    return min(gain, ch.max_move - ch.move)


# C: update.c mobile_update
def mobile_update(game) -> None:
    from quickmud.commands.move import move_char
    from quickmud.commands.obj import can_loot
    from quickmud.core.errors import NotPorted
    from quickmud.entities.handler import is_affected, obj_from_room, obj_to_char
    from quickmud.systems.fight import _char_list_from
    from quickmud.systems.mobprog import has_trigger, mp_percent_trigger
    from quickmud.systems.specials import SPECIALS

    for ch in _char_list_from(game.char_list, 0):  # "Examine all mobs."
        if not ch.is_npc or ch.in_room is None or is_affected(ch, C.AFF_CHARM):
            continue
        if ch.in_room.area.empty and not ch.act & C.ACT_UPDATE_ALWAYS:
            continue

        if ch.spec_fun is not None:  # "Examine call for special procedure"
            fn = SPECIALS.get(ch.spec_fun)
            if fn is None:
                raise NotPorted(f"special.c {ch.spec_fun}")
            if fn(ch):
                continue

        if ch.index.shop is not None:  # "give him some gold"
            if ch.gold * 100 + ch.silver < ch.index.wealth:
                ch.gold += c_div(ch.index.wealth * number_range(1, 20), 5000000)
                ch.silver += c_div(ch.index.wealth * number_range(1, 20), 50000)

        # "Check triggers only if mobile still in default position"
        if ch.position == ch.index.default_pos:
            if has_trigger(ch, C.TRIG_DELAY) and ch.mprog_delay > 0:  # "Delay"
                ch.mprog_delay -= 1
                if ch.mprog_delay <= 0:
                    mp_percent_trigger(ch, None, None, None, C.TRIG_DELAY)
                    continue
            if has_trigger(ch, C.TRIG_RANDOM):
                if mp_percent_trigger(ch, None, None, None, C.TRIG_RANDOM):
                    continue

        # "That's all for sleeping / busy monster, and empty zones"
        if ch.position != C.POS_STANDING:
            continue

        # "Scavenge"
        if ch.act & C.ACT_SCAVENGER and ch.in_room.contents and number_bits(6) == 0:
            best, top = None, 1
            for obj in ch.in_room.contents:
                if obj.wear_flags & C.ITEM_TAKE and can_loot(ch, obj) and obj.cost > top and obj.cost > 0:
                    best, top = obj, obj.cost
            if best is not None:
                obj_from_room(best)
                obj_to_char(best, ch)
                act("$n gets $p.", ch, best, None, C.TO_ROOM)

        # "Wander"
        if ch.act & C.ACT_SENTINEL or number_bits(3) != 0:
            continue
        door = number_bits(5)
        if door > 5:
            continue
        pexit = ch.in_room.exit[door]
        if pexit is None or pexit.to_room is None:
            continue
        to = pexit.to_room
        if (not pexit.exit_info & C.EX_CLOSED and not to.room_flags & C.ROOM_NO_MOB
                and (not ch.act & C.ACT_STAY_AREA or to.area is ch.in_room.area)
                and (not ch.act & C.ACT_OUTDOORS or not to.room_flags & C.ROOM_INDOORS)
                and (not ch.act & C.ACT_INDOORS or to.room_flags & C.ROOM_INDOORS)):
            move_char(ch, door, False)


# C: update.c weather_update
def weather_update(game) -> None:
    from quickmud.entities.handler import is_awake

    t, w = game.time_info, game.weather_info
    buf = ""
    t.hour += 1
    if t.hour == 5:
        w.sunlight = C.SUN_LIGHT  # sic (#85): 5 is light and 6 sunrise, the other way from boot_db's
        buf += "The day has begun.\n\r"
    elif t.hour == 6:
        w.sunlight = C.SUN_RISE
        buf += "The sun rises in the east.\n\r"
    elif t.hour == 19:
        w.sunlight = C.SUN_SET
        buf += "The sun slowly disappears in the west.\n\r"
    elif t.hour == 20:
        w.sunlight = C.SUN_DARK
        buf += "The night has begun.\n\r"
    elif t.hour == 24:
        t.hour = 0
        t.day += 1
    if t.day >= 35:
        t.day = 0
        t.month += 1
    if t.month >= 17:
        t.month = 0
        t.year += 1

    # "Weather change."
    if 9 <= t.month <= 16:
        diff = -2 if w.mmhg > 985 else 2
    else:
        diff = -2 if w.mmhg > 1015 else 2
    w.change += diff * dice(1, 4) + dice(2, 6) - dice(2, 6)
    w.change = min(max(w.change, -12), 12)
    w.mmhg += w.change
    w.mmhg = min(max(w.mmhg, 960), 1040)

    if w.sky == C.SKY_CLOUDLESS:
        if w.mmhg < 990 or (w.mmhg < 1010 and number_bits(2) == 0):
            buf += "The sky is getting cloudy.\n\r"
            w.sky = C.SKY_CLOUDY
    elif w.sky == C.SKY_CLOUDY:
        if w.mmhg < 970 or (w.mmhg < 990 and number_bits(2) == 0):
            buf += "It starts to rain.\n\r"
            w.sky = C.SKY_RAINING
        if w.mmhg > 1030 and number_bits(2) == 0:
            buf += "The clouds disappear.\n\r"
            w.sky = C.SKY_CLOUDLESS
    elif w.sky == C.SKY_RAINING:
        if w.mmhg < 970 and number_bits(2) == 0:
            buf += "Lightning flashes in the sky.\n\r"
            w.sky = C.SKY_LIGHTNING
        if w.mmhg > 1030 or (w.mmhg > 1010 and number_bits(2) == 0):
            buf += "The rain stopped.\n\r"
            w.sky = C.SKY_CLOUDY
    elif w.sky == C.SKY_LIGHTNING:
        if w.mmhg > 1010 or (w.mmhg > 990 and number_bits(2) == 0):
            buf += "The lightning has stopped.\n\r"
            w.sky = C.SKY_RAINING
    else:
        from quickmud.core.log import bug

        bug("Weather_update: bad sky %d.", w.sky)
        w.sky = C.SKY_CLOUDLESS

    if buf != "":
        for d in list(game.descriptor_list):
            ch = d.character
            if (d.connected == C.CON_PLAYING and not ch.in_room.room_flags & C.ROOM_INDOORS
                    and is_awake(ch)):
                send_to_char(buf, ch)


def _msg(text: str | None) -> bool:
    """A skill_table message the C tests by pointer: NULL is none."""
    return text is not None


def _skill(sn: int):
    from quickmud.data.skills import SKILL_TABLE

    return SKILL_TABLE[sn] if sn < len(SKILL_TABLE) else None


# C: update.c char_update
def char_update(game) -> None:
    from quickmud.commands.comm import do_quit
    from quickmud.core.log import bug
    from quickmud.entities.handler import (affect_find, affect_join, affect_remove, char_from_room, char_to_room,
                                        extract_obj, get_eq_char, is_affected, is_affected_by, is_immortal)
    from quickmud.persist.player import save_char_obj
    from quickmud.systems.fight import _char_list_from, damage, stop_fighting, update_pos
    from quickmud.systems.magic import saves_spell
    from quickmud.world.index import Affect
    from quickmud.world.lookup import GSN

    ch_quit = None
    game.save_number += 1  # "update save counter"
    if game.save_number > 29:
        game.save_number = 0

    for ch in _char_list_from(game.char_list, 0):
        if ch.timer > 30:
            ch_quit = ch

        if ch.position >= C.POS_STUNNED:
            # "check to see if we need to go home": only a mob with a zone, and nothing in the C sets one (#85)
            if ch.hit < ch.max_hit:
                ch.hit = sh_int(ch.hit + hit_gain(ch))
            else:
                ch.hit = ch.max_hit
            if ch.mana < ch.max_mana:
                ch.mana = sh_int(ch.mana + mana_gain(ch))
            else:
                ch.mana = ch.max_mana
            if ch.move < ch.max_move:
                ch.move = sh_int(ch.move + move_gain(ch))
            else:
                ch.move = ch.max_move

        if ch.position == C.POS_STUNNED:
            update_pos(ch)

        if not ch.is_npc and ch.level < C.LEVEL_IMMORTAL:
            obj = get_eq_char(ch, C.WEAR_LIGHT)
            if obj is not None and obj.item_type == C.ITEM_LIGHT and obj.value[2] > 0:
                obj.value[2] -= 1
                if obj.value[2] == 0 and ch.in_room is not None:
                    ch.in_room.light -= 1
                    act("$p goes out.", ch, obj, None, C.TO_ROOM)
                    act("$p flickers and goes out.", ch, obj, None, C.TO_CHAR)
                    extract_obj(game, obj)
                elif obj.value[2] <= 5 and ch.in_room is not None:
                    act("$p flickers.", ch, obj, None, C.TO_CHAR)

            if is_immortal(ch):
                ch.timer = 0
            ch.timer += 1
            if ch.timer >= 12:
                if ch.was_in_room is None and ch.in_room is not None:
                    ch.was_in_room = ch.in_room
                    if ch.fighting is not None:
                        stop_fighting(game, ch, True)
                    act("$n disappears into the void.", ch, None, None, C.TO_ROOM)
                    send_to_char("You disappear into the void.\n\r", ch)
                    if ch.level > 1:
                        save_char_obj(game, ch)
                    char_from_room(ch)
                    char_to_room(ch, game.index.get_room_index(C.ROOM_VNUM_LIMBO))

            gain_condition(ch, C.COND_DRUNK, -1)
            gain_condition(ch, C.COND_FULL, -4 if ch.size > C.SIZE_MEDIUM else -2)
            gain_condition(ch, C.COND_THIRST, -1)
            gain_condition(ch, C.COND_HUNGER, -2 if ch.size > C.SIZE_MEDIUM else -1)

        affects = list(ch.affected)
        for k, paf in enumerate(affects):
            paf_next = affects[k + 1] if k + 1 < len(affects) else None
            if paf.duration > 0:
                paf.duration -= 1
                if number_range(0, 4) == 0 and paf.level > 0:
                    paf.level -= 1  # "spell strength fades with time"
            elif paf.duration < 0:
                pass
            else:
                if paf_next is None or paf_next.type != paf.type or paf_next.duration > 0:
                    sk = _skill(paf.type)
                    if paf.type > 0 and sk is not None and _msg(sk.msg_off):
                        send_to_char(sk.msg_off, ch)
                        send_to_char("\n\r", ch)
                affect_remove(ch, paf)

        # "Careful with the damages here, MUST NOT refer to ch after damage taken, as it may be lethal damage (on
        # NPC)."
        if is_affected_by(ch, GSN["gsn_plague"]):
            if ch.in_room is None:
                continue
            act("$n writhes in agony as plague sores erupt from $s skin.", ch, None, None, C.TO_ROOM)
            send_to_char("You writhe in agony from the plague.\n\r", ch)
            af = affect_find(ch.affected, GSN["gsn_plague"])
            if af is None:
                ch.affected_by &= ~C.AFF_PLAGUE
                continue
            if af.level == 1:
                continue
            level = af.level - 1
            plague = Affect(where=C.TO_AFFECTS, type=GSN["gsn_plague"], level=level,
                            duration=number_range(1, 2 * level), location=C.APPLY_STR, modifier=-5,
                            bitvector=C.AFF_PLAGUE)
            for vch in list(ch.in_room.people):
                if (not saves_spell(plague.level - 2, vch, C.DAM_DISEASE) and not is_immortal(vch)
                        and not is_affected(vch, C.AFF_PLAGUE) and number_bits(4) == 0):
                    send_to_char("You feel hot and feverish.\n\r", vch)
                    act("$n shivers and looks very ill.", vch, None, None, C.TO_ROOM)
                    affect_join(vch, plague)  # one struct for all: affect_join can change it, as in the C
            dam = min(ch.level, c_div(af.level, 5) + 1)
            ch.mana = sh_int(ch.mana - dam)
            ch.move = sh_int(ch.move - dam)
            damage(ch, ch, dam, GSN["gsn_plague"], C.DAM_DISEASE, False)
        elif is_affected(ch, C.AFF_POISON) and not is_affected(ch, C.AFF_SLOW):
            poison = affect_find(ch.affected, GSN["gsn_poison"])
            if poison is not None:
                act("$n shivers and suffers.", ch, None, None, C.TO_ROOM)
                send_to_char("You shiver and suffer.\n\r", ch)
                damage(ch, ch, c_div(poison.level, 10) + 1, GSN["gsn_poison"], C.DAM_POISON, False)
        elif ch.position == C.POS_INCAP and number_range(0, 1) == 0:
            damage(ch, ch, 1, C.TYPE_UNDEFINED, C.DAM_NONE, False)
        elif ch.position == C.POS_MORTAL:
            damage(ch, ch, 1, C.TYPE_UNDEFINED, C.DAM_NONE, False)

    # "Autosave and autoquit. Check that these chars still exist."
    ch = game.char_list[0] if game.char_list else None
    while ch is not None:
        if not ch.valid:  # "Edwin's fix for possible pet-induced problem"
            bug("update_char: Trying to work with an invalidated character.\n", 0)
            break
        i = next((k for k, c in enumerate(game.char_list) if c is ch), None)
        ch_next = game.char_list[i + 1] if i is not None and i + 1 < len(game.char_list) else None
        if ch.desc is not None and ch.desc.fileno % 30 == game.save_number:  # non-negative: a descriptor
            save_char_obj(game, ch)
        if ch is ch_quit:
            do_quit(ch, "")
        ch = ch_next


def _obj_list_from(objs: list):
    """The objects of object_list, by obj->next, read before each one's turn, as _char_list_from walks characters.
    An object freed during the turn before it (a corpse's contents, extracted with it) leaves the C on
    recycle.c's free list, where every object has no place and no affects, so obj_update does nothing more and
    ends: the objects after it wait for the next tick (sic, #85)."""
    snap = list(objs)
    i = 0
    while i < len(snap):
        j = i + 1
        while j < len(snap) and not snap[j].valid:
            j += 1
        yield snap[i]
        if j < len(snap) and not snap[j].valid:
            return
        i = j


# C: update.c obj_update
def obj_update(game) -> None:
    from quickmud.entities.handler import extract_obj, obj_from_obj, obj_to_char, obj_to_obj, obj_to_room

    for obj in _obj_list_from(game.object_list):
        # "go through affects and decrement"
        affects = list(obj.affected)
        for k, paf in enumerate(affects):
            paf_next = affects[k + 1] if k + 1 < len(affects) else None
            if paf.duration > 0:
                paf.duration -= 1
                if number_range(0, 4) == 0 and paf.level > 0:
                    paf.level -= 1  # "spell strength fades with time"
            elif paf.duration < 0:
                pass
            else:
                if paf_next is None or paf_next.type != paf.type or paf_next.duration > 0:
                    sk = _skill(paf.type)
                    if paf.type > 0 and sk is not None and _msg(sk.msg_obj):
                        if obj.carried_by is not None:
                            act(sk.msg_obj, obj.carried_by, obj, None, C.TO_CHAR)
                        if obj.in_room is not None and obj.in_room.people:
                            act(sk.msg_obj, obj.in_room.people[0], obj, None, C.TO_ALL)
                from quickmud.entities.handler import affect_remove_obj

                affect_remove_obj(obj, paf)

        if obj.timer <= 0:
            continue
        obj.timer -= 1
        if obj.timer > 0:
            continue

        t = obj.item_type
        if t == C.ITEM_FOUNTAIN:
            message = "$p dries up."
        elif t in (C.ITEM_CORPSE_NPC, C.ITEM_CORPSE_PC):
            message = "$p decays into dust."
        elif t == C.ITEM_FOOD:
            message = "$p decomposes."
        elif t == C.ITEM_POTION:
            message = "$p has evaporated from disuse."
        elif t == C.ITEM_PORTAL:
            message = "$p fades out of existence."
        elif t == C.ITEM_CONTAINER and obj.wear_flags & C.ITEM_WEAR_FLOAT:
            if obj.contains:
                message = "$p flickers and vanishes, spilling its contents on the floor."
            else:
                message = "$p flickers and vanishes."
        else:
            message = "$p crumbles into dust."

        if obj.carried_by is not None:
            if obj.carried_by.is_npc and obj.carried_by.index.shop is not None:
                obj.carried_by.silver += c_div(obj.cost, 5)
            else:
                act(message, obj.carried_by, obj, None, C.TO_CHAR)
                if obj.wear_loc == C.WEAR_FLOAT:
                    act(message, obj.carried_by, obj, None, C.TO_ROOM)
        elif obj.in_room is not None and obj.in_room.people:
            rch = obj.in_room.people[0]
            # sic (#85): an object in the pit has no room, so this test never applies
            if not (obj.in_obj is not None and obj.in_obj.index.vnum == C.OBJ_VNUM_PIT
                    and not obj.in_obj.wear_flags & C.ITEM_TAKE):
                act(message, rch, obj, None, C.TO_ROOM)
                act(message, rch, obj, None, C.TO_CHAR)

        if (obj.item_type == C.ITEM_CORPSE_PC or obj.wear_loc == C.WEAR_FLOAT) and obj.contains:
            for t_obj in list(obj.contains):  # "save the contents"
                obj_from_obj(t_obj)
                if obj.in_obj is not None:  # "in another object"
                    obj_to_obj(t_obj, obj.in_obj)
                elif obj.carried_by is not None:  # "carried"
                    if obj.wear_loc == C.WEAR_FLOAT:
                        if obj.carried_by.in_room is None:
                            extract_obj(game, t_obj)
                        else:
                            obj_to_room(t_obj, obj.carried_by.in_room)
                    else:
                        obj_to_char(t_obj, obj.carried_by)
                elif obj.in_room is None:  # "destroy it"
                    extract_obj(game, t_obj)
                else:  # "to a room"
                    obj_to_room(t_obj, obj.in_room)
        extract_obj(game, obj)


# C: update.c aggr_update
def aggr_update(game) -> None:
    """For each mortal player, each aggressive mob in the room attacks some player there, picked at random."""
    from quickmud.entities.handler import can_see, is_affected, is_awake
    from quickmud.systems.fight import _char_list_from, multi_hit

    for wch in _char_list_from(game.char_list, 0):
        if wch.is_npc or wch.level >= C.LEVEL_IMMORTAL or wch.in_room is None or wch.in_room.area.empty:
            continue
        for ch in _people_from(wch.in_room.people):
            if (not ch.is_npc or not ch.act & C.ACT_AGGRESSIVE or ch.in_room.room_flags & C.ROOM_SAFE
                    or is_affected(ch, C.AFF_CALM) or ch.fighting is not None or is_affected(ch, C.AFF_CHARM)
                    or not is_awake(ch) or (ch.act & C.ACT_WIMPY and is_awake(wch)) or not can_see(ch, wch)
                    or number_bits(1) == 0):
                continue
            # "Now make the aggressor fight a RANDOM pc victim in the room, giving each 'vch' an equal chance of
            # selection."
            count, victim = 0, None
            for vch in list(wch.in_room.people):
                if (not vch.is_npc and vch.level < C.LEVEL_IMMORTAL and ch.level >= vch.level - 5
                        and (not ch.act & C.ACT_WIMPY or not is_awake(vch)) and can_see(ch, vch)):
                    if number_range(0, count) == 0:
                        victim = vch
                    count += 1
            if victim is None:
                continue
            multi_hit(ch, victim, C.TYPE_UNDEFINED)


def _people_from(people: list):
    """A room's people by next_in_room, each next read at the start of its turn, as the C reads ch_next. One that
    leaves the room before its turn is skipped (unlinked); one moved during the turn before it carries on through
    its new room's people from where char_to_room put it (the head), and one taken out of every room ends it."""
    ch = people[0] if people else None
    while ch is not None:
        room = ch.in_room
        nxt = None
        if room is not None:
            k = next((n for n, p in enumerate(room.people) if p is ch), None)
            if k is not None and k + 1 < len(room.people):
                nxt = room.people[k + 1]
        yield ch
        ch = nxt


# C: update.c update_handler
def update_handler(game) -> None:
    from quickmud.systems.fight import violence_update
    from quickmud.systems.music import song_update

    on = game.updates
    game.pulse_area -= 1
    if game.pulse_area <= 0:
        game.pulse_area = C.PULSE_AREA
        if "area" in on:
            area_update(game)

    game.pulse_music -= 1
    if game.pulse_music <= 0:
        game.pulse_music = C.PULSE_MUSIC
        if "song" in on:
            song_update(game)

    game.pulse_mobile -= 1
    if game.pulse_mobile <= 0:
        game.pulse_mobile = C.PULSE_MOBILE
        if "mobile" in on:
            mobile_update(game)

    game.pulse_violence -= 1
    if game.pulse_violence <= 0:
        game.pulse_violence = C.PULSE_VIOLENCE
        if "violence" in on:
            violence_update(game)

    game.pulse_point -= 1
    if game.pulse_point <= 0:
        wiznet(game, "TICK!", None, None, C.WIZ_TICKS, 0, 0)
        game.pulse_point = C.PULSE_TICK
        if "weather" in on:
            weather_update(game)
        if "char" in on:
            char_update(game)
        if "obj" in on:
            obj_update(game)

    if "aggr" in on:
        aggr_update(game)


# C: update.c gain_condition
def gain_condition(ch, i_cond: int, value: int) -> None:
    from quickmud.net.output import send_to_char

    if value == 0 or ch.is_npc or ch.level >= C.LEVEL_IMMORTAL:
        return
    condition = ch.pcdata.condition[i_cond]
    if condition == -1:
        return
    ch.pcdata.condition[i_cond] = max(0, min(condition + value, 48))  # URANGE(0, condition + value, 48)
    if ch.pcdata.condition[i_cond] == 0:
        if i_cond == C.COND_HUNGER:
            send_to_char("You are hungry.\n\r", ch)
        elif i_cond == C.COND_THIRST:
            send_to_char("You are thirsty.\n\r", ch)
        elif i_cond == C.COND_DRUNK and condition != 0:
            send_to_char("You are sober.\n\r", ch)


# C: update.c advance_level
def advance_level(ch, hide: bool) -> None:
    """A level's gains: the title, then hit points, mana, moves (three random draws, in that order) and practices.
    do_advance calls it with hide set; gain_exp without, to tell the player."""
    from quickmud.commands.info import set_title
    from quickmud.core.cint import c_div, sh_int
    from quickmud.core.rng import number_range
    from quickmud.data.attributes import CON_APP, WIS_APP
    from quickmud.data.classes import CLASS_TABLE, TITLE_TABLE
    from quickmud.entities import game as game_module
    from quickmud.entities.handler import get_curr_stat
    from quickmud.net.output import send_to_char

    ch.pcdata.last_level = c_div(ch.played + int(game_module.current.current_time - ch.logon), 3600)
    set_title(ch, "the %s" % TITLE_TABLE[ch.class_][ch.level][1 if ch.sex == C.SEX_FEMALE else 0])
    cls = CLASS_TABLE[ch.class_]
    add_hp = CON_APP[get_curr_stat(ch, C.STAT_CON)].hitp + number_range(cls.hp_min, cls.hp_max)
    add_mana = number_range(2, c_div(2 * get_curr_stat(ch, C.STAT_INT) + get_curr_stat(ch, C.STAT_WIS), 5))
    if not cls.fMana:
        add_mana = c_div(add_mana, 2)
    add_move = number_range(1, c_div(get_curr_stat(ch, C.STAT_CON) + get_curr_stat(ch, C.STAT_DEX), 6))
    add_prac = WIS_APP[get_curr_stat(ch, C.STAT_WIS)].practice
    add_hp = max(2, c_div(add_hp * 9, 10))
    add_mana = max(2, c_div(add_mana * 9, 10))
    add_move = max(6, c_div(add_move * 9, 10))
    ch.max_hit = sh_int(ch.max_hit + add_hp)
    ch.max_mana = sh_int(ch.max_mana + add_mana)
    ch.max_move = sh_int(ch.max_move + add_move)
    ch.practice = sh_int(ch.practice + add_prac)
    ch.train = sh_int(ch.train + 1)
    ch.pcdata.perm_hit = sh_int(ch.pcdata.perm_hit + add_hp)
    ch.pcdata.perm_mana = sh_int(ch.pcdata.perm_mana + add_mana)
    ch.pcdata.perm_move = sh_int(ch.pcdata.perm_move + add_move)
    if not hide:
        send_to_char("You gain %d hit point%s, %d mana, %d move, and %d practice%s.\n\r"
                     % (add_hp, "" if add_hp == 1 else "s", add_mana, add_move, add_prac,
                        "" if add_prac == 1 else "s"), ch)


# C: update.c gain_exp
def gain_exp(ch, gain: int) -> None:
    from quickmud.core.cint import sh_int
    from quickmud.core.log import log_string
    from quickmud.entities import game as game_module
    from quickmud.net.output import send_to_char
    from quickmud.persist.player import save_char_obj
    from quickmud.systems.skills import exp_per_level

    if ch.is_npc or ch.level >= C.LEVEL_HERO:
        return
    ch.exp = max(exp_per_level(ch, ch.pcdata.points), ch.exp + gain)
    while ch.level < C.LEVEL_HERO and ch.exp >= exp_per_level(ch, ch.pcdata.points) * (ch.level + 1):
        send_to_char("{GYou raise a level!!  {x", ch)
        ch.level = sh_int(ch.level + 1)
        log_string("%s gained level %d" % (ch.name, ch.level))
        wiznet(game_module.current, "$N has attained level %d!" % ch.level, ch, None, C.WIZ_LEVELS, 0, 0)
        advance_level(ch, False)
        save_char_obj(game_module.current, ch)
