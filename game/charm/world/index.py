"""The world's prototypes as the game holds them at run time: areas, rooms, exits, resets, mob and object indexes.

areafile/ reads what the area files say; ``build_index`` then makes the prototypes the C's loaders leave behind.
That's the second half of load_mobiles and load_objects: names looked up to numbers (race, attack, position, sex,
size, item type, weapon class, liquid, spell), a mob's race flags ORed into its own and its 'F' lines removed,
ACT_IS_NPC set, and the first letters of its long description and description upper-cased. Fields have the C's
names and its integer widths (sh_int, int, long).

Lists the C builds by pushing on the front (a room's people and contents, a mob's mprogs) are Python lists in the
C's order: index 0 is the C's head.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c, src/db2.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from charm.core.cint import int32, sh_int
from charm.data import constants as C
from charm.data.races import RACE_TABLE
from charm.world import lookup
from charm.world.areafile.lookups import prefix_lookup
from charm.world.areafile.model import Mob, Obj
from charm.world.areafile.world import World

MAX_DIR = 6


@dataclass(eq=False)
class Affect:
    """AFFECT_DATA. Copied, never shared: affect_to_char and affect_to_obj copy the one they're given."""

    where: int
    type: int
    level: int
    duration: int
    location: int
    modifier: int
    bitvector: int

    def copy(self) -> "Affect":
        return replace(self)


@dataclass(eq=False)
class ExtraDescr:
    keyword: str
    description: str


@dataclass(eq=False)
class Area:
    """AREA_DATA."""

    vnum: int  # its place in the area list (top_area when it was loaded)
    file_name: str
    name: str
    credits: str
    min_vnum: int
    max_vnum: int
    security: int = 9
    builders: str = "None"
    age: int = 15
    nplayer: int = 0
    empty: bool = False


@dataclass(eq=False)
class Reset:
    """RESET_DATA."""

    command: str
    arg1: int
    arg2: int
    arg3: int
    arg4: int


@dataclass(eq=False)
class Exit:
    """EXIT_DATA. ``vnum`` is the file's; ``to_room`` is what fix_exits made of it (None for vnum <= 0)."""

    vnum: int
    to_room: "Room | None"
    exit_info: int
    rs_flags: int
    key: int
    keyword: str
    description: str
    orig_door: int


@dataclass(eq=False)
class Room:
    """ROOM_INDEX_DATA."""

    vnum: int
    name: str
    description: str
    area: Area
    room_flags: int
    sector_type: int
    heal_rate: int = 100
    mana_rate: int = 100
    clan: int = 0
    owner: str = ""
    light: int = 0
    exit: list[Exit | None] = field(default_factory=lambda: [None] * MAX_DIR)
    resets: list[Reset] = field(default_factory=list)
    extra_descr: list[ExtraDescr] = field(default_factory=list)
    people: list[Any] = field(default_factory=list)  # Char, head first
    contents: list[Any] = field(default_factory=list)  # Obj, head first


@dataclass(eq=False)
class Help:
    """HELP_DATA."""

    level: int
    keyword: str
    text: str


@dataclass(eq=False)
class Shop:
    """SHOP_DATA."""

    keeper: int
    buy_type: tuple[int, ...]
    profit_buy: int
    profit_sell: int
    open_hour: int
    close_hour: int


@dataclass(eq=False)
class MobProgRef:
    """MPROG_LIST: a trigger on a mob, and the code fix_mobprogs found for it."""

    trig_type: int
    vnum: int
    trig_phrase: str
    code: str


@dataclass(eq=False)
class MobIndex:
    """MOB_INDEX_DATA."""

    vnum: int
    area: Area
    player_name: str
    short_descr: str
    long_descr: str
    description: str
    race: int
    act: int
    affected_by: int
    alignment: int
    group: int
    level: int
    hitroll: int
    hit: tuple[int, int, int]  # DICE_NUMBER, DICE_TYPE, DICE_BONUS
    mana: tuple[int, int, int]
    damage: tuple[int, int, int]
    dam_type: int
    ac: tuple[int, int, int, int]
    off_flags: int
    imm_flags: int
    res_flags: int
    vuln_flags: int
    start_pos: int
    default_pos: int
    sex: int
    wealth: int
    form: int
    parts: int
    size: int
    material: str
    mprog_flags: int = 0
    mprogs: list[MobProgRef] = field(default_factory=list)
    spec_fun: str | None = None  # the spec_table name; the function comes with special.c
    shop: Shop | None = None
    new_format: bool = True
    count: int = 0
    killed: int = 0


@dataclass(eq=False)
class ObjIndex:
    """OBJ_INDEX_DATA."""

    vnum: int
    area: Area
    name: str
    short_descr: str
    description: str
    material: str
    item_type: int
    extra_flags: int
    wear_flags: int
    value: list[int]
    level: int
    weight: int
    cost: int
    condition: int
    affected: list[Affect] = field(default_factory=list)  # head first
    extra_descr: list[ExtraDescr] = field(default_factory=list)
    new_format: bool = True
    count: int = 0
    reset_num: int = 0


@dataclass
class Index:
    """The prototypes, by vnum, and the area list in load order. Lookups return None for a vnum that isn't there,
    as get_*_index do once booting is over."""

    areas: list[Area]
    rooms: dict[int, Room]
    mobs: dict[int, MobIndex]
    objs: dict[int, ObjIndex]
    help_greeting: str | None = None  # the text of the last help whose keyword is "greeting" (load_helps)
    helps: list["Help"] = field(default_factory=list)  # help_first..help_last, in load order

    # C: db.c get_room_index
    def get_room_index(self, vnum: int) -> Room | None:
        return self.rooms.get(vnum)

    # C: db.c get_mob_index
    def get_mob_index(self, vnum: int) -> MobIndex | None:
        return self.mobs.get(vnum)

    # C: db.c get_obj_index
    def get_obj_index(self, vnum: int) -> ObjIndex | None:
        return self.objs.get(vnum)


# LATER: keep plain "\n" in memory and write "\n\r" on output, once every reader of these strings is ported
def _s(s: str | None) -> str | None:
    """A string as fread_string stores it: areafile keeps plain newlines, the game has "\\n\\r" for each."""
    return None if s is None else s.replace("\n", "\n\r")


def _upper_first(s: str) -> str:
    """``s[0] = UPPER(s[0])``: ASCII only, like the C macro."""
    return s[0].upper() + s[1:] if s and "a" <= s[0] <= "z" else s


_REMOVE_FIELD = {"act": "act", "aff": "affected_by", "off": "off_flags", "imm": "imm_flags", "res": "res_flags",
                 "vuln": "vuln_flags", "form": "form", "parts": "parts"}


# C: db2.c load_mobiles
def mob_index(m: Mob, area: Area) -> MobIndex:
    """The prototype load_mobiles leaves, from what areafile read (areafile.boot's _load_mobiles is the first half:
    the reading)."""
    race = lookup.race_lookup(m.race)
    rt = RACE_TABLE[race]
    p = MobIndex(
        vnum=m.vnum, area=area, player_name=_s(m.keywords), short_descr=_s(m.short_descr),
        long_descr=_upper_first(_s(m.long_descr)), description=_upper_first(_s(m.description)), race=race,
        act=m.act | C.ACT_IS_NPC | rt.act, affected_by=m.affected_by | rt.aff, alignment=sh_int(m.alignment),
        group=sh_int(m.group), level=sh_int(m.level), hitroll=sh_int(m.hitroll),
        hit=(sh_int(m.hit.number), sh_int(m.hit.sides), sh_int(m.hit.bonus)),
        mana=(sh_int(m.mana.number), sh_int(m.mana.sides), sh_int(m.mana.bonus)),
        damage=(sh_int(m.damage.number), sh_int(m.damage.sides), sh_int(m.damage.bonus)),
        dam_type=lookup.attack_lookup(m.attack), ac=tuple(sh_int(a) for a in m.ac),
        off_flags=m.off_flags | rt.off, imm_flags=m.imm_flags | rt.imm, res_flags=m.res_flags | rt.res,
        vuln_flags=m.vuln_flags | rt.vuln, start_pos=lookup.position_lookup(m.start_pos),
        default_pos=lookup.position_lookup(m.default_pos), sex=lookup.sex_lookup(m.sex), wealth=m.wealth,
        form=m.form | rt.form, parts=m.parts | rt.parts, size=lookup.size_lookup(m.size), material=m.material)
    for r in m.removals:  # 'F' lines, in file order, after the race flags
        name = _REMOVE_FIELD[r.field]
        setattr(p, name, getattr(p, name) & ~r.bits)
    for ref in m.mobprogs:  # already in the C's order (newest first)
        p.mprog_flags |= ref.trigger_bit
        p.mprogs.append(MobProgRef(ref.trigger_bit, ref.vnum, _s(ref.phrase), ""))
    return p


_WHERE = {"object": C.TO_OBJECT, "affects": C.TO_AFFECTS, "immune": C.TO_IMMUNE, "resist": C.TO_RESIST,
          "vuln": C.TO_VULN}


def _obj_values(o: Obj) -> list[int]:
    v = o.values
    t = o.item_type
    if t == C.ITEM_WEAPON:
        out = [lookup.weapon_type(v[0]), v[1], v[2], lookup.attack_lookup(v[3]), v[4]]
    elif t in (C.ITEM_DRINK_CON, C.ITEM_FOUNTAIN):
        out = [v[0], v[1], lookup.liq_lookup(v[2]), v[3], v[4]]
    elif t in (C.ITEM_WAND, C.ITEM_STAFF):
        out = [v[0], v[1], v[2], lookup.skill_lookup(v[3]), v[4]]
    elif t in (C.ITEM_POTION, C.ITEM_PILL, C.ITEM_SCROLL):
        out = [v[0]] + [lookup.skill_lookup(w) for w in v[1:]]
    else:
        out = list(v)
    return [int32(x) for x in out]


# C: db2.c load_objects
def obj_index(o: Obj, area: Area) -> ObjIndex:
    """The prototype load_objects leaves, from what areafile read (areafile.boot's _load_objects is the reading)."""
    level = sh_int(o.level)
    return ObjIndex(
        vnum=o.vnum, area=area, name=_s(o.keywords), short_descr=_s(o.short_descr), description=_s(o.description),
        material=_s(o.material), item_type=sh_int(o.item_type), extra_flags=int32(o.extra_flags),
        wear_flags=int32(o.wear_flags), value=_obj_values(o), level=level, weight=sh_int(o.weight),
        cost=int32(o.cost), condition=o.condition,
        affected=[Affect(_WHERE[a.where], -1, level, -1, sh_int(a.location), sh_int(a.modifier), int32(a.bitvector))
                  for a in o.affects],
        extra_descr=[ExtraDescr(_s(e.keywords), _s(e.description)) for e in o.extra_descr])


def build_index(world: World) -> Index:
    """Every prototype the boot loaded, linked the way the C links them: exits to rooms (fix_exits), mobprog code
    to triggers (fix_mobprogs), shops and specials to mobs, resets to rooms."""
    if world.fatal is not None:
        raise ValueError(f"the boot stopped: {world.fatal}")
    areas = [Area(i, _s(h.file_name), _s(h.name), _s(h.credits), h.game_min_vnum, h.game_max_vnum, h.security,
                  _s(h.builders))
             for i, h in enumerate(world.areas)]
    by_header = {id(h): areas[i] for i, h in enumerate(world.areas)}
    area_of_mob: dict[int, Area] = {}
    area_of_obj: dict[int, Area] = {}
    for f in world.files:
        a = by_header[id(f.header)] if f.header is not None else None  # the file's last #AREA
        for m in f.mobs:
            area_of_mob[m.vnum] = a
        for o in f.objects:
            area_of_obj[o.vnum] = a
    mobs = {v: mob_index(m, area_of_mob[v]) for v, m in world.mobs.items()}
    objs = {v: obj_index(o, area_of_obj[v]) for v, o in world.objects.items()}
    for f in world.files:
        for s in f.specials:  # load_specials: a later line for the same mob wins
            mobs[s.mob_vnum].spec_fun = s.resolved
    for keeper, s in world.shops.items():
        mobs[keeper].shop = Shop(keeper, tuple(s.buy_types), s.profit_buy, s.profit_sell, s.open_hour, s.close_hour)
    for m in mobs.values():
        for ref in m.mprogs:
            ref.code = _s(world.mobprogs[ref.vnum].code)
    rooms: dict[int, Room] = {}
    for v, r in world.rooms.items():
        rooms[v] = Room(v, _s(r.name), _s(r.description), areas[r.area_index], r.effective_flags, sh_int(r.sector),
                        sh_int(r.heal_rate), sh_int(r.mana_rate), 0, _s(r.owner),
                        extra_descr=[ExtraDescr(_s(e.keywords), _s(e.description)) for e in r.extra_descr])
        if r.clan:
            rooms[v].clan = max(0, prefix_lookup(r.clan, world.tables.clans))  # clan_lookup
    for v, r in world.rooms.items():
        for d, e in r.exits.items():
            rooms[v].exit[d] = Exit(e.to_vnum, rooms.get(e.to_vnum) if e.to_vnum > 0 else None, e.rs_flags,
                                    e.rs_flags, sh_int(e.key), _s(e.keyword), _s(e.description), d)
        rooms[v].resets = [Reset(rs.command, sh_int(rs.arg1), sh_int(rs.arg2), sh_int(rs.arg3), sh_int(rs.arg4))
                           for rs in world.room_resets.get(v, [])]
    greeting, helps = None, []
    for f in world.files:
        for h in f.helps:
            helps.append(Help(sh_int(h.level), _s(h.keywords), _s(h.text)))
            if h.keywords.lower() == "greeting":  # load_helps: !str_cmp (pHelp->keyword, "greeting")
                greeting = helps[-1].text
    return Index(areas, rooms, mobs, objs, greeting, helps)
