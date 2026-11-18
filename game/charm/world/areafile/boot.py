"""boot_db's area loading, ported from src/db.c and src/db2.c.

A Boot reads files in area.lst order into one shared set of indexes, as the game does: shops, specials and 'D'
resets look up things loaded earlier (in any file), and vnums are unique across the whole world. ``finish()``
then runs fix_exits and fix_mobprogs. Every ``bug()`` the game would log is recorded as a Diagnostic with the
same text, and every fatal condition raises AreaParseError, so the result can be compared line for line with a
real boot log (see world.py and the ``explore parity`` command).

Adapted from xania-explorer 90cfc79 areafile/parser.py: the section loop and structure carry over; every loader
was rewritten from Charm's db.c/db2.c (ROM's formats and checks differ from Xania's throughout).

Not modelled (reported, never guessed): the old #MOBOLD and #OBJOLD formats (no stock area uses them), and
area.lst's "-" (read from stdin). The first reset pass (area_update) is the game's: charm.entities.boot.

load_mobiles and load_objects come in two halves. This module reads: the model keeps what the file says. Then
charm.world.index builds the prototypes the C leaves, with a mob's race flags ORed into its own, ACT_IS_NPC set,
names looked up to numbers, and so on. Both halves carry the C function's marker.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/db2.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from charm.core.errors import CWouldCrash
from charm.core.strings import lower, str_prefix, upper

from .lookups import LookupTables, prefix_lookup
from .model import (
    AreaFile, AreaHeader, Dice, Exit, ExtraDescription, FlagRemoval, Help, Mob, MobProg, MobProgRef, Obj, ObjAffect,
    REV_DIR, Reset, Room, Shop, Social, Special,
)
from .reader import AreaParseError, Diagnostic, Reader, sh_int

MAX_KEY_HASH = 1024  # merc.h
MAX_TRADE = 5
MAX_DIR = 6
FLAG_FIELDS = ("act", "aff", "off", "imm", "res", "vul", "for", "par")  # db2.c load_mobiles 'F' lines, in order
FLAG_FIELD_NAMES = {"vul": "vuln", "for": "form", "par": "parts"}


class UnsupportedSection(AreaParseError):
    """A section the game reads but charm_tools doesn't model yet. What the game does with it is unknown here."""


@dataclass
class Counts:
    """The totals the game's ``memory`` command prints (db.c do_memory), in its order."""

    affects: int = 0  # Affects  top_affect
    areas: int = 0  # Areas    top_area
    extra_descr: int = 0  # ExDes    top_ed
    exits: int = 0  # Exits    top_exit
    helps: int = 0  # Helps    top_help
    socials: int = 0  # Socials  social_count
    mobs: int = 0  # Mobs     top_mob_index
    mobs_new: int = 0  # (n new format)  newmobs
    objects: int = 0  # Objs     top_obj_index
    objects_new: int = 0  # (n new format)  newobjs
    resets: int = 0  # Resets   top_reset (allocations; see Boot._new_reset)
    rooms: int = 0  # Rooms    top_room
    shops: int = 0  # Shops    top_shop
    mobprogs: int = 0  # top_mprog_index (logged as "Loaded %d mobprogs.", not in memory)


@dataclass
class Boot:
    tables: LookupTables
    files: list[AreaFile] = field(default_factory=list)
    areas: list[AreaHeader] = field(default_factory=list)  # every #AREA and #AREADATA, in load order (area_first)
    rooms: dict[int, Room] = field(default_factory=dict)
    mobs: dict[int, Mob] = field(default_factory=dict)
    objects: dict[int, Obj] = field(default_factory=dict)
    mobprogs: dict[int, MobProg] = field(default_factory=dict)
    room_resets: dict[int, list[Reset]] = field(default_factory=dict)  # resets attached to each room, in order
    shop_of: dict[int, Shop] = field(default_factory=dict)  # keeper vnum -> shop
    diagnostics: list[Diagnostic] = field(default_factory=list)
    counts: Counts = field(default_factory=Counts)
    area_last: AreaHeader | None = None  # global, like the C's area_last
    _reset_free: bool = False  # the reset free list (holds at most one block: a freed 'D')
    _room_order: list[int] = field(default_factory=list)
    _mob_order: list[int] = field(default_factory=list)
    finished: bool = False

    # -- the per-file section loop (boot_db, db.c:325-404) ------------------------------------------------------
    def load_file(self, path: Path, name: str | None = None) -> AreaFile:
        r = Reader.from_path(path)
        if name is not None:
            r.filename = name
        return self.load_text(r)

    def load_text(self, r: Reader) -> AreaFile:
        af = AreaFile(r.filename)
        self.files.append(af)
        current_area = None  # reset per file; load_helps attaches helps to it
        try:
            while True:
                if r.read_letter() != "#":
                    raise r.error("Boot_db: # not found.")
                word = r.read_word()
                if word.startswith("$"):
                    break
                section = upper(word)
                af.sections.append(section)
                if section == "AREA":
                    current_area = self._load_area(r, af)
                elif section == "AREADATA":
                    current_area = self._new_load_area(r, af)
                elif section == "HELPS":
                    self._load_helps(r, af)
                elif section in ("MOBOLD", "OBJOLD"):
                    raise UnsupportedSection(
                        f"#{section} (the old format) isn't modelled by charm_tools yet; how the game loads this "
                        "file is unknown here", r.filename, r.line)
                elif section == "MOBILES":
                    self._load_mobiles(r, af)
                elif section == "MOBPROGS":
                    self._load_mobprogs(r, af)
                elif section == "OBJECTS":
                    self._load_objects(r, af)
                elif section == "RESETS":
                    self._load_resets(r, af)
                elif section == "ROOMS":
                    self._load_rooms(r, af)
                elif section == "SHOPS":
                    self._load_shops(r, af)
                elif section == "SOCIALS":
                    self._load_socials(r, af)
                elif section == "SPECIALS":
                    self._load_specials(r, af)
                else:
                    raise r.error("Boot_db: bad section name.")
        finally:
            self.diagnostics.extend(r.diagnostics)
        del current_area
        return af

    # -- lookups that are fatal while booting (get_*_index with fBootDb) ---------------------------------------
    def _room(self, r: Reader | None, vnum: int) -> Room:
        if vnum in self.rooms:
            return self.rooms[vnum]
        raise self._fatal(r, f"Get_room_index: bad vnum {vnum}.")

    def _mob(self, r: Reader | None, vnum: int) -> Mob:
        if vnum in self.mobs:
            return self.mobs[vnum]
        raise self._fatal(r, f"Get_mob_index: bad vnum {vnum}.")

    def _obj(self, r: Reader | None, vnum: int) -> Obj:
        if vnum in self.objects:
            return self.objects[vnum]
        raise self._fatal(r, f"Get_obj_index: bad vnum {vnum}.")

    @staticmethod
    def _fatal(r: Reader | None, message: str) -> AreaParseError:
        if r is not None:
            return r.error(message)
        return AreaParseError(message, log=Diagnostic(message).log_lines())

    @staticmethod
    def _crash(r: Reader, what: str) -> AreaParseError:
        """fread_string returned NULL at EOF and this loader dereferences it: the game segfaults, printing nothing
        more."""
        return AreaParseError(f"the game dereferences {what} (NULL from Fread_string at EOF) and crashes",
                              r.filename, r.line, log=[])

    def _need_area(self, r: Reader, message: str) -> AreaHeader:
        if self.area_last is None:
            raise r.error(message)
        return self.area_last

    # -- #AREA (load_area, db.c:441) and #AREADATA (new_load_area, db.c:518) -----------------------------------
    # C: db.c load_area
    def _load_area(self, r: Reader, af: AreaFile) -> AreaHeader:
        file_name = r.read_string()
        name = r.read_string()
        credits = r.read_string()
        lo = r.read_number()
        hi = r.read_number()
        header = AreaHeader(file_name, name, credits, lo, hi)
        return self._add_area(af, header)

    # C: db.c new_load_area
    def _new_load_area(self, r: Reader, af: AreaFile) -> AreaHeader:
        h = AreaHeader(file_name=r.filename, name="New Area", credits="", min_vnum=0, max_vnum=0, builders="",
                       olc=True)
        while True:
            # The C reads "End" at feof(); that's true only after a read has hit the end, which this approximates.
            word = "End" if r.at_eof else r.read_word()
            w = lower(word)
            if w == "name":
                h.name = r.read_string()
            elif w == "security":
                h.security = r.read_number()
            elif w == "vnums":
                h.min_vnum = r.read_number()
                h.max_vnum = r.read_number()
            elif w == "end":
                return self._add_area(af, h)
            elif w == "builders":
                h.builders = r.read_string()
            elif w == "credits":
                h.credits = r.read_string()
            # anything else: ignored, and the loop reads the next word (no fread_to_eol)

    def _add_area(self, af: AreaFile, header: AreaHeader) -> AreaHeader:
        af.header = header  # a second #AREA in one file replaces it here; the game keeps both as areas
        header.game_min_vnum, header.game_max_vnum = header.min_vnum, header.max_vnum
        self.areas.append(header)
        self.area_last = header
        self.counts.areas += 1
        return header

    # C: db.c assign_area_vnum
    def _assign_area_vnum(self, vnum: int) -> None:
        a = self.area_last
        if a.game_min_vnum == 0 or a.game_max_vnum == 0:
            a.game_min_vnum = a.game_max_vnum = vnum
        if not a.game_min_vnum <= vnum <= a.game_max_vnum:
            if vnum < a.game_min_vnum:
                a.game_min_vnum = vnum
            else:
                a.game_max_vnum = vnum

    # -- #HELPS (load_helps, db.c:603) -------------------------------------------------------------------------
    # C: db.c load_helps
    def _load_helps(self, r: Reader, af: AreaFile) -> None:
        while True:
            line = r.line
            level = r.read_number()
            keyword = r.read_string()
            if keyword is None:
                raise self._crash(r, "the help keyword (keyword[0])")
            if keyword.startswith("$"):
                break
            af.helps.append(Help(level, keyword, r.read_string(), af.filename, line))
            self.counts.helps += 1

    # -- #MOBILES (load_mobiles, db2.c:190) --------------------------------------------------------------------
    # C: db2.c load_mobiles
    def _load_mobiles(self, r: Reader, af: AreaFile) -> None:
        area = self._need_area(r, "Load_mobiles: no #AREA seen yet.")
        t = self.tables
        while True:
            if r.read_letter() != "#":
                raise r.error("Load_mobiles: # not found.")
            line = r.line
            vnum = sh_int(r.read_number())
            if vnum == 0:
                break
            if vnum in self.mobs:
                raise r.error(f"Load_mobiles: vnum {vnum} duplicated.")
            keywords = r.read_string()
            short = r.read_string()
            long = r.read_string()
            desc = r.read_string()
            race = r.read_string()
            # In the C's order: race_lookup reads name[0], then long_descr[0] and description[0] are upper-cased.
            for value, what in ((race, "the race name (race_lookup)"), (long, "the long description"),
                                (desc, "the description")):
                if value is None:
                    raise self._crash(r, what)
            act = r.read_flag()
            aff = r.read_flag()
            alignment = r.read_number()
            group = r.read_number()
            level = r.read_number()
            hitroll = r.read_number()
            hit = self._dice(r)
            mana = self._dice(r)
            damage = self._dice(r)
            attack = r.read_word()
            ac = tuple(r.read_number() * 10 for _ in range(4))
            off, imm, res, vuln = (r.read_flag() for _ in range(4))
            start_pos = r.read_word()
            default_pos = r.read_word()
            sex = r.read_word()
            wealth = r.read_number()
            form = r.read_flag()
            parts = r.read_flag()
            size = r.read_word()
            if prefix_lookup(size, t.sizes) < 0:
                r.bug("CHECK_POS : size == -1 < 0")
            material = r.read_word()
            mob = Mob(vnum, keywords, short, long, desc, race, act, aff, alignment, group, level, hitroll, hit, mana,
                      damage, attack, ac, off, imm, res, vuln, start_pos, default_pos, sex, wealth, form, parts, size,
                      material, file=af.filename, line=line)
            while True:
                letter = r.read_letter()
                if letter == "F":
                    word = r.read_word()
                    bits = r.read_flag()
                    for prefix in FLAG_FIELDS:
                        if str_prefix(word, prefix):
                            mob.removals.append(FlagRemoval(FLAG_FIELD_NAMES.get(prefix, prefix), bits))
                            break
                    else:
                        raise r.error("Flag remove: flag not found.")
                elif letter == "M":
                    word = r.read_word()
                    i = prefix_lookup(word, [n for n, _ in t.mprog_triggers])
                    if i < 0:
                        raise r.error("MOBprogs: invalid trigger.")
                    trig, bit = t.mprog_triggers[i]
                    pvnum = r.read_number()
                    # pMprog->next = pMobIndex->mprogs: the game's list is in reverse file order.
                    mob.mobprogs.insert(0, MobProgRef(trig, bit, pvnum, r.read_string()))
                else:
                    r.ungetc()
                    break
            self.mobs[vnum] = mob
            self._mob_order.append(vnum)
            self._assign_area_vnum(vnum)
            af.mobs.append(mob)
            self.counts.mobs += 1
            self.counts.mobs_new += 1
        del area

    @staticmethod
    def _dice(r: Reader) -> Dice:
        n = r.read_number()
        r.read_letter()  # 'd' (any character is accepted)
        s = r.read_number()
        r.read_letter()  # '+'
        return Dice(n, s, r.read_number())

    # -- #OBJECTS (load_objects, db2.c:379) --------------------------------------------------------------------
    # C: db2.c load_objects
    def _load_objects(self, r: Reader, af: AreaFile) -> None:
        self._need_area(r, "Load_objects: no #AREA seen yet.")
        t, d = self.tables, self.tables.defines
        weapon, container = d["ITEM_WEAPON"], d["ITEM_CONTAINER"]
        drinks = {d["ITEM_DRINK_CON"], d["ITEM_FOUNTAIN"]}
        wands = {d["ITEM_WAND"], d["ITEM_STAFF"]}
        spells = {d["ITEM_POTION"], d["ITEM_PILL"], d["ITEM_SCROLL"]}
        item_names = [n for n, _ in t.item_types]
        while True:
            if r.read_letter() != "#":
                raise r.error("Load_objects: # not found.")
            line = r.line
            vnum = sh_int(r.read_number())
            if vnum == 0:
                break
            if vnum in self.objects:
                raise r.error(f"Load_objects: vnum {vnum} duplicated.")
            keywords = r.read_string()
            short = r.read_string()
            desc = r.read_string()
            material = r.read_string()
            type_word = r.read_word()
            i = prefix_lookup(type_word, item_names)
            item_type = t.item_types[i][1] if i >= 0 else -1
            if item_type < 0:
                r.bug(f"CHECK_POS : item_type == {item_type} < 0")
            extra = r.read_flag()
            wear = r.read_flag()
            values: list[int | str]
            if item_type == weapon:
                values = [r.read_word(), r.read_number(), r.read_number(), r.read_word(), r.read_flag()]
            elif item_type == container:
                values = [r.read_number(), r.read_flag(), r.read_number(), r.read_number(), r.read_number()]
            elif item_type in drinks:
                v0, v1, liq = r.read_number(), r.read_number(), r.read_word()
                if prefix_lookup(liq, t.liquids) < 0:
                    r.bug("CHECK_POS : liq_lookup == -1 < 0")
                values = [v0, v1, liq, r.read_number(), r.read_number()]
            elif item_type in wands:
                values = [r.read_number(), r.read_number(), r.read_number(), r.read_word(), r.read_number()]
            elif item_type in spells:
                values = [r.read_number(), r.read_word(), r.read_word(), r.read_word(), r.read_word()]
            else:
                values = [r.read_flag() for _ in range(5)]
            level = r.read_number()
            weight = r.read_number()
            cost = r.read_number()
            condition = r.read_letter()
            obj = Obj(vnum, keywords, short, desc, material, type_word, item_type, extra, wear, values, level, weight,
                      cost, condition, file=af.filename, line=line)
            while True:
                letter = r.read_letter()
                if letter == "A":
                    obj.affects.insert(0, ObjAffect("object", r.read_number(), r.read_number()))
                    self.counts.affects += 1
                elif letter == "F":
                    where = {"A": "affects", "I": "immune", "R": "resist", "V": "vuln"}.get(r.read_letter())
                    if where is None:
                        raise r.error("Load_objects: Bad where on flag set.")
                    obj.affects.insert(0, ObjAffect(where, r.read_number(), r.read_number(), r.read_flag()))
                    self.counts.affects += 1
                elif letter == "E":
                    obj.extra_descr.insert(0, ExtraDescription(r.read_string(), r.read_string()))
                    self.counts.extra_descr += 1
                else:
                    r.ungetc()
                    break
            self.objects[vnum] = obj
            self._assign_area_vnum(vnum)
            af.objects.append(obj)
            self.counts.objects += 1
            self.counts.objects_new += 1

    # -- #RESETS (load_resets, db.c:1009) ----------------------------------------------------------------------
    def _new_reset(self) -> None:
        """new_reset_data (mem.c:55): top_reset counts allocations, and a freed 'D' reset is reused by the next one
        read, without counting. So Resets in 'memory' isn't simply the number of reset lines."""
        if self._reset_free:
            self._reset_free = False
        else:
            self.counts.resets += 1

    # C: db.c load_resets
    def _load_resets(self, r: Reader, af: AreaFile) -> None:
        self._need_area(r, "Load_resets: no #AREA seen yet.")
        d = self.tables.defines
        is_door = d["EX_ISDOOR"]
        closed, locked = d["EX_CLOSED"], d["EX_LOCKED"]
        r_vnum = -1
        while True:
            letter = r.read_letter()
            if letter == "S":
                break
            if letter == "*":
                r.read_to_eol()
                continue
            line = r.line
            self._new_reset()
            r.read_number()  # if_flag, ignored
            arg1 = r.read_number()
            arg2 = r.read_number()
            arg3 = 0 if letter in ("G", "R") else r.read_number()
            arg4 = r.read_number() if letter in ("P", "M") else 0
            reset = Reset(letter, arg1, arg2, arg3, arg4, r.read_to_eol(), file=af.filename, line=line)
            af.resets.append(reset)
            if letter in ("M", "O"):
                r_vnum = arg3
            elif letter == "D":
                r_vnum = arg1
                room = self._room(r, arg1)
                ex = room.exits.get(arg2) if 0 <= arg2 < MAX_DIR else None
                if ex is None or not ex.rs_flags & is_door:
                    raise r.error(f"Load_resets: 'D': exit {arg2}, room {arg1} not door.")
                if arg3 == 1:
                    ex.rs_flags |= closed
                elif arg3 == 2:
                    ex.rs_flags |= closed | locked
                elif arg3 != 0:
                    r.bug(f"Load_resets: 'D': bad 'locks': {arg3}.")
            elif letter == "R":
                r_vnum = arg1
            if r_vnum == -1:
                raise r.error("load_resets : rVnum == -1")
            if letter != "D":
                room = self._room(r, r_vnum)
                reset.room_vnum = room.vnum
                self.room_resets.setdefault(room.vnum, []).append(reset)
            else:
                self._reset_free = True  # free_reset_data

    # -- #ROOMS (load_rooms, db.c:1113) ------------------------------------------------------------------------
    # C: db.c load_rooms
    def _load_rooms(self, r: Reader, af: AreaFile) -> None:
        area = self._need_area(r, "Load_resets: no #AREA seen yet.")  # sic: the C prints Load_resets here
        d = self.tables.defines
        law = d["ROOM_LAW"]
        lock_flags = {1: d["EX_ISDOOR"], 2: d["EX_ISDOOR"] | d["EX_PICKPROOF"], 3: d["EX_ISDOOR"] | d["EX_NOPASS"],
                      4: d["EX_ISDOOR"] | d["EX_NOPASS"] | d["EX_PICKPROOF"]}
        while True:
            if r.read_letter() != "#":
                raise r.error("Load_rooms: # not found.")
            line = r.line
            vnum = sh_int(r.read_number())
            if vnum == 0:
                break
            if vnum in self.rooms:
                raise r.error(f"Load_rooms: vnum {vnum} duplicated.")
            name = r.read_string()
            desc = r.read_string()
            r.read_number()  # area number, ignored
            flags = r.read_flag()
            room = Room(vnum, name, desc, flags, 0, area=area.name, area_index=len(self.areas) - 1,
                        file=af.filename, line=line)
            room.effective_flags = flags | (law if 3000 <= vnum < 3400 else 0)  # "horrible hack"
            room.sector = r.read_number()
            clan_index = 0
            while True:
                letter = r.read_letter()
                if letter == "S":
                    break
                if letter == "H":
                    room.heal_rate = r.read_number()
                elif letter == "M":
                    room.mana_rate = r.read_number()
                elif letter == "C":
                    if clan_index:
                        raise r.error("Load_rooms: duplicate clan fields.")
                    room.clan = r.read_string()
                    if room.clan is None:
                        raise self._crash(r, "the clan name (clan_lookup)")
                    clan_index = self._clan_lookup(room.clan)
                elif letter == "D":
                    door = r.read_number()
                    if door < 0 or door > 5:
                        raise r.error(f"Fread_rooms: vnum {vnum} has bad door number.")
                    ex_desc = r.read_string()
                    keyword = r.read_string()
                    locks = r.read_number()
                    key = r.read_number()
                    to = r.read_number()
                    room.exits[door] = Exit(door, ex_desc, keyword, locks, key, to, lock_flags.get(locks, 0))
                    self.counts.exits += 1
                elif letter == "E":
                    room.extra_descr.insert(0, ExtraDescription(r.read_string(), r.read_string()))
                    self.counts.extra_descr += 1
                elif letter == "O":
                    if room.owner is None:
                        raise self._crash(r, "the room owner (owner[0], on a second 'O' line)")
                    if room.owner:
                        raise r.error("Load_rooms: duplicate owner.")
                    room.owner = r.read_string()
                else:
                    raise r.error(f"Load_rooms: vnum {vnum} has flag not 'DES'.")
            self.rooms[vnum] = room
            self._room_order.append(vnum)
            self._assign_area_vnum(vnum)
            af.rooms.append(room)
            self.counts.rooms += 1

    def _clan_lookup(self, name: str) -> int:
        """clan_lookup (lookup.c): the empty name matches clan 0 (""); not found is 0 too."""
        if name == "":
            return 0
        i = prefix_lookup(name, self.tables.clans)
        return max(i, 0)

    # -- #SHOPS (load_shops, db.c:1287) ------------------------------------------------------------------------
    # C: db.c load_shops
    def _load_shops(self, r: Reader, af: AreaFile) -> None:
        while True:
            line = r.line
            keeper = r.read_number()
            if keeper == 0:
                break
            buy = [r.read_number() for _ in range(MAX_TRADE)]
            shop = Shop(keeper, buy, r.read_number(), r.read_number(), r.read_number(), r.read_number(),
                        af.filename, line)
            r.read_to_eol()
            self._mob(r, keeper)
            self.shop_of[keeper] = shop
            af.shops.append(shop)
            self.counts.shops += 1

    # -- #SPECIALS (load_specials, db.c:1344) ------------------------------------------------------------------
    # C: db.c load_specials
    def _load_specials(self, r: Reader, af: AreaFile) -> None:
        while True:
            letter = r.read_letter()
            if letter == "S":
                return
            if letter == "M":
                line = r.line
                vnum = r.read_number()
                self._mob(r, vnum)
                word = r.read_word()
                i = prefix_lookup(word, self.tables.specials)
                if i < 0:
                    raise r.error(f"Load_specials: 'M': vnum {vnum}.")
                af.specials.append(Special(vnum, word, self.tables.specials[i], af.filename, line))
            elif letter != "*":
                raise r.error(f"Load_specials: letter '{letter}' not *MS.")
            r.read_to_eol()

    # -- #SOCIALS (load_socials, db2.c:53) ---------------------------------------------------------------------
    # C: db2.c load_socials
    def _load_socials(self, r: Reader, af: AreaFile) -> None:
        while True:
            name = r.read_word()
            if name == "#0":
                return
            r.read_to_eol()
            messages: list[str | None] = [None] * 8
            for i in range(8):
                text = r.read_string_eol()
                if text == "$":
                    continue
                if text == "#":
                    break
                messages[i] = text
            af.socials.append(Social(name, messages))
            self.counts.socials += 1

    # -- #MOBPROGS (load_mobprogs, db.c:1519) ------------------------------------------------------------------
    # C: db.c load_mobprogs
    def _load_mobprogs(self, r: Reader, af: AreaFile) -> None:
        self._need_area(r, "Load_mobprogs: no #AREA seen yet.")
        while True:
            if r.read_letter() != "#":
                raise r.error("Load_mobprogs: # not found.")
            vnum = sh_int(r.read_number())
            if vnum == 0:
                break
            if vnum in self.mobprogs:
                raise r.error(f"Load_mobprogs: vnum {vnum} duplicated.")
            prog = MobProg(vnum, r.read_string(), af.filename)
            self.mobprogs[vnum] = prog
            af.mobprogs.append(prog)
            self.counts.mobprogs += 1

    # -- after the last file: fix_exits (db.c:1384) and fix_mobprogs (db.c:1572) -------------------------------
    def hash_order(self, order: list[int]) -> list[int]:
        """The order the C walks a vnum hash table: bucket 0..1023, newest first within a bucket."""
        buckets: dict[int, list[int]] = {}
        for vnum in order:
            if vnum < 0:  # the C's vnum % MAX_KEY_HASH is negative, and indexes before its hash table
                raise CWouldCrash(f"db.c: vnum {vnum} hashes before the start of the hash table")
            buckets.setdefault(vnum % MAX_KEY_HASH, []).insert(0, vnum)  # non-negative: checked above
        return [v for h in sorted(buckets) for v in buckets[h]]

    # C: db.c fix_exits
    # C: db.c fix_mobprogs
    def finish(self) -> None:
        if self.finished:
            return
        no_mob = self.tables.defines["ROOM_NO_MOB"]
        rooms = self.hash_order(self._room_order)
        for vnum in rooms:
            room = self.rooms[vnum]
            last_room = last_obj = None
            for rs in self.room_resets.get(vnum, []):
                c = rs.command
                if c == "M":
                    self._mob(None, rs.arg1)
                    last_room = self._room(None, rs.arg3)
                elif c == "O":
                    self._obj(None, rs.arg1)
                    last_obj = self._room(None, rs.arg3)
                elif c == "P":
                    self._obj(None, rs.arg1)
                    if last_obj is None:
                        raise self._fatal(None, f"fix_exits : reset in room {vnum} with iLastObj NULL")
                elif c in ("G", "E"):
                    self._obj(None, rs.arg1)
                    if last_room is None:
                        raise self._fatal(None, f"fix_exits : reset in room {vnum} with iLastRoom NULL")
                    last_obj = last_room
                elif c == "R":
                    self._room(None, rs.arg1)
                    if rs.arg2 < 0 or rs.arg2 > MAX_DIR:
                        raise self._fatal(None, f"fix_exits : reset in room {vnum} with arg2 {rs.arg2} >= MAX_DIR")
                else:
                    raise self._fatal(None, f"fix_exits : room {vnum} with reset cmd {c}")
            has_exit = False
            for door in range(6):
                ex = room.exits.get(door)
                if ex is not None and ex.to_vnum > 0:
                    self._room(None, ex.to_vnum)  # missing: fatal, because fBootDb is still TRUE here
                    has_exit = True
            if not has_exit:
                room.effective_flags |= no_mob
        for vnum in rooms:
            room = self.rooms[vnum]
            for door in range(6):
                ex = room.exits.get(door)
                if ex is None or ex.to_vnum <= 0:
                    continue
                to = self.rooms[ex.to_vnum]
                rev = to.exits.get(REV_DIR[door])
                if rev is None:
                    continue
                rev_to = rev.to_vnum if rev.to_vnum > 0 else 0
                if rev_to != vnum and not 1200 <= vnum <= 1299:
                    self.diagnostics.append(Diagnostic(f"Fix_exits: {vnum}:{door} -> {to.vnum}:{REV_DIR[door]} "
                                                       f"-> {rev_to}."))
        for vnum in self.hash_order(self._mob_order):
            for ref in self.mobs[vnum].mobprogs:
                if ref.vnum not in self.mobprogs:
                    raise self._fatal(None, f"Fix_mobprogs: code vnum {ref.vnum} not found.")
        self.finished = True
