"""The C game's table structs, as frozen dataclasses with the C field names.

Generated from the C by quickmud_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

A field that points to a function or a variable (a spec_fun, a gsn) holds its C name as a string until that code is
ported.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/merc.h. Licence terms: README.md#licence-terms and doc/.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemType:
    """struct item_type"""

    type: int  # C: int
    name: str | None  # C: char *


@dataclass(frozen=True)
class WeaponType:
    """struct weapon_type"""

    name: str | None  # C: char *
    vnum: int  # C: sh_int
    type: int  # C: sh_int
    gsn: str | None  # C: sh_int *


@dataclass(frozen=True)
class LiqType:
    """struct liq_type"""

    liq_name: str | None  # C: char *
    liq_color: str | None  # C: char *
    liq_affect: tuple[int, ...]  # C: sh_int [5]


@dataclass(frozen=True)
class RaceType:
    """struct race_type"""

    name: str | None  # C: char *
    pc_race: bool  # C: bool
    act: int  # C: long
    aff: int  # C: long
    off: int  # C: long
    imm: int  # C: long
    res: int  # C: long
    vuln: int  # C: long
    form: int  # C: long
    parts: int  # C: long


@dataclass(frozen=True)
class SizeType:
    """struct size_type"""

    name: str | None  # C: char *


@dataclass(frozen=True)
class FlagType:
    """struct flag_type"""

    name: str | None  # C: char *
    bit: int  # C: int
    settable: bool  # C: bool


@dataclass(frozen=True)
class ClanType:
    """struct clan_type"""

    name: str | None  # C: char *
    who_name: str | None  # C: char *
    hall: int  # C: sh_int
    independent: bool  # C: bool


@dataclass(frozen=True)
class SpecType:
    """struct spec_type"""

    name: str | None  # C: char *
    function: str | None  # C: SPEC_FUN *


@dataclass(frozen=True)
class SkillType:
    """struct skill_type"""

    name: str | None  # C: char *
    skill_level: tuple[int, ...]  # C: sh_int [4]
    rating: tuple[int, ...]  # C: sh_int [4]
    spell_fun: str | None  # C: SPELL_FUN *
    target: int  # C: sh_int
    minimum_position: int  # C: sh_int
    pgsn: str | None  # C: sh_int *
    slot: int  # C: sh_int
    min_mana: int  # C: sh_int
    beats: int  # C: sh_int
    noun_damage: str | None  # C: char *
    msg_off: str | None  # C: char *
    msg_obj: str | None  # C: char *


@dataclass(frozen=True)
class AttackType:
    """struct attack_type"""

    name: str | None  # C: char *
    noun: str | None  # C: char *
    damage: int  # C: int


@dataclass(frozen=True)
class PositionType:
    """struct position_type"""

    name: str | None  # C: char *
    short_name: str | None  # C: char *


@dataclass(frozen=True)
class SexType:
    """struct sex_type"""

    name: str | None  # C: char *


@dataclass(frozen=True)
class WiznetType:
    """struct wiznet_type"""

    name: str | None  # C: char *
    flag: int  # C: long
    level: int  # C: int


@dataclass(frozen=True)
class PcRaceType:
    """struct pc_race_type"""

    name: str | None  # C: char *
    who_name: str | None  # C: char [6]
    points: int  # C: sh_int
    class_mult: tuple[int, ...]  # C: sh_int [4]
    skills: tuple[str, ...]  # C: char * [5]
    stats: tuple[int, ...]  # C: sh_int [5]
    max_stats: tuple[int, ...]  # C: sh_int [5]
    size: int  # C: sh_int


@dataclass(frozen=True)
class ClassType:
    """struct class_type"""

    name: str | None  # C: char *
    who_name: str | None  # C: char [4]
    attr_prime: int  # C: sh_int
    weapon: int  # C: sh_int
    guild: tuple[int, ...]  # C: sh_int [2]
    skill_adept: int  # C: sh_int
    thac0_00: int  # C: sh_int
    thac0_32: int  # C: sh_int
    hp_min: int  # C: sh_int
    hp_max: int  # C: sh_int
    fMana: bool  # C: bool
    base_group: str | None  # C: char *
    default_group: str | None  # C: char *


@dataclass(frozen=True)
class GroupType:
    """struct group_type"""

    name: str | None  # C: char *
    rating: tuple[int, ...]  # C: sh_int [4]
    spells: tuple[str, ...]  # C: char * [15]


@dataclass(frozen=True)
class StrAppType:
    """struct str_app_type"""

    tohit: int  # C: sh_int
    todam: int  # C: sh_int
    carry: int  # C: sh_int
    wield: int  # C: sh_int


@dataclass(frozen=True)
class IntAppType:
    """struct int_app_type"""

    learn: int  # C: sh_int


@dataclass(frozen=True)
class WisAppType:
    """struct wis_app_type"""

    practice: int  # C: sh_int


@dataclass(frozen=True)
class DexAppType:
    """struct dex_app_type"""

    defensive: int  # C: sh_int


@dataclass(frozen=True)
class ConAppType:
    """struct con_app_type"""

    hitp: int  # C: sh_int
    shock: int  # C: sh_int


@dataclass(frozen=True)
class BoardData:
    """struct board_data"""

    short_name: str | None  # C: char *
    long_name: str | None  # C: char *
    read_level: int  # C: int
    write_level: int  # C: int
    names: str | None  # C: char *
    force_type: int  # C: int
    purge_days: int  # C: int
    note_first: str | None  # C: NOTE_DATA *
    changed: bool  # C: bool


@dataclass(frozen=True)
class CmdType:
    """struct cmd_type"""

    name: str | None  # C: char *
    do_fun: str | None  # C: DO_FUN *
    position: int  # C: sh_int
    level: int  # C: sh_int
    log: int  # C: sh_int
    show: int  # C: sh_int
