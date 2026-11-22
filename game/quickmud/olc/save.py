"""olc_save.c: asave, which writes areas back to their files in OLC's format (#AREADATA, new-format mobs and
objects), the area list, and the help files OLC changed.

The C walks the vnum hash tables (bucket 0 to 1023, newest first in a bucket), so rooms, specials, resets and
shops come out in that order, not the file's. Its strings go through fprintf's %s, which prints a NULL pointer as
"(null)" (glibc); _s does the same for None.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/olc_save.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.core.cint import c_div
from quickmud.core.errors import CWouldCrash
from quickmud.core.log import bug, log_string
from quickmud.core.strings import atoi, smash_tilde, str_cmp
from quickmud.data import constants as C
from quickmud.data.attacks import ATTACK_TABLE
from quickmud.data.characters import POSITION_TABLE, SEX_TABLE
from quickmud.data.clans import CLAN_TABLE
from quickmud.data.flags import WEAR_LOC_STRINGS
from quickmud.data.items import LIQ_TABLE
from quickmud.data.races import RACE_TABLE, SIZE_TABLE
from quickmud.data.skills import SKILL_TABLE
from quickmud.olc import ED_AREA, ED_HELP, ED_MOBILE, ED_NONE, ED_OBJECT, ED_ROOM
from quickmud.olc.bits import flag_string

STRFIX = C.MAX_STRING_LENGTH * 2  # fix_string's static buffer


def _game():
    from quickmud.entities import game as game_module

    return game_module.current


def _s(s: str | None) -> str:
    """fprintf's %s: glibc prints a NULL pointer as "(null)"."""
    return "(null)" if s is None else s


def _chains(protos) -> list[list]:
    """A vnum hash table's chains (index_hash[vnum % MAX_KEY_HASH]), newest first, from prototypes in the order
    they were made (the index's dicts keep that order)."""
    chains: list[list] = [[] for _ in range(C.MAX_KEY_HASH)]
    for p in protos:
        if p.vnum < 0:
            raise CWouldCrash(f"olc_save.c: vnum {p.vnum} hashes before the start of the hash table")
        chains[p.vnum % C.MAX_KEY_HASH].insert(0, p)  # non-negative: checked above
    return chains


def _hash_order(protos) -> list:
    return [p for chain in _chains(protos) for p in chain]


def _open(game, name: str):
    """fopen (name, "w") from the directory the C runs in, or None."""
    from quickmud.entities.game import c_path

    try:
        return open(c_path(game, name), "w", encoding="latin-1", newline="")
    except OSError:
        return None


# C: olc_save.c fix_string
def fix_string(s: str | None) -> str | None:
    """The string without "\\r" and "~" (None for NULL, which the C returns as '\\0'). The C copies the character
    after one it skips without looking at it, so a second "\\r" or "~" in a row stays; a skip onto the end of the
    string ends it (the C then reads on past the terminator, into a part of its buffer nothing prints)."""
    if s is None:
        return None
    chars, p, n = [], 0, len(s)
    while p < n:
        if s[p] in "\r~":
            p += 1
            if p == n:
                break
        chars.append(s[p])
        p += 1
    out = "".join(chars)
    if len(out) >= STRFIX:
        raise CWouldCrash(f"olc_save.c fix_string: {len(out)} characters overflow its {STRFIX}-byte buffer")
    return out


# C: olc_save.c save_area_list
def save_area_list(game) -> None:
    fp = _open(game, "area.lst")
    if fp is None:
        bug("Save_area_list: fopen", 0)
        return
    with fp:
        fp.write("social.are\n")  # "ROM OLC"
        for ha in game.index.had_list:  # "Add any help files that need to be loaded at startup"
            if ha.area is None:
                fp.write("%s\n" % _s(ha.filename))
        for area in game.index.areas:
            fp.write("%s\n" % _s(area.file_name))
        fp.write("$\n")


# C: olc_save.c fwrite_flag
def fwrite_flag(flags: int) -> str:
    """Flags as fread_flag reads them: a letter for each of the 32 bits set (A-Z, then a-f), or "0"."""
    if flags == 0:
        return "0"
    out = []
    for offset in range(32):
        if flags & (1 << offset):
            out.append(chr(ord("A") + offset) if offset <= 25 else chr(ord("a") + offset - 26))
    return "".join(out)


# C: olc_save.c save_mobprogs
def save_mobprogs(fp, area) -> None:
    index = _game().index
    fp.write("#MOBPROGS\n")
    for i in range(area.min_vnum, area.max_vnum + 1):
        code = index.get_mprog_index(i)
        if code is not None:
            fp.write("#%d\n" % i)
            fp.write("%s~\n" % _s(fix_string(code)))
    fp.write("#0\n\n")


def _dif(a: int, b: int) -> int:
    """DIF(a, b): the bits a has and b hasn't."""
    return a & ~b


# C: olc_save.c save_mobile
def save_mobile(fp, p) -> None:
    from quickmud.systems.mobcmds import mprog_type_to_name

    race = RACE_TABLE[p.race]
    w = fp.write
    w("#%d\n" % p.vnum)
    w("%s~\n" % _s(p.player_name))
    w("%s~\n" % _s(p.short_descr))
    w("%s~\n" % _s(fix_string(p.long_descr)))
    w("%s~\n" % _s(fix_string(p.description)))
    w("%s~\n" % _s(race.name))
    w("%s " % fwrite_flag(p.act))
    w("%s " % fwrite_flag(p.affected_by))
    w("%d %d\n" % (p.alignment, p.group))
    w("%d " % p.level)
    w("%d " % p.hitroll)
    w("%dd%d+%d " % p.hit)
    w("%dd%d+%d " % p.mana)
    w("%dd%d+%d " % p.damage)
    w("%s\n" % _s(ATTACK_TABLE[p.dam_type].name))
    w("%d %d %d %d\n" % (c_div(p.ac[C.AC_PIERCE], 10), c_div(p.ac[C.AC_BASH], 10), c_div(p.ac[C.AC_SLASH], 10),
                         c_div(p.ac[C.AC_EXOTIC], 10)))
    w("%s " % fwrite_flag(p.off_flags))
    w("%s " % fwrite_flag(p.imm_flags))
    w("%s " % fwrite_flag(p.res_flags))
    w("%s\n" % fwrite_flag(p.vuln_flags))
    w("%s %s %s %d\n" % (_s(POSITION_TABLE[p.start_pos].short_name), _s(POSITION_TABLE[p.default_pos].short_name),
                         _s(SEX_TABLE[p.sex].name), p.wealth))
    w("%s " % fwrite_flag(p.form))
    w("%s " % fwrite_flag(p.parts))
    w("%s " % _s(SIZE_TABLE[p.size].name))
    # The C's test is backwards (#92): a material is written as "unknown", and an empty one as itself.
    w("%s\n" % (_s(p.material) if not p.material else "unknown"))
    for letter, race_bits, own in (("act", race.act, p.act), ("aff", race.aff, p.affected_by),
                                   ("off", race.off, p.off_flags), ("imm", race.imm, p.imm_flags),
                                   ("res", race.res, p.res_flags), ("vul", race.vuln, p.vuln_flags),
                                   ("for", race.form, p.form), ("par", race.parts, p.parts)):
        temp = _dif(race_bits, own)
        if temp:
            w("F %s %s\n" % (letter, fwrite_flag(temp)))
    for prog in p.mprogs:
        w("M %s %d %s~\n" % (mprog_type_to_name(prog.trig_type), prog.vnum, _s(prog.trig_phrase)))


# C: olc_save.c save_mobiles
def save_mobiles(fp, area) -> None:
    index = _game().index
    fp.write("#MOBILES\n")
    for i in range(area.min_vnum, area.max_vnum + 1):
        p = index.get_mob_index(i)
        if p is not None:
            save_mobile(fp, p)
    fp.write("#0\n\n\n\n")


def _skill_name(sn: int) -> str:
    return _s(SKILL_TABLE[sn].name) if sn != -1 else ""


# C: olc_save.c save_object
def save_object(fp, p) -> None:
    from quickmud.entities.handler import item_name, weapon_name

    w = fp.write
    v = p.value
    w("#%d\n" % p.vnum)
    w("%s~\n" % _s(p.name))
    w("%s~\n" % _s(p.short_descr))
    w("%s~\n" % _s(fix_string(p.description)))
    w("%s~\n" % _s(p.material))
    w("%s " % item_name(p.item_type))
    w("%s " % fwrite_flag(p.extra_flags))
    w("%s\n" % fwrite_flag(p.wear_flags))
    t = p.item_type
    if t in (C.ITEM_DRINK_CON, C.ITEM_FOUNTAIN):
        w("%d %d '%s' %d %d\n" % (v[0], v[1], _s(LIQ_TABLE[v[2]].liq_name), v[3], v[4]))
    elif t == C.ITEM_CONTAINER:
        w("%d %s %d %d %d\n" % (v[0], fwrite_flag(v[1]), v[2], v[3], v[4]))
    elif t == C.ITEM_WEAPON:
        w("%s %d %d %s %s\n" % (weapon_name(v[0]), v[1], v[2], _s(ATTACK_TABLE[v[3]].name), fwrite_flag(v[4])))
    elif t in (C.ITEM_PILL, C.ITEM_POTION, C.ITEM_SCROLL):
        w("%d '%s' '%s' '%s' '%s'\n" % (v[0] if v[0] > 0 else 0, _skill_name(v[1]), _skill_name(v[2]),
                                        _skill_name(v[3]), _skill_name(v[4])))
    elif t in (C.ITEM_STAFF, C.ITEM_WAND):
        w("%d %d %d '%s' %d\n" % (v[0], v[1], v[2], _skill_name(v[3]), v[4]))
    else:
        w("%s %s %s %s %s\n" % tuple(fwrite_flag(x) for x in v[:5]))
    w("%d " % p.level)
    w("%d " % p.weight)
    w("%d " % p.cost)
    c = p.condition
    letter = ("P" if c > 90 else "G" if c > 75 else "A" if c > 50 else "W" if c > 25 else "D" if c > 10
              else "B" if c > 0 else "R")
    w("%s\n" % letter)
    for af in p.affected:
        if af.where == C.TO_OBJECT or af.bitvector == 0:
            w("A\n%d %d\n" % (af.location, af.modifier))
        else:
            w("F\n")
            where = {C.TO_AFFECTS: "A ", C.TO_IMMUNE: "I ", C.TO_RESIST: "R ", C.TO_VULN: "V "}.get(af.where)
            if where is None:
                bug("olc_save: Invalid Affect->where", 0)
            else:
                w(where)
            w("%d %d %s\n" % (af.location, af.modifier, fwrite_flag(af.bitvector)))
    for ed in p.extra_descr:
        w("E\n%s~\n%s~\n" % (_s(ed.keyword), _s(fix_string(ed.description))))


# C: olc_save.c save_objects
def save_objects(fp, area) -> None:
    index = _game().index
    fp.write("#OBJECTS\n")
    for i in range(area.min_vnum, area.max_vnum + 1):
        p = index.get_obj_index(i)
        if p is not None:
            save_object(fp, p)
    fp.write("#0\n\n\n\n")


_DOOR_FLAGS = (C.EX_CLOSED | C.EX_LOCKED | C.EX_PICKPROOF | C.EX_NOPASS | C.EX_EASY | C.EX_HARD | C.EX_INFURIATING
               | C.EX_NOCLOSE | C.EX_NOLOCK)


# C: olc_save.c save_rooms
def save_rooms(fp, area) -> None:
    w = fp.write
    w("#ROOMS\n")
    for room in _hash_order(_game().index.rooms.values()):
        if room.area is not area:
            continue
        w("#%d\n" % room.vnum)
        w("%s~\n" % _s(room.name))
        w("%s~\n" % _s(fix_string(room.description)))
        w("0 ")
        w("%d " % room.room_flags)
        w("%d\n" % room.sector_type)
        for ed in room.extra_descr:
            w("E\n%s~\n%s~\n" % (_s(ed.keyword), _s(fix_string(ed.description))))
        for door in range(C.MAX_DIR):
            ex = room.exit[door]
            if ex is None or ex.to_room is None:
                continue
            # "HACK : TO PREVENT EX_LOCKED etc without EX_ISDOOR to stop booting the mud": this changes the exit,
            # and takes EX_ISDOOR off a door with nothing else set, one that starts open (#92)
            if ex.rs_flags & _DOOR_FLAGS:
                ex.rs_flags |= C.EX_ISDOOR
            else:
                ex.rs_flags &= ~C.EX_ISDOOR
            locks = 0
            door_ = ex.rs_flags & C.EX_ISDOOR
            pick, nopass = ex.rs_flags & C.EX_PICKPROOF, ex.rs_flags & C.EX_NOPASS
            if door_ and not pick and not nopass:
                locks = 1
            if door_ and pick and not nopass:
                locks = 2
            if door_ and not pick and nopass:
                locks = 3
            if door_ and pick and nopass:
                locks = 4
            w("D%d\n" % ex.orig_door)
            w("%s~\n" % _s(fix_string(ex.description)))
            w("%s~\n" % _s(ex.keyword))
            w("%d %d %d\n" % (locks, ex.key, ex.to_room.vnum))
        if room.mana_rate != 100 or room.heal_rate != 100:
            w("M %d H %d\n" % (room.mana_rate, room.heal_rate))
        if room.clan > 0:
            w("C %s~\n" % _s(CLAN_TABLE[room.clan].name))
        if room.owner:  # !IS_NULLSTR
            w("O %s~\n" % room.owner)
        w("S\n")
    w("#0\n\n\n\n")


# C: olc_save.c save_specials
def save_specials(fp, area) -> None:
    from quickmud.world.lookup import spec_name

    fp.write("#SPECIALS\n")
    for p in _hash_order(_game().index.mobs.values()):
        if p.area is area and p.spec_fun:
            fp.write("M %d %s\n" % (p.vnum, _s(spec_name(p.spec_fun))))
    fp.write("S\n\n\n\n")


# C: olc_save.c save_door_resets
def save_door_resets(fp, area) -> None:
    for room in _hash_order(_game().index.rooms.values()):
        if room.area is not area:
            continue
        for door in range(C.MAX_DIR):
            ex = room.exit[door]
            if ex is not None and ex.to_room is not None and ex.rs_flags & (C.EX_CLOSED | C.EX_LOCKED):
                fp.write("D 0 %d %d %d\n" % (room.vnum, ex.orig_door, 2 if ex.rs_flags & C.EX_LOCKED else 1))


def _short(proto, what: str) -> str:
    if proto is None:
        raise CWouldCrash(f"olc_save.c save_resets: {what} names no prototype")
    return _s(proto.short_descr)


# C: olc_save.c save_resets
def save_resets(fp, area) -> None:
    """The rooms' resets, in hash order. An 'O' or 'R' reset sets the C's loop variable to the room it names, so
    the walk goes on from that room's place in its own hash chain (the same room, for any reset the loader made)."""
    from quickmud.persist.player import capitalize

    index = _game().index
    w = fp.write
    w("#RESETS\n")
    save_door_resets(fp, area)
    chains = _chains(index.rooms.values())
    last_mob = None
    for ih in range(C.MAX_KEY_HASH):
        chain, j = chains[ih], 0
        while j < len(chain):
            room = chain[j]
            if room.area is area:
                for rs in room.resets:
                    c = rs.command
                    if c == "M":
                        last_mob = index.get_mob_index(rs.arg1)
                        w("M 0 %d %d %d %d Load %s\n" % (rs.arg1, rs.arg2, rs.arg3, rs.arg4, _short(last_mob, "M")))
                    elif c == "O":
                        last_obj = index.get_obj_index(rs.arg1)
                        room = index.get_room_index(rs.arg3)
                        if room is None:
                            raise CWouldCrash(f"olc_save.c save_resets: O reset to room {rs.arg3}, which isn't")
                        w("O 0 %d 0 %d %s loaded to %s\n" % (rs.arg1, rs.arg3, capitalize(_short(last_obj, "O")),
                                                             _s(room.name)))
                    elif c == "P":
                        last_obj = index.get_obj_index(rs.arg1)
                        # "put inside" names the object itself, not its container (arg3) (#92)
                        w("P 0 %d %d %d %d %s put inside %s\n" % (rs.arg1, rs.arg2, rs.arg3, rs.arg4,
                                                                  capitalize(_short(last_obj, "P")),
                                                                  _short(last_obj, "P")))
                    elif c == "G":
                        w("G 0 %d 0 %s is given to %s\n" % (
                            rs.arg1, capitalize(_short(index.get_obj_index(rs.arg1), "G")),
                            _s(last_mob.short_descr) if last_mob is not None else "!NO_MOB!"))
                        if last_mob is None:
                            bug("Save_resets: !NO_MOB! in [%s]" % _s(area.file_name), 0)
                    elif c == "E":
                        w("E 0 %d 0 %d %s is loaded %s of %s\n" % (
                            rs.arg1, rs.arg3, capitalize(_short(index.get_obj_index(rs.arg1), "E")),
                            flag_string(WEAR_LOC_STRINGS, rs.arg3),
                            _s(last_mob.short_descr) if last_mob is not None else "!NO_MOB!"))
                        if last_mob is None:
                            bug("Save_resets: !NO_MOB! in [%s]" % _s(area.file_name), 0)
                    elif c == "D":
                        pass
                    elif c == "R":
                        room = index.get_room_index(rs.arg1)
                        if room is None:
                            raise CWouldCrash(f"olc_save.c save_resets: R reset in room {rs.arg1}, which isn't")
                        w("R 0 %d %d Randomize %s\n" % (rs.arg1, rs.arg2, _s(room.name)))
                    else:
                        bug("Save_resets: bad command %c.", ord(c[:1] or "\0"))
            # pRoom = pRoom->next: the next room in the chain the (maybe changed) room is in
            chain = chains[room.vnum % C.MAX_KEY_HASH]  # non-negative: _chains refused negative vnums
            j = next(k for k, r in enumerate(chain) if r is room) + 1
    w("S\n\n\n\n")


# C: olc_save.c save_shops
def save_shops(fp, area) -> None:
    w = fp.write
    w("#SHOPS\n")
    for p in _hash_order(_game().index.mobs.values()):
        if p.area is area and p.shop is not None:
            shop = p.shop
            w("%d " % shop.keeper)
            for i in range(C.MAX_TRADE):
                w("%d " % shop.buy_type[i] if shop.buy_type[i] != 0 else "0 ")
            w("%d %d " % (shop.profit_buy, shop.profit_sell))
            w("%d %d\n" % (shop.open_hour, shop.close_hour))
    w("0\n\n\n\n")


# C: olc_save.c save_helps
def save_helps(fp, ha) -> None:
    fp.write("#HELPS\n")
    for help in ha.helps:
        fp.write("%d %s~\n" % (help.level, _s(help.keyword)))
        fp.write("%s~\n\n" % _s(fix_string(help.text)))
    fp.write("-1 $~\n\n")
    ha.changed = False


# C: olc_save.c save_other_helps
def save_other_helps(ch) -> None:
    from quickmud.net.output import printf_to_char

    game = _game()
    for ha in game.index.had_list:
        if ha.changed:
            fp = _open(game, ha.filename)
            if fp is None:  # perror (ha->filename), to stderr
                return
            with fp:
                save_helps(fp, ha)
                if ch is not None:
                    printf_to_char(ch, "%s\n\r", _s(ha.filename))
                fp.write("#$\n")


# C: olc_save.c save_area
def save_area(area) -> None:
    game = _game()
    fp = _open(game, area.file_name)
    if fp is None:
        bug("Open_area: fopen", 0)
        raise CWouldCrash(f"olc_save.c save_area: can't open {area.file_name}, and fprintf gets a NULL file")
    with fp:
        w = fp.write
        w("#AREADATA\n")
        w("Name %s~\n" % _s(area.name))
        w("Builders %s~\n" % _s(fix_string(area.builders)))
        w("VNUMs %d %d\n" % (area.min_vnum, area.max_vnum))
        w("Credits %s~\n" % _s(area.credits))
        w("Security %d\n" % area.security)
        w("End\n\n\n\n")
        save_mobiles(fp, area)
        save_objects(fp, area)
        save_rooms(fp, area)
        save_specials(fp, area)
        save_resets(fp, area)
        save_shops(fp, area)
        save_mobprogs(fp, area)
        if area.helps is not None and area.helps.helps:
            save_helps(fp, area.helps)
        w("#$\n")


# C: olc.c get_area_data
def get_area_data(vnum: int):
    return next((a for a in _game().index.areas if a.vnum == vnum), None)


# C: olc_save.c do_asave
def do_asave(ch, argument: str) -> None:
    from quickmud.commands.interp import is_number
    from quickmud.entities.handler import is_builder
    from quickmud.net.output import send_to_char

    game = _game()
    arg1 = smash_tilde(argument)
    if arg1 == "":
        if ch is not None:
            send_to_char("Syntax:\n\r", ch)
            send_to_char("  asave <vnum>   - saves a particular area\n\r", ch)
            send_to_char("  asave list     - saves the area.lst file\n\r", ch)
            send_to_char("  asave area     - saves the area being edited\n\r", ch)
            send_to_char("  asave changed  - saves all changed zones\n\r", ch)
            send_to_char("  asave world    - saves the world! (db dump)\n\r", ch)
            send_to_char("\n\r", ch)
        return

    # "Snarf the value (which need not be numeric)."
    value = atoi(arg1)
    area = get_area_data(value)
    if area is None and is_number(arg1):
        if ch is not None:
            send_to_char("That area does not exist.\n\r", ch)
        return

    if is_number(arg1):  # "Save area of given vnum."
        if ch is not None and not is_builder(ch, area):
            send_to_char("You are not a builder for this area.\n\r", ch)
            return
        save_area_list(game)
        save_area(area)
        return

    if str_cmp("world", arg1):  # "Save the world, only authorized areas."
        save_area_list(game)
        for area in game.index.areas:
            if ch is not None and not is_builder(ch, area):  # "Builder must be assigned this area."
                continue
            save_area(area)
            area.area_flags &= ~C.AREA_CHANGED
        if ch is not None:
            send_to_char("You saved the world.\n\r", ch)
        save_other_helps(None)
        return

    if str_cmp("changed", arg1):  # "Save changed areas, only authorized areas."
        save_area_list(game)
        if ch is not None:
            send_to_char("Saved zones:\n\r", ch)
        else:
            log_string("Saved zones:")
        buf = "None.\n\r"
        for area in game.index.areas:
            if ch is not None and not is_builder(ch, area):
                continue
            if area.area_flags & C.AREA_CHANGED:
                save_area(area)
                buf = "%24s - '%s'" % (_s(area.name), _s(area.file_name))
                if ch is not None:
                    send_to_char(buf, ch)
                    send_to_char("\n\r", ch)
                else:
                    log_string(buf)
                area.area_flags &= ~C.AREA_CHANGED
        save_other_helps(ch)
        if str_cmp(buf, "None.\n\r"):
            if ch is not None:
                send_to_char(buf, ch)
            else:
                log_string("None.")
        return

    if str_cmp(arg1, "list"):  # "Save the area.lst file."
        save_area_list(game)
        return

    if str_cmp(arg1, "area"):  # "Save area being edited, if authorized."
        if ch is None or ch.desc is None:
            return
        d = ch.desc
        if d.editor == ED_NONE:
            send_to_char("You are not editing an area, therefore an area vnum is required.\n\r", ch)
            return
        if d.editor == ED_AREA:
            area = d.pEdit
        elif d.editor == ED_ROOM:
            area = ch.in_room.area
        elif d.editor in (ED_OBJECT, ED_MOBILE):
            area = d.pEdit.area
        elif d.editor == ED_HELP:
            send_to_char("Grabando area : ", ch)
            save_other_helps(ch)
            return
        else:
            area = ch.in_room.area
        if not is_builder(ch, area):
            send_to_char("You are not a builder for this area.\n\r", ch)
            return
        save_area_list(game)
        save_area(area)
        area.area_flags &= ~C.AREA_CHANGED
        send_to_char("Area saved.\n\r", ch)
        return

    if ch is not None:  # "Show correct syntax."
        do_asave(ch, "")
