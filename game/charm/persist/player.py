"""Player files: save_char_obj and load_char_obj, and the readers and writers for a character, its objects and pet.

Ported line by line from save.c, so a file either game writes loads in the other (#25 decision 6, #30 decision 4).
The quirks are kept:
- KEY matches whole words, ignoring case, in the C's order within each first letter
- lists are written tail first, so loading (which pushes on the front) gets them back in order
- an object's Name, ShD and Desc, and a pet's ShD, LnD and Desc, are written when they're its own strings, not
  its prototype's; the C compares pointers there (own_strings, kept by things._OwnString: a string read here is
  assigned, so it's marked)
- fwrite_pet writes "Pos 8", and sets the pet standing: "pet->position = POS_FIGHTING ? ..." assigns
- in a #PET section the "no match" check sits after a break, so an unknown key is skipped a word at a time

The files are read with the area loader's Reader, whose fread_* ports are the same functions; its bug() lines are
logged at once, as the C's are.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/save.c, src/recycle.c, src/db.c. Licence terms: README.md#licence-terms
and doc/.
"""

from __future__ import annotations

import gzip
import os
import sys
from pathlib import Path

from charm.core import log
from charm.core.cint import c_div, int32, sh_int
from charm.data import constants as C
from charm.data.boards import BOARDS
from charm.data.classes import CLASS_TABLE
from charm.data.clans import CLAN_TABLE
from charm.data.races import PC_RACE_TABLE, RACE_TABLE
from charm.data.skills import GROUP_TABLE, SKILL_TABLE
from charm.entities.create import create_mobile, create_object
from charm.entities.game import Game, c_path
from charm.entities.handler import extract_obj, get_trust, is_affected, is_immortal, obj_to_char, obj_to_obj
from charm.entities.things import Char, Obj, new_char, new_obj, new_pcdata
from charm.persist.boards import BOARD_NOTFOUND, board_lookup
from charm.systems.skills import gn_add, group_add, group_lookup
from charm.world.areafile.lookups import prefix_lookup
from charm.world.areafile.reader import Reader
from charm.world.index import Affect, ExtraDescr
from charm.world.lookup import GSN, race_lookup, skill_lookup

MAX_NEST = 100  # save.c


class PlayerReader(Reader):
    """The area Reader, but bug() logs at once (no FILE/LINE: the C only prints those while an area is open)."""

    def bug(self, message: str) -> None:
        log.bug(message, 0)


# C: db.c capitalize
def capitalize(s: str) -> str:
    low = "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)
    return (low[0].upper() if "a" <= low[:1] <= "z" else low[:1]) + low[1:]


# C: save.c print_flags
def print_flags(flag: int) -> str:
    flag &= 0xFFFFFFFF  # an int parameter
    out = "".join(chr(ord("A") + n) if n < 26 else chr(ord("a") + n - 26) for n in range(32) if flag & (1 << n))
    return out or "0"


# C: recycle.c get_pc_id
def get_pc_id(game: Game) -> int:
    val = game.last_pc_id + 1 if game.current_time <= game.last_pc_id else game.current_time
    game.last_pc_id = val
    return val


def _clan_lookup(name: str) -> int:
    """lookup.c clan_lookup: 0 when not found."""
    return max(prefix_lookup(name, [c.name for c in CLAN_TABLE]), 0)


def _skill_name(sn: int) -> str:
    return SKILL_TABLE[sn].name if 0 <= sn < len(SKILL_TABLE) else "(null)"  # glibc prints NULL as "(null)"


def _affc(a: Affect) -> str:
    return "Affc '%s' %3d %3d %3d %3d %3d %10d\n" % (_skill_name(a.type), a.where, a.level, a.duration, a.modifier,
                                                    a.location, a.bitvector)


def _colour(pc, *names: str) -> str:
    return " ".join("%d%d%d" % (pc.colours[n][2], pc.colours[n][0], pc.colours[n][1]) for n in names)


COLOUR_LINES = {
    "Coloura": ("text", "auction", "gossip", "music", "question"),
    "Colourb": ("answer", "quote", "quote_text", "immtalk_text", "immtalk_type"),
    "Colourc": ("info", "tell", "reply", "gtell_text", "gtell_type"),
    "Colourd": ("room_title", "room_text", "room_exits", "room_things", "prompt"),
    "Coloure": ("fight_death", "fight_yhit", "fight_ohit", "fight_thit", "fight_skill"),
    "Colourf": ("wiznet", "say", "say_text", "tell_text", "reply_text"),
    "Colourg": ("auction_text", "gossip_text", "music_text", "question_text", "answer_text"),
}


# C: save.c fwrite_char
def fwrite_char(game: Game, ch: Char) -> str:
    out = ["#%s\n" % ("MOB" if ch.is_npc else "PLAYER"), "Name %s~\n" % ch.name, "Id   %d\n" % ch.id,
           "LogO %d\n" % game.current_time, "Vers %d\n" % 5]
    if ch.short_descr != "":
        out.append("ShD  %s~\n" % ch.short_descr)
    if ch.long_descr != "":
        out.append("LnD  %s~\n" % ch.long_descr)
    if ch.description != "":
        out.append("Desc %s~\n" % ch.description)
    if ch.prompt is not None:  # the C's condition is "prompt != NULL || ...": always true when there is one
        out.append("Prom %s~\n" % ch.prompt)
    out.append("Race %s~\n" % PC_RACE_TABLE[ch.race].name)
    if ch.clan:
        out.append("Clan %s~\n" % CLAN_TABLE[ch.clan].name)
    out += ["Sex  %d\n" % ch.sex, "Cla  %d\n" % ch.class_, "Levl %d\n" % ch.level]
    if ch.trust != 0:
        out.append("Tru  %d\n" % ch.trust)
    out += ["Sec  %d\n" % ch.pcdata.security, "Plyd %d\n" % int32(ch.played + (game.current_time - ch.logon)),
            "Scro %d\n" % ch.lines]
    limbo = game.index.get_room_index(C.ROOM_VNUM_LIMBO)
    if ch.in_room is limbo and ch.was_in_room is not None:
        room = ch.was_in_room.vnum
    else:
        room = 3001 if ch.in_room is None else ch.in_room.vnum
    out.append("Room %d\n" % room)
    out.append("HMV  %d %d %d %d %d %d\n" % (ch.hit, ch.max_hit, ch.mana, ch.max_mana, ch.move, ch.max_move))
    out.append("Gold %d\n" % (ch.gold if ch.gold > 0 else 0))
    out.append("Silv %d\n" % (ch.silver if ch.silver > 0 else 0))
    out.append("Exp  %d\n" % ch.exp)
    if ch.act != 0:
        out.append("Act  %s\n" % print_flags(ch.act))
    if ch.affected_by != 0:
        out.append("AfBy %s\n" % print_flags(ch.affected_by))
    out.append("Comm %s\n" % print_flags(ch.comm))
    if ch.wiznet:
        out.append("Wizn %s\n" % print_flags(ch.wiznet))
    if ch.invis_level:
        out.append("Invi %d\n" % ch.invis_level)
    if ch.incog_level:
        out.append("Inco %d\n" % ch.incog_level)
    out.append("Pos  %d\n" % (C.POS_STANDING if ch.position == C.POS_FIGHTING else ch.position))
    if ch.practice != 0:
        out.append("Prac %d\n" % ch.practice)
    if ch.train != 0:
        out.append("Trai %d\n" % ch.train)
    if ch.saving_throw != 0:
        out.append("Save  %d\n" % ch.saving_throw)
    out.append("Alig  %d\n" % ch.alignment)
    if ch.hitroll != 0:
        out.append("Hit   %d\n" % ch.hitroll)
    if ch.damroll != 0:
        out.append("Dam   %d\n" % ch.damroll)
    out.append("ACs %d %d %d %d\n" % tuple(ch.armor))
    if ch.wimpy != 0:
        out.append("Wimp  %d\n" % ch.wimpy)
    out.append("Attr %d %d %d %d %d\n" % tuple(ch.perm_stat))
    out.append("AMod %d %d %d %d %d\n" % tuple(ch.mod_stat))
    if ch.is_npc:
        out.append("Vnum %d\n" % ch.index.vnum)
    else:
        pc = ch.pcdata
        out.append("Pass %s~\n" % pc.pwd)
        if pc.bamfin != "":
            out.append("Bin  %s~\n" % pc.bamfin)
        if pc.bamfout != "":
            out.append("Bout %s~\n" % pc.bamfout)
        out += ["Titl %s~\n" % pc.title, "Pnts %d\n" % pc.points, "TSex %d\n" % pc.true_sex,
                "LLev %d\n" % pc.last_level, "HMVP %d %d %d\n" % (pc.perm_hit, pc.perm_mana, pc.perm_move),
                "Cnd  %d %d %d %d\n" % tuple(pc.condition)]
        for key, names in COLOUR_LINES.items():
            out.append("%s     %s\n" % (key, _colour(pc, *names)))
        for pos in range(C.MAX_ALIAS):
            if pc.alias[pos] is None or pc.alias_sub[pos] is None:
                break
            out.append("Alias %s %s~\n" % (pc.alias[pos], pc.alias_sub[pos]))
        out.append("Boards       %d " % C.MAX_BOARD + "".join("%s %d " % (b.short_name, pc.last_note[i])
                                                               for i, b in enumerate(BOARDS)) + "\n")
        for sn, s in enumerate(SKILL_TABLE):
            if pc.learned[sn] > 0:
                out.append("Sk %d '%s'\n" % (pc.learned[sn], s.name))
        for gn, g in enumerate(GROUP_TABLE):
            if pc.group_known[gn]:
                out.append("Gr '%s'\n" % g.name)
    for a in ch.affected:
        if 0 <= a.type < C.MAX_SKILL:
            out.append(_affc(a))
    out.append("End\n\n")
    return "".join(out)


# C: save.c fwrite_obj
def fwrite_obj(ch: Char, objs: list[Obj], nest: int) -> str:
    """Every object in a list (the C's next_content chain from the head), tail first."""
    out = []
    for obj in reversed(objs):  # "Slick recursion to write lists backwards, so loading them will load forwards"
        p = obj.index
        # "Castrate storage characters."
        if ((ch.level < obj.level - 2 and obj.item_type != C.ITEM_CONTAINER) or obj.item_type == C.ITEM_KEY
                or (obj.item_type == C.ITEM_MAP and not obj.value[0])):
            continue
        out += ["#O\n", "Vnum %d\n" % p.vnum]
        if not p.new_format:
            out.append("Oldstyle\n")
        if obj.enchanted:
            out.append("Enchanted\n")
        out.append("Nest %d\n" % nest)
        if "name" in obj.own_strings:
            out.append("Name %s~\n" % obj.name)
        if "short_descr" in obj.own_strings:
            out.append("ShD  %s~\n" % obj.short_descr)
        if "description" in obj.own_strings:
            out.append("Desc %s~\n" % obj.description)
        if obj.extra_flags != p.extra_flags:
            out.append("ExtF %d\n" % obj.extra_flags)
        if obj.wear_flags != p.wear_flags:
            out.append("WeaF %d\n" % obj.wear_flags)
        if obj.item_type != p.item_type:
            out.append("Ityp %d\n" % obj.item_type)
        if obj.weight != p.weight:
            out.append("Wt   %d\n" % obj.weight)
        if obj.condition != p.condition:
            out.append("Cond %d\n" % obj.condition)
        out.append("Wear %d\n" % obj.wear_loc)
        if obj.level != p.level:
            out.append("Lev  %d\n" % obj.level)
        if obj.timer != 0:
            out.append("Time %d\n" % obj.timer)
        out.append("Cost %d\n" % obj.cost)
        if list(obj.value) != list(p.value):
            out.append("Val  %d %d %d %d %d\n" % tuple(obj.value))
        if obj.item_type in (C.ITEM_POTION, C.ITEM_SCROLL, C.ITEM_PILL):
            for i in (1, 2, 3):
                if obj.value[i] > 0:
                    out.append("Spell %d '%s'\n" % (i, _skill_name(obj.value[i])))
        elif obj.item_type in (C.ITEM_STAFF, C.ITEM_WAND):
            if obj.value[3] > 0:
                out.append("Spell 3 '%s'\n" % _skill_name(obj.value[3]))
        for a in obj.affected:
            if 0 <= a.type < C.MAX_SKILL:
                out.append(_affc(a))
        for ed in obj.extra_descr:
            out.append("ExDe %s~ %s~\n" % (ed.keyword, ed.description))
        out.append("End\n\n")
        if obj.contains:
            out.append(fwrite_obj(ch, obj.contains, nest + 1))
    return "".join(out)


# C: save.c fwrite_pet
def fwrite_pet(game: Game, pet: Char) -> str:
    p = pet.index
    out = ["#PET\n", "Vnum %d\n" % p.vnum, "Name %s~\n" % pet.name, "LogO %d\n" % game.current_time]
    if "short_descr" in pet.own_strings:
        out.append("ShD  %s~\n" % pet.short_descr)
    if "long_descr" in pet.own_strings:
        out.append("LnD  %s~\n" % pet.long_descr)
    if "description" in pet.own_strings:
        out.append("Desc %s~\n" % pet.description)
    if pet.race != p.race:
        out.append("Race %s~\n" % RACE_TABLE[pet.race].name)
    if pet.clan:
        out.append("Clan %s~\n" % CLAN_TABLE[pet.clan].name)
    out.append("Sex  %d\n" % pet.sex)
    if pet.level != p.level:
        out.append("Levl %d\n" % pet.level)
    out.append("HMV  %d %d %d %d %d %d\n" % (pet.hit, pet.max_hit, pet.mana, pet.max_mana, pet.move, pet.max_move))
    if pet.gold > 0:
        out.append("Gold %d\n" % pet.gold)
    if pet.silver > 0:
        out.append("Silv %d\n" % pet.silver)
    if pet.exp > 0:
        out.append("Exp  %d\n" % pet.exp)
    if pet.act != p.act:
        out.append("Act  %s\n" % print_flags(pet.act))
    if pet.affected_by != p.affected_by:
        out.append("AfBy %s\n" % print_flags(pet.affected_by))
    if pet.comm != 0:
        out.append("Comm %s\n" % print_flags(pet.comm))
    pet.position = C.POS_STANDING  # "pet->position = POS_FIGHTING ? POS_STANDING : ..." assigns
    out.append("Pos  %d\n" % pet.position)
    if pet.saving_throw != 0:
        out.append("Save %d\n" % pet.saving_throw)
    if pet.alignment != p.alignment:
        out.append("Alig %d\n" % pet.alignment)
    if pet.hitroll != p.hitroll:
        out.append("Hit  %d\n" % pet.hitroll)
    if pet.damroll != p.damage[C.DICE_BONUS]:
        out.append("Dam  %d\n" % pet.damroll)
    out.append("ACs  %d %d %d %d\n" % tuple(pet.armor))
    out.append("Attr %d %d %d %d %d\n" % tuple(pet.perm_stat))
    out.append("AMod %d %d %d %d %d\n" % tuple(pet.mod_stat))
    for a in pet.affected:
        if 0 <= a.type < C.MAX_SKILL:
            out.append(_affc(a))
    out.append("End\n")
    return "".join(out)


# C: save.c save_char_obj
def save_char_obj(game: Game, ch: Char) -> None:
    if ch.is_npc:
        return
    if not ch.valid:  # "Fix by Edwin"
        log.bug("save_char_obj: Trying to save an invalidated character.\n", 0)
        return
    if ch.desc is not None and ch.desc.original is not None:
        ch = ch.desc.original
    if is_immortal(ch) or ch.level >= C.LEVEL_IMMORTAL:  # "create god log"
        path = c_path(game, C.GOD_DIR + capitalize(ch.name))
        try:
            path.write_text("Lev %2d Trust %2d  %s%s\n" % (ch.level, get_trust(ch), ch.name, ch.pcdata.title),
                            encoding="latin-1", newline="\n")
        except OSError as e:
            log.bug("Save_char_obj: fopen", 0)
            print(f"{path}: {e.strerror}", file=sys.stderr)
    text = fwrite_char(game, ch)
    if ch.carrying:
        text += fwrite_obj(ch, ch.carrying, 0)
    if ch.pet is not None and ch.pet.in_room is ch.in_room:  # "save the pets"
        text += fwrite_pet(game, ch.pet)
    text += "#END\n"
    temp, final = c_path(game, C.TEMP_FILE), c_path(game, C.PLAYER_DIR + capitalize(ch.name))
    try:
        temp.write_text(text, encoding="latin-1", newline="\n")
    except OSError as e:
        log.bug("Save_char_obj: fopen", 0)
        print(f"{final}: {e.strerror}", file=sys.stderr)
        return
    os.replace(temp, final)


DEFAULT_COLOURS = {
    "text": (C.NORMAL, C.WHITE, 0), "auction": (C.BRIGHT, C.YELLOW, 0), "auction_text": (C.BRIGHT, C.WHITE, 0),
    "gossip": (C.NORMAL, C.MAGENTA, 0), "gossip_text": (C.BRIGHT, C.MAGENTA, 0), "music": (C.NORMAL, C.RED, 0),
    "music_text": (C.BRIGHT, C.RED, 0), "question": (C.BRIGHT, C.YELLOW, 0),
    "question_text": (C.BRIGHT, C.WHITE, 0), "answer": (C.BRIGHT, C.YELLOW, 0),
    "answer_text": (C.BRIGHT, C.WHITE, 0), "quote": (C.NORMAL, C.YELLOW, 0), "quote_text": (C.NORMAL, C.GREEN, 0),
    "immtalk_text": (C.NORMAL, C.CYAN, 0), "immtalk_type": (C.NORMAL, C.YELLOW, 0), "info": (C.BRIGHT, C.YELLOW, 1),
    "say": (C.NORMAL, C.GREEN, 0), "say_text": (C.BRIGHT, C.GREEN, 0), "tell": (C.NORMAL, C.GREEN, 0),
    "tell_text": (C.BRIGHT, C.GREEN, 0), "reply": (C.NORMAL, C.GREEN, 0), "reply_text": (C.BRIGHT, C.GREEN, 0),
    "gtell_text": (C.NORMAL, C.GREEN, 0), "gtell_type": (C.NORMAL, C.RED, 0), "wiznet": (C.NORMAL, C.GREEN, 0),
    "room_title": (C.NORMAL, C.CYAN, 0), "room_text": (C.NORMAL, C.WHITE, 0), "room_exits": (C.NORMAL, C.GREEN, 0),
    "room_things": (C.NORMAL, C.CYAN, 0), "prompt": (C.NORMAL, C.CYAN, 0), "fight_death": (C.BRIGHT, C.RED, 0),
    "fight_yhit": (C.NORMAL, C.GREEN, 0), "fight_ohit": (C.NORMAL, C.YELLOW, 0), "fight_thit": (C.NORMAL, C.RED, 0),
    "fight_skill": (C.BRIGHT, C.WHITE, 0),
}


# C: save.c load_char_obj
def load_char_obj(game: Game, d, name: str) -> bool:
    ch = new_char(game.current_time)
    ch.pcdata = new_pcdata()
    d.character, ch.desc = ch, d
    ch.name = name
    ch.id = get_pc_id(game)
    ch.race = race_lookup("human")
    ch.act = C.PLR_NOSUMMON
    ch.comm = C.COMM_COMBINE | C.COMM_PROMPT
    ch.prompt = "<%hhp %mm %vmv> "
    pc = ch.pcdata
    pc.confirm_delete = False
    pc.board = C.DEFAULT_BOARD
    pc.pwd = pc.bamfin = pc.bamfout = pc.title = ""
    ch.perm_stat = [13] * C.MAX_STATS
    pc.condition[C.COND_THIRST] = pc.condition[C.COND_FULL] = pc.condition[C.COND_HUNGER] = 48
    pc.security = 0
    for field_name, value in DEFAULT_COLOURS.items():
        pc.colours[field_name] = list(value)

    found = False
    base = c_path(game, C.PLAYER_DIR + capitalize(name))
    gz = Path(str(base) + ".gz")
    if gz.exists():  # "decompress if .gz file exists" (gzip -dfq)
        base.write_bytes(gzip.decompress(gz.read_bytes()))
        gz.unlink()
    if base.exists():
        nest: list[Obj | None] = [None] * MAX_NEST
        found = True
        r = PlayerReader(base.read_bytes().decode("latin-1"), base.name)
        while True:
            letter = r.read_letter()
            if letter == "*":
                r.read_to_eol()
                continue
            if letter != "#":
                log.bug("Load_char_obj: # not found.", 0)
                break
            word = r.read_word().lower()
            if word == "player":
                fread_char(game, ch, r)
            elif word in ("object", "o"):
                fread_obj(game, ch, r, nest)
            elif word == "pet":
                fread_pet(game, ch, r)
            elif word == "end":
                break
            else:
                log.bug("Load_char_obj: bad section.", 0)
                break

    if found:  # initialize race
        if ch.race == 0:
            ch.race = race_lookup("human")
        ch.size = PC_RACE_TABLE[ch.race].size
        ch.dam_type = 17  # punch
        for skill in PC_RACE_TABLE[ch.race].skills:
            if skill is None:
                break
            group_add(ch, skill, False)
        rt = RACE_TABLE[ch.race]
        ch.affected_by |= rt.aff
        ch.imm_flags |= rt.imm
        ch.res_flags |= rt.res
        ch.vuln_flags |= rt.vuln
        ch.form = rt.form
        ch.parts = rt.parts
    if found and ch.version < 2:  # "RT initialize skills"
        group_add(ch, "rom basics", False)
        group_add(ch, CLASS_TABLE[ch.class_].base_group, False)
        group_add(ch, CLASS_TABLE[ch.class_].default_group, True)
        pc.learned[GSN["gsn_recall"]] = 50
    if found and ch.version < 3 and (ch.level > 35 or ch.trust > 35):  # "fix levels"
        ch.level = {40: 60, 39: 58, 38: 56, 37: 53}.get(ch.level, ch.level)
        ch.trust = {40: 60, 39: 58, 38: 56, 37: 53, 36: 51}.get(ch.trust, ch.trust)
    if found and ch.version < 4:  # "ream gold"
        ch.gold = c_div(ch.gold, 100)
    return found


def _is(word: str, *literals: str) -> bool:
    w = word.lower()
    return any(w == x.lower() for x in literals)


def _new_affect(r: Reader, with_where: bool, unknown: str) -> Affect:
    paf = Affect(0, 0, 0, 0, 0, 0, 0)  # new_affect: all zeros
    sn = skill_lookup(r.read_word())
    if sn < 0:
        log.bug(unknown, 0)
    else:
        paf.type = sn
    if with_where:
        paf.where = sh_int(r.read_number())
    paf.level = sh_int(r.read_number())
    paf.duration = sh_int(r.read_number())
    paf.modifier = sh_int(r.read_number())
    paf.location = sh_int(r.read_number())
    paf.bitvector = int32(r.read_number())
    return paf


def _load_colour(pc, field_name: str, v: int) -> None:
    """LOAD_COLOUR: the digits beep, bright, colour as one number."""
    c = pc.colours[field_name]
    c[1] = v
    if c[1] > 100:
        c[1] -= 100
        c[2] = 1
    else:
        c[2] = 0
    if c[1] > 10:
        c[1] -= 10
        c[0] = 1
    else:
        c[0] = 0


def _word(r: Reader) -> str:
    return "End" if r.at_eof else r.read_word()


# C: save.c fread_char
def fread_char(game: Game, ch: Char, r: Reader) -> None:
    pc = ch.pcdata
    count = 0
    lastlogoff = game.current_time
    log.log_string(f"Loading {ch.name}.")
    numbers = {  # KEY(literal, field, fread_number), by first letter, in the C's order
        "A": [("Alignment", "alignment"), ("Alig", "alignment")],
        "C": [("Class", "class_"), ("Cla", "class_")],
        "D": [("Damroll", "damroll"), ("Dam", "damroll")],
        "E": [("Exp", "exp")],
        "G": [("Gold", "gold")],
        "H": [("Hitroll", "hitroll"), ("Hit", "hitroll")],
        "I": [("Id", "id"), ("InvisLevel", "invis_level"), ("Inco", "incog_level"), ("Invi", "invis_level")],
        "L": [("Level", "level"), ("Lev", "level"), ("Levl", "level")],
        "P": [("Played", "played"), ("Plyd", "played"), ("Position", "position"), ("Pos", "position"),
              ("Practice", "practice"), ("Prac", "practice")],
        "S": [("SavingThrow", "saving_throw"), ("Save", "saving_throw"), ("Scro", "lines"), ("Sex", "sex")],
        "T": [("Trai", "train"), ("Trust", "trust"), ("Tru", "trust")],
        "V": [("Version", "version"), ("Vers", "version")],
        "W": [("Wimpy", "wimpy"), ("Wimp", "wimpy")],
    }
    longs = {"id", "gold", "played", "exp"}  # long and int fields; the rest are sh_int
    while True:
        word = _word(r)
        first = word[:1].upper()
        matched = True
        if first == "*":
            r.read_to_eol()
        elif first == "A" and _is(word, "Act"):
            ch.act = r.read_flag()
        elif first == "A" and _is(word, "AffectedBy", "AfBy"):
            ch.affected_by = r.read_flag()
        elif first == "A" and _is(word, "Alignment", "Alig"):
            ch.alignment = sh_int(r.read_number())
        elif first == "A" and _is(word, "Alia", "Alias"):
            if count >= C.MAX_ALIAS:
                r.read_to_eol()
            else:
                pc.alias[count] = r.read_word()
                pc.alias_sub[count] = r.read_word() if _is(word, "Alia") else r.read_string()
                count += 1
        elif first == "A" and _is(word, "AC", "Armor"):
            r.read_to_eol()
        elif first == "A" and _is(word, "ACs"):
            ch.armor = [sh_int(r.read_number()) for _ in range(4)]
        elif first == "A" and _is(word, "AffD", "Affc"):
            ch.affected.insert(0, _new_affect(r, _is(word, "Affc"), "Fread_char: unknown skill."))
        elif first == "A" and _is(word, "AttrMod", "AMod"):
            ch.mod_stat = [sh_int(r.read_number()) for _ in range(C.MAX_STATS)]
        elif first == "A" and _is(word, "AttrPerm", "Attr"):
            ch.perm_stat = [sh_int(r.read_number()) for _ in range(C.MAX_STATS)]
        elif first == "B" and _is(word, "Bamfin", "Bin"):
            pc.bamfin = r.read_string()
        elif first == "B" and _is(word, "Bamfout", "Bout"):
            pc.bamfout = r.read_string()
        elif first == "B" and _is(word, "Boards"):
            for _ in range(r.read_number()):
                boardname = r.read_word()
                i = board_lookup(boardname)
                if i == BOARD_NOTFOUND:
                    log.log_string(f"fread_char: {ch.name} had unknown board name: {boardname}. Skipped.")
                    r.read_number()
                else:
                    pc.last_note[i] = r.read_number()
        elif first == "C" and _is(word, "Class", "Cla"):
            ch.class_ = sh_int(r.read_number())
        elif first == "C" and _is(word, "Clan"):
            ch.clan = _clan_lookup(r.read_string())
        elif first == "C" and _is(word, "Comm"):
            ch.comm = r.read_flag()
        elif first == "C" and _is(word, "Condition", "Cond"):
            for i in range(3):
                pc.condition[i] = sh_int(r.read_number())
        elif first == "C" and _is(word, "Cnd"):
            for i in range(4):
                pc.condition[i] = sh_int(r.read_number())
        elif first == "C" and word.lower() in {k.lower() for k in COLOUR_LINES}:
            key = next(k for k in COLOUR_LINES if k.lower() == word.lower())
            for name in COLOUR_LINES[key]:
                _load_colour(pc, name, r.read_number())
        elif first == "D" and _is(word, "Damroll", "Dam"):
            ch.damroll = sh_int(r.read_number())
        elif first == "D" and _is(word, "Description", "Desc"):
            ch.description = r.read_string()
        elif first == "E" and _is(word, "End"):
            # "adjust hp mana move up -- here for speed's sake"
            percent = min(c_div((game.current_time - lastlogoff) * 25, 2 * 60 * 60), 100)
            if percent > 0 and not is_affected(ch, C.AFF_POISON) and not is_affected(ch, C.AFF_PLAGUE):
                ch.hit = sh_int(ch.hit + c_div((ch.max_hit - ch.hit) * percent, 100))
                ch.mana = sh_int(ch.mana + c_div((ch.max_mana - ch.mana) * percent, 100))
                ch.move = sh_int(ch.move + c_div((ch.max_move - ch.move) * percent, 100))
            return
        elif first == "G" and _is(word, "Group", "Gr"):
            temp = r.read_word()
            gn = group_lookup(temp)
            if gn < 0:
                print(temp, end="", file=sys.stderr)
                log.bug("Fread_char: unknown group. ", 0)
            else:
                gn_add(ch, gn)
        elif first == "H" and _is(word, "HpManaMove", "HMV"):
            ch.hit, ch.max_hit, ch.mana, ch.max_mana, ch.move, ch.max_move = (
                sh_int(r.read_number()) for _ in range(6))
        elif first == "H" and _is(word, "HpManaMovePerm", "HMVP"):
            pc.perm_hit, pc.perm_mana, pc.perm_move = (sh_int(r.read_number()) for _ in range(3))
        elif first == "I" and word.lower().startswith("imc") and not any(
                _is(word, lit) for lit, _ in numbers["I"]):
            r.read_to_eol()  # IMC2 was removed in R2 (#21): skip its old keys quietly
        elif first == "L" and _is(word, "LastLevel", "LLev"):
            pc.last_level = int32(r.read_number())
        elif first == "L" and _is(word, "LogO"):
            lastlogoff = int32(r.read_number())
        elif first == "L" and _is(word, "LongDescr", "LnD"):
            ch.long_descr = r.read_string()
        elif first == "N" and _is(word, "Name"):
            ch.name = r.read_string()
        elif first == "P" and _is(word, "Password", "Pass"):
            pc.pwd = r.read_string()
        elif first == "P" and _is(word, "Points", "Pnts"):
            pc.points = sh_int(r.read_number())
        elif first == "P" and _is(word, "Prompt", "Prom"):
            ch.prompt = r.read_string()
        elif first == "R" and _is(word, "Race"):
            ch.race = race_lookup(r.read_string())
        elif first == "R" and _is(word, "Room"):
            ch.in_room = game.index.get_room_index(r.read_number())
            if ch.in_room is None:
                ch.in_room = game.index.get_room_index(C.ROOM_VNUM_LIMBO)
        elif first == "S" and _is(word, "ShortDescr", "ShD"):
            ch.short_descr = r.read_string()
        elif first == "S" and _is(word, "Sec"):
            pc.security = int32(r.read_number())
        elif first == "S" and _is(word, "Silv"):
            ch.silver = r.read_number()
        elif first == "S" and _is(word, "Skill", "Sk"):
            value = r.read_number()
            temp = r.read_word()
            sn = skill_lookup(temp)
            if sn < 0:
                print(temp, end="", file=sys.stderr)
                log.bug("Fread_char: unknown skill. ", 0)
            else:
                pc.learned[sn] = sh_int(value)
        elif first == "T" and _is(word, "TrueSex", "TSex"):
            pc.true_sex = sh_int(r.read_number())
        elif first == "T" and _is(word, "Title", "Titl"):
            title = r.read_string()
            pc.title = title if title[:1] in (".", ",", "!", "?") else " " + title
        elif first == "V" and _is(word, "Vnum"):
            ch.index = game.index.get_mob_index(r.read_number())
        elif first == "W" and _is(word, "Wizn"):
            ch.wiznet = r.read_flag()
        else:
            hit = next((f for lit, f in numbers.get(first, []) if _is(word, lit)), None)
            if hit is not None:
                v = r.read_number()
                setattr(ch, hit, v if hit in longs else sh_int(v))
            else:
                matched = False
        if not matched:
            log.bug("Fread_char: no match.", 0)
            log.bug(word, 0)
            r.read_to_eol()


# C: db.c check_pet_affected
def check_pet_affected(game: Game, vnum: int, paf: Affect) -> bool:
    p = game.index.get_mob_index(vnum)
    if p is None:
        return False
    return paf.where == C.TO_AFFECTS and bool(p.affected_by & paf.bitvector)


# C: save.c fread_pet
def fread_pet(game: Game, ch: Char, r: Reader) -> None:
    ix = game.index
    lastlogoff = game.current_time
    vnum = 0
    word = "END" if r.at_eof else r.read_word()  # "first entry had BETTER be the vnum or we barf"
    if _is(word, "Vnum"):
        vnum = r.read_number()
        if ix.get_mob_index(vnum) is None:
            log.bug("Fread_pet: bad vnum %d.", vnum)
            pet = create_mobile(game, ix.get_mob_index(C.MOB_VNUM_FIDO))
        else:
            pet = create_mobile(game, ix.get_mob_index(vnum))
    else:
        log.bug("Fread_pet: no vnum in file.", 0)
        pet = create_mobile(game, ix.get_mob_index(C.MOB_VNUM_FIDO))
    strings = {"Desc": "description", "LnD": "long_descr", "Name": "name", "ShD": "short_descr"}
    numbers = {"Alig": "alignment", "Dam": "damroll", "Exp": "exp", "Gold": "gold", "Hit": "hitroll",
               "Levl": "level", "Pos": "position", "Save": "saving_throw", "Sex": "sex", "Silv": "silver"}
    while True:
        word = "END" if r.at_eof else r.read_word()
        if word[:1] == "*":
            r.read_to_eol()
        elif _is(word, "Act"):
            pet.act = r.read_flag()
        elif _is(word, "AfBy"):
            pet.affected_by = r.read_flag()
        elif _is(word, "ACs"):
            pet.armor = [sh_int(r.read_number()) for _ in range(4)]
        elif _is(word, "AffD"):
            pet.affected.insert(0, _new_affect(r, False, "Fread_char: unknown skill."))
        elif _is(word, "Affc"):
            paf = _new_affect(r, True, "Fread_char: unknown skill.")
            if not check_pet_affected(game, vnum, paf):  # "a bug with duplicating affects in saved pets"
                pet.affected.insert(0, paf)
        elif _is(word, "AMod"):
            pet.mod_stat = [sh_int(r.read_number()) for _ in range(C.MAX_STATS)]
        elif _is(word, "Attr"):
            pet.perm_stat = [sh_int(r.read_number()) for _ in range(C.MAX_STATS)]
        elif _is(word, "Clan"):
            pet.clan = _clan_lookup(r.read_string())
        elif _is(word, "Comm"):
            pet.comm = r.read_flag()
        elif _is(word, "End"):
            pet.leader = pet.master = ch
            ch.pet = pet
            percent = c_div((game.current_time - lastlogoff) * 25, 2 * 60 * 60)
            if percent > 0 and not is_affected(ch, C.AFF_POISON) and not is_affected(ch, C.AFF_PLAGUE):
                percent = min(percent, 100)
                pet.hit = sh_int(pet.hit + c_div((pet.max_hit - pet.hit) * percent, 100))
                pet.mana = sh_int(pet.mana + c_div((pet.max_mana - pet.mana) * percent, 100))
                pet.move = sh_int(pet.move + c_div((pet.max_move - pet.move) * percent, 100))
            return
        elif _is(word, "HMV"):
            pet.hit, pet.max_hit, pet.mana, pet.max_mana, pet.move, pet.max_move = (
                sh_int(r.read_number()) for _ in range(6))
        elif _is(word, "LogO"):
            lastlogoff = int32(r.read_number())
        elif _is(word, "Race"):
            pet.race = race_lookup(r.read_string())
        elif any(_is(word, k) for k in strings):
            name = strings[next(k for k in strings if _is(word, k))]
            setattr(pet, name, r.read_string())  # a new string, so the pet's own (_OwnString marks it)
        elif any(_is(word, k) for k in numbers):
            name = numbers[next(k for k in numbers if _is(word, k))]
            v = r.read_number()
            setattr(pet, name, v if name in ("gold", "silver", "exp") else sh_int(v))
        # else: nothing. The C's "no match" check is after a break, so an unknown word is just skipped.


# C: save.c fread_obj
def fread_obj(game: Game, ch: Char, r: Reader, nest: list) -> None:
    ix = game.index
    obj = None
    first = True  # "used to counter fp offset"
    new_format = make_new = False
    word = "End" if r.at_eof else r.read_word()
    if _is(word, "Vnum"):
        first = False  # "fp will be in right place"
        vnum = r.read_number()
        if ix.get_obj_index(vnum) is None:
            log.bug("Fread_obj: bad vnum %d.", vnum)
        else:
            obj = create_object(game, ix.get_obj_index(vnum), -1)
            new_format = True
    if obj is None:  # "either not found or old style"
        obj = new_obj()
        obj.name = obj.short_descr = obj.description = ""
    f_nest, f_vnum, i_nest = False, True, 0
    while True:
        if first:
            first = False
        else:
            word = "End" if r.at_eof else r.read_word()
        c = word[:1].upper()
        matched = True
        if c == "*":
            r.read_to_eol()
        elif _is(word, "AffD", "Affc"):
            obj.affected.insert(0, _new_affect(r, _is(word, "Affc"), "Fread_obj: unknown skill."))
        elif _is(word, "Cond"):
            obj.condition = sh_int(r.read_number())
        elif _is(word, "Cost"):
            obj.cost = int32(r.read_number())
        elif _is(word, "Description", "Desc"):
            obj.description = r.read_string()
        elif _is(word, "Enchanted"):
            obj.enchanted = True
        elif _is(word, "ExtraFlags", "ExtF"):
            obj.extra_flags = int32(r.read_number())
        elif _is(word, "ExtraDescr", "ExDe"):
            obj.extra_descr.insert(0, ExtraDescr(r.read_string(), r.read_string()))
        elif _is(word, "End"):
            if not f_nest or (f_vnum and obj.index is None):
                log.bug("Fread_obj: incomplete object.", 0)
                return  # free_obj; one made by create_object stays in object_list, as in the C
            if not f_vnum:
                obj = create_object(game, ix.get_obj_index(C.OBJ_VNUM_DUMMY), 0)
            if not new_format:
                game.object_list.insert(0, obj)
                obj.index.count = sh_int(obj.index.count + 1)
            if not obj.index.new_format and obj.item_type == C.ITEM_ARMOR and obj.value[1] == 0:
                obj.value[1] = obj.value[2] = obj.value[0]
            if make_new:
                wear = obj.wear_loc
                extract_obj(game, obj)
                obj = create_object(game, obj.index, 0)
                obj.wear_loc = wear
            if i_nest == 0 or nest[i_nest] is None:
                obj_to_char(obj, ch)
            else:
                obj_to_obj(obj, nest[i_nest - 1])
            return
        elif _is(word, "ItemType", "Ityp"):
            obj.item_type = sh_int(r.read_number())
        elif _is(word, "Level", "Lev"):
            obj.level = sh_int(r.read_number())
        elif _is(word, "Name"):
            obj.name = r.read_string()
        elif _is(word, "Nest"):
            i_nest = r.read_number()
            if i_nest < 0 or i_nest >= MAX_NEST:
                log.bug("Fread_obj: bad nest %d.", i_nest)
            else:
                nest[i_nest] = obj
                f_nest = True
        elif _is(word, "Oldstyle"):
            if obj.index is not None and obj.index.new_format:
                make_new = True
        elif _is(word, "ShortDescr", "ShD"):
            obj.short_descr = r.read_string()
        elif _is(word, "Spell"):
            i_value = r.read_number()
            sn = skill_lookup(r.read_word())
            if i_value < 0 or i_value > 3:
                log.bug("Fread_obj: bad iValue %d.", i_value)
            elif sn < 0:
                log.bug("Fread_obj: unknown skill.", 0)
            else:
                obj.value[i_value] = sn
        elif _is(word, "Timer", "Time"):
            obj.timer = sh_int(r.read_number())
        elif _is(word, "Values", "Vals"):
            for i in range(4):
                obj.value[i] = int32(r.read_number())
            if obj.item_type == C.ITEM_WEAPON and obj.value[0] == 0:
                obj.value[0] = obj.index.value[0]
        elif _is(word, "Val"):
            for i in range(5):
                obj.value[i] = int32(r.read_number())
        elif _is(word, "Vnum"):
            vnum = r.read_number()
            obj.index = ix.get_obj_index(vnum)
            if obj.index is None:
                log.bug("Fread_obj: bad vnum %d.", vnum)
            else:
                f_vnum = True
        elif _is(word, "WearFlags", "WeaF"):
            obj.wear_flags = int32(r.read_number())
        elif _is(word, "WearLoc", "Wear"):
            obj.wear_loc = sh_int(r.read_number())
        elif _is(word, "Weight", "Wt"):
            obj.weight = sh_int(r.read_number())
        else:
            matched = False
        if not matched:
            log.bug("Fread_obj: no match.", 0)
            r.read_to_eol()
