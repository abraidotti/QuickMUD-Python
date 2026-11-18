"""CHAR_DATA and OBJ_DATA, and the C's constructors for them (recycle.c new_char, new_obj).

Fields keep the C names (``class`` is ``class_``; ``pIndexData`` is ``index``). The defaults are the C's: a new
character is new_char's, and a new object is all zeros, as new_obj leaves it. Lists the C threads through
next_content and similar are Python lists in the C's order, head first.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/recycle.c, src/merc.h. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from charm.data import constants as C
from charm.world.index import Affect, ExtraDescr, MobIndex, ObjIndex, Room


@dataclass(eq=False)
class Char:
    """CHAR_DATA, with new_char's defaults."""

    index: MobIndex | None = None  # pIndexData; None for a player
    name: str = ""
    short_descr: str = ""
    long_descr: str = ""
    description: str = ""
    prompt: str | None = ""
    prefix: str = ""
    material: str = ""
    id: int = 0
    version: int = 0
    group: int = 0
    clan: int = 0
    sex: int = 0
    class_: int = 0
    race: int = 0
    level: int = 0
    trust: int = 0
    played: int = 0
    lines: int = C.PAGELEN
    logon: int = 0
    timer: int = 0
    wait: int = 0
    daze: int = 0
    hit: int = 20
    max_hit: int = 20
    mana: int = 100
    max_mana: int = 100
    move: int = 100
    max_move: int = 100
    gold: int = 0
    silver: int = 0
    exp: int = 0
    act: int = 0
    comm: int = 0
    wiznet: int = 0
    imm_flags: int = 0
    res_flags: int = 0
    vuln_flags: int = 0
    invis_level: int = 0
    incog_level: int = 0
    affected_by: int = 0
    position: int = C.POS_STANDING
    practice: int = 0
    train: int = 0
    carry_weight: int = 0
    carry_number: int = 0
    saving_throw: int = 0
    alignment: int = 0
    hitroll: int = 0
    damroll: int = 0
    armor: list[int] = field(default_factory=lambda: [100] * 4)
    wimpy: int = 0
    perm_stat: list[int] = field(default_factory=lambda: [13] * C.MAX_STATS)
    mod_stat: list[int] = field(default_factory=lambda: [0] * C.MAX_STATS)
    form: int = 0
    parts: int = 0
    size: int = 0
    off_flags: int = 0
    damage: list[int] = field(default_factory=lambda: [0] * 3)
    dam_type: int = 0
    start_pos: int = 0
    default_pos: int = 0
    mprog_delay: int = 0
    spec_fun: str | None = None
    mprog_target: "Char | None" = None
    in_room: Room | None = None
    was_in_room: Room | None = None
    fighting: "Char | None" = None
    desc: object | None = None  # the connection (charm.net.descriptor.Descriptor); None for a mob or link-dead
    pcdata: "PCData | None" = None  # a player's; None for a mob
    gen_data: "GenData | None" = None  # while customising a new character
    pet: "Char | None" = None
    leader: "Char | None" = None
    master: "Char | None" = None
    on: "Obj | None" = None  # the furniture it's on
    valid: bool = True  # VALIDATE / INVALIDATE: free_char invalidates
    own_strings: set[str] = field(default_factory=set)  # a pet's strings that aren't its prototype's (see Obj)
    carrying: list["Obj"] = field(default_factory=list)  # head first
    affected: list[Affect] = field(default_factory=list)  # head first

    @property
    def is_npc(self) -> bool:
        """IS_NPC."""
        return bool(self.act & C.ACT_IS_NPC)


COLOUR_FIELDS = (
    "text", "auction", "auction_text", "gossip", "gossip_text", "music", "music_text", "question", "question_text",
    "answer", "answer_text", "quote", "quote_text", "immtalk_text", "immtalk_type", "info", "say", "say_text", "tell",
    "tell_text", "reply", "reply_text", "gtell_text", "gtell_type", "wiznet", "room_title", "room_text", "room_exits",
    "room_things", "prompt", "fight_death", "fight_yhit", "fight_ohit", "fight_thit", "fight_skill")


@dataclass(eq=False)
class PCData:
    """PC_DATA. Each colour setting is [bright, colour, beep], as the C's int field[3]."""

    pwd: str = ""
    bamfin: str = ""
    bamfout: str = ""
    title: str = ""
    perm_hit: int = 0
    perm_mana: int = 0
    perm_move: int = 0
    true_sex: int = 0
    last_level: int = 0
    condition: list[int] = field(default_factory=lambda: [0] * 4)
    learned: list[int] = field(default_factory=lambda: [0] * C.MAX_SKILL)
    group_known: list[bool] = field(default_factory=lambda: [False] * C.MAX_GROUP)
    points: int = 0
    confirm_delete: bool = False
    alias: list[str | None] = field(default_factory=lambda: [None] * C.MAX_ALIAS)
    alias_sub: list[str | None] = field(default_factory=lambda: [None] * C.MAX_ALIAS)
    board: int = 0  # an index into charm.data.boards.BOARDS (the C keeps a pointer)
    last_note: list[int] = field(default_factory=lambda: [0] * C.MAX_BOARD)
    in_progress: object | None = None
    security: int = 0
    colours: dict[str, list[int]] = field(default_factory=lambda: {f: [0, 0, 0] for f in COLOUR_FIELDS})

    def __getattr__(self, name):  # pcdata.prompt -> its colour triple, as colour() reads it
        colours = self.__dict__.get("colours")
        if colours is not None and name in colours:
            return colours[name]
        raise AttributeError(name)


@dataclass(eq=False)
class GenData:
    """GEN_DATA: what a new character has picked while customising."""

    skill_chosen: list[bool] = field(default_factory=lambda: [False] * C.MAX_SKILL)
    group_chosen: list[bool] = field(default_factory=lambda: [False] * C.MAX_GROUP)
    points_chosen: int = 0


@dataclass(eq=False)
class Obj:
    """OBJ_DATA, all zeros as new_obj leaves it."""

    index: ObjIndex | None = None  # pIndexData
    in_room: Room | None = None
    carried_by: Char | None = None
    in_obj: "Obj | None" = None
    on: "Obj | None" = None
    contains: list["Obj"] = field(default_factory=list)  # head first
    extra_descr: list[ExtraDescr] = field(default_factory=list)
    affected: list[Affect] = field(default_factory=list)  # head first
    enchanted: bool = False
    owner: str | None = None
    name: str = ""
    short_descr: str = ""
    description: str = ""
    item_type: int = 0
    extra_flags: int = 0
    wear_flags: int = 0
    wear_loc: int = 0
    weight: int = 0
    cost: int = 0
    level: int = 0
    condition: int = 0
    material: str = ""
    timer: int = 0
    value: list[int] = field(default_factory=lambda: [0] * 5)
    # Which strings are the object's own, not its prototype's: fwrite_obj writes Name, ShD and Desc when the C's
    # pointers differ, and a string read from a player file is always a new one, even with the same text.
    own_strings: set[str] = field(default_factory=set)


# C: recycle.c new_char
def new_char(current_time: int) -> Char:
    return Char(logon=current_time)


# C: recycle.c new_obj
def new_obj() -> Obj:
    return Obj()


# C: recycle.c new_pcdata
def new_pcdata() -> PCData:
    return PCData()


# C: recycle.c new_gen_data
def new_gen_data() -> GenData:
    return GenData()
