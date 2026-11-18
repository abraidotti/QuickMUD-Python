"""Plain data classes for what Charm's area files hold.

Values are what the *file* says, except where noted. Where the loader transforms data (merging race flags into
mobs, upper-casing the first letter of descriptions), this model keeps the file value; T2 applies the race table.

Adapted from xania-explorer 90cfc79 areafile/model.py for ROM 2.4: ROM has no spell slot numbers, one-way or
cosmetic exits, or level-band parsing in the loader; it has clans, owners, heal and mana rates, mobprog triggers
and flag-removal lines on mobs.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DIRECTIONS = ("north", "east", "south", "west", "up", "down")
REV_DIR = (2, 3, 0, 1, 5, 4)  # act_move.c rev_dir[]
CONDITIONS = {"P": 100, "G": 90, "A": 75, "W": 50, "D": 25, "B": 10, "R": 0}  # db2.c load_objects; else 100

_LEVEL_BAND = re.compile(r"^\{\s*(\w+)\s+(\w+)\s*\}")


@dataclass(frozen=True)
class Dice:
    number: int
    sides: int
    bonus: int

    @property
    def average(self) -> float:
        return self.number * (self.sides + 1) / 2 + self.bonus

    def __str__(self) -> str:
        return f"{self.number}d{self.sides}+{self.bonus}"


@dataclass
class ExtraDescription:
    keywords: str
    description: str


@dataclass
class AreaHeader:
    """#AREA (load_area) or #AREADATA (OLC's new_load_area)."""

    file_name: str  # #AREA's first string; #AREADATA uses the area.lst name
    name: str
    credits: str  # e.g. "{ 5 35} Hatchet  Mud School"
    min_vnum: int
    max_vnum: int
    builders: str = "None"
    security: int = 9
    olc: bool = False  # True for #AREADATA

    @property
    def level_band(self) -> tuple[str, str] | None:
        """The "{ lo hi}" at the start of credits: shown by the 'areas' command, not used by the loader."""
        m = _LEVEL_BAND.match(self.credits)
        return (m.group(1), m.group(2)) if m else None


@dataclass
class MobProgRef:
    """An 'M' line on a mob: trigger, mobprog vnum, trigger phrase."""

    trigger: str
    trigger_bit: int
    vnum: int
    phrase: str


@dataclass
class FlagRemoval:
    """An 'F' line on a mob: clear these bits from one flag field after the race flags are added."""

    field: str  # act, aff, off, imm, res, vuln, form or parts (the word in the file may be a prefix)
    bits: int


@dataclass
class Mob:
    vnum: int
    keywords: str
    short_descr: str
    long_descr: str
    description: str
    race: str
    act: int  # file value; the game ORs in ACT_IS_NPC and the race's act flags
    affected_by: int
    alignment: int
    group: int
    level: int
    hitroll: int
    hit: Dice
    mana: Dice
    damage: Dice
    attack: str  # dam_type word (attack_lookup; 0 if unknown, no error)
    ac: tuple[int, int, int, int]  # pierce, bash, slash, exotic: file value x 10, as the game stores it
    off_flags: int
    imm_flags: int
    res_flags: int
    vuln_flags: int
    start_pos: str
    default_pos: str
    sex: str
    wealth: int
    form: int
    parts: int
    size: str
    material: str
    removals: list[FlagRemoval] = field(default_factory=list)
    mobprogs: list[MobProgRef] = field(default_factory=list)
    file: str = ""
    line: int = 0


@dataclass
class ObjAffect:
    where: str  # "object" for 'A' lines; "affects", "immune", "resist" or "vuln" for 'F' lines
    location: int
    modifier: int
    bitvector: int = 0


@dataclass
class Obj:
    vnum: int
    keywords: str
    short_descr: str
    description: str
    material: str
    type_word: str
    item_type: int  # item_lookup result; -1 if unknown (the game logs CHECK_POS and keeps -1)
    extra_flags: int
    wear_flags: int
    # value[0..4] as read: numbers, or words where the game looks a name up (weapon type and attack for weapons,
    # the liquid for drink containers and fountains, spell names for wands, staves, potions, pills and scrolls).
    values: list[int | str]
    level: int
    weight: int
    cost: int
    condition_letter: str
    affects: list[ObjAffect] = field(default_factory=list)
    extra_descr: list[ExtraDescription] = field(default_factory=list)
    file: str = ""
    line: int = 0

    @property
    def condition(self) -> int:
        return CONDITIONS.get(self.condition_letter, 100)


@dataclass
class Exit:
    direction: int
    description: str
    keyword: str
    locks: int  # 1 door, 2 +pickproof, 3 +nopass, 4 +both; anything else: no door flags
    key: int
    to_vnum: int
    rs_flags: int = 0  # EX_ISDOOR etc. from locks, plus EX_CLOSED/EX_LOCKED from 'D' resets

    @property
    def direction_name(self) -> str:
        return DIRECTIONS[self.direction]


@dataclass
class Room:
    vnum: int
    name: str
    description: str
    room_flags: int  # file value
    sector: int
    exits: dict[int, Exit] = field(default_factory=dict)
    extra_descr: list[ExtraDescription] = field(default_factory=list)
    heal_rate: int = 100
    mana_rate: int = 100
    clan: str = ""
    owner: str = ""
    effective_flags: int = 0  # after the loader: the 3000-3399 ROOM_LAW hack, and ROOM_NO_MOB from fix_exits
    area: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Reset:
    command: str  # M O P G E D R (anything else is fatal later, in fix_exits)
    arg1: int
    arg2: int
    arg3: int
    arg4: int
    comment: str  # the rest of the line
    room_vnum: int | None = None  # the room the game attaches it to (D resets aren't kept)
    file: str = ""
    line: int = 0


@dataclass
class Shop:
    keeper: int
    buy_types: list[int]  # MAX_TRADE (5) item types; 0 = none
    profit_buy: int
    profit_sell: int
    open_hour: int
    close_hour: int
    file: str = ""
    line: int = 0


@dataclass
class Special:
    mob_vnum: int
    spec_fun: str  # the word in the file
    resolved: str  # the spec_table entry it matched
    file: str = ""
    line: int = 0


@dataclass
class Help:
    level: int
    keywords: str
    text: str
    file: str = ""
    line: int = 0


@dataclass
class Social:
    name: str
    # char_no_arg, others_no_arg, char_found, others_found, vict_found, char_not_found, char_auto, others_auto:
    # None where the file had "$" or the social ended early with "#".
    messages: list[str | None]


@dataclass
class MobProg:
    vnum: int
    code: str
    file: str = ""


@dataclass
class AreaFile:
    """Everything boot_db read from one file in area.lst."""

    filename: str
    header: AreaHeader | None = None
    sections: list[str] = field(default_factory=list)  # in the order seen
    mobs: list[Mob] = field(default_factory=list)
    objects: list[Obj] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    resets: list[Reset] = field(default_factory=list)  # every reset line read, D included
    shops: list[Shop] = field(default_factory=list)
    specials: list[Special] = field(default_factory=list)
    mobprogs: list[MobProg] = field(default_factory=list)
    helps: list[Help] = field(default_factory=list)
    socials: list[Social] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.header.name if self.header else self.filename
