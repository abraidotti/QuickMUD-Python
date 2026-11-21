"""olc_act.c: what each editor's commands do. This PR has the shared helpers (?, version, the lists ? shows, the
vnum range checks) and the area editor (aedit_*); the room, object and mob editors come in the PRs after.

Every editor command takes (ch, argument) and returns True if it changed the area, which the editor then marks
AREA_CHANGED.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/olc_act.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.commands.interp import is_number, one_argument
from charm.core.strings import atoi, str_cmp, str_prefix, upper
from charm.data import constants as C
from charm.data import flags as F
from charm.data.attacks import ATTACK_TABLE
from charm.data.items import LIQ_TABLE
from charm.data.mobprogs import MPROG_FLAGS
from charm.data.skills import SKILL_TABLE
from charm.data.specials import SPEC_TABLE
from charm.net.output import page_to_char, send_to_char
from charm.olc.bits import flag_string

# olc.h
VERSION = "ILAB Online Creation [Beta 1.0, ROM 2.3 modified]\n\r     Port a ROM 2.4 v1.8\n\r"
AUTHOR = ("     By Jason(jdinkel@mines.colorado.edu)\n\r     Modified for use with ROM 2.3\n\r"
          "     By Hans Birkeland (hansbi@ifi.uio.no)\n\r     Modificado para uso en ROM 2.4b6\n\r"
          "     Por Ivan Toledo (itoledo@ctcreuna.cl)\n\r")
DATE = ("     (Apr. 7, 1995 - ROM mod, Apr 16, 1995)\n\r     (Port a ROM 2.4 - Nov 2, 1996)\n\r"
        "     Version actual : 1.8 - Sep 8, 1998\n\r")
CREDITS = "     Original by Surreality(cxw197@psu.edu) and Locke(locke@lm.com)"


def _game():
    from charm.entities import game as game_module

    return game_module.current


# C: olc_act.c show_version
def show_version(ch, argument: str) -> bool:
    for text in (VERSION, AUTHOR, DATE, CREDITS):
        send_to_char(text, ch)
        send_to_char("\n\r", ch)
    return False


# help_table: (command, structure, description); a structure is a flag table, or the name of another table
HELP_TABLE = (
    ("area", F.AREA_FLAGS, "Area attributes."), ("room", F.ROOM_FLAGS, "Room attributes."),
    ("sector", F.SECTOR_FLAGS, "Sector types, terrain."), ("exit", F.EXIT_FLAGS, "Exit types."),
    ("type", F.TYPE_FLAGS, "Types of objects."), ("extra", F.EXTRA_FLAGS, "Object attributes."),
    ("wear", F.WEAR_FLAGS, "Where to wear object."), ("spec", "spec_table", "Available special programs."),
    ("sex", F.SEX_FLAGS, "Sexes."), ("act", F.ACT_FLAGS, "Mobile attributes."),
    ("affect", F.AFFECT_FLAGS, "Mobile affects."), ("wear-loc", F.WEAR_LOC_FLAGS, "Where mobile wears object."),
    ("spells", "skill_table", "Names of current spells."), ("container", F.CONTAINER_FLAGS, "Container status."),
    # "ROM specific bits:"
    ("armor", F.AC_TYPE, "Ac for different attacks."), ("apply", F.APPLY_FLAGS, "Apply flags"),
    ("form", F.FORM_FLAGS, "Mobile body form."), ("part", F.PART_FLAGS, "Mobile body parts."),
    ("imm", F.IMM_FLAGS, "Mobile immunity."), ("res", F.RES_FLAGS, "Mobile resistance."),
    ("vuln", F.VULN_FLAGS, "Mobile vulnerability."), ("off", F.OFF_FLAGS, "Mobile offensive behaviour."),
    ("size", F.SIZE_FLAGS, "Mobile size."), ("position", F.POSITION_FLAGS, "Mobile positions."),
    ("wclass", F.WEAPON_CLASS, "Weapon class."), ("wtype", F.WEAPON_TYPE2, "Special weapon type."),
    ("portal", F.PORTAL_FLAGS, "Portal types."), ("furniture", F.FURNITURE_FLAGS, "Furniture types."),
    ("liquid", "liq_table", "Liquid types."), ("apptype", F.APPLY_TYPES, "Apply types."),
    ("weapon", "attack_table", "Weapon types."), ("mprog", MPROG_FLAGS, "MobProgram flags."),
)


def _columns(names, width: str, per_line: int) -> str:
    """The C's column loops: each name padded to width, a line break after every per_line, and one at the end
    if the last line isn't full."""
    out, col = [], 0
    for name in names:
        out.append(width % name)  # format: sprintf
        col += 1
        if col % per_line == 0:  # non-negative: a count
            out.append("\n\r")
    if col % per_line != 0:  # non-negative: a count
        out.append("\n\r")
    return "".join(out)


# C: olc_act.c show_flag_cmds
def show_flag_cmds(ch, flag_table) -> None:
    send_to_char(_columns([f.name for f in flag_table if f.settable], "%-19.18s", 4), ch)


# C: olc_act.c show_skill_cmds
def show_skill_cmds(ch, tar: int) -> None:
    names = []
    for skill in SKILL_TABLE:  # the C stops at the first unnamed row; the generated table ends before it
        if str_cmp(skill.name, "reserved") or skill.spell_fun == "spell_null":
            continue
        if tar == -1 or skill.target == tar:
            names.append(skill.name)
    send_to_char(_columns(names, "%-19.18s", 4), ch)


# C: olc_act.c show_spec_cmds
def show_spec_cmds(ch) -> None:
    send_to_char("Preceed special functions with 'spec_'\n\r\n\r", ch)
    send_to_char(_columns([s.name[5:] for s in SPEC_TABLE if s.function is not None], "%-19.18s", 4), ch)


# C: olc_act.c show_liqlist
def show_liqlist(ch) -> None:
    out = []
    for liq, t in enumerate(LIQ_TABLE):  # up to the NULL row, which the generated table leaves out
        if liq % 21 == 0:  # non-negative: an index
            out.append("Name                 Color          Proof Full Thirst Food Ssize\n\r")
        out.append("%-20s %-14s %5d %4d %6d %4d %5d\n\r" % ((t.liq_name, t.liq_color) + tuple(t.liq_affect[:5])))
    page_to_char("".join(out), ch)


# C: olc_act.c show_damlist
def show_damlist(ch) -> None:
    out = []
    for att, t in enumerate(ATTACK_TABLE):  # up to the NULL row, which the generated table leaves out
        if att % 21 == 0:  # non-negative: an index
            out.append("Name                 Noun\n\r")
        out.append("%-20s %-20s\n\r" % (t.name, t.noun))
    page_to_char("".join(out), ch)


# C: olc_act.c show_help
def show_help(ch, argument: str) -> bool:
    from charm.persist.player import capitalize

    argument, arg = one_argument(argument)
    _, spell = one_argument(argument)
    if arg == "":  # "Display syntax."
        send_to_char("Syntax:  ? [command]\n\r\n\r", ch)
        send_to_char("[command]  [description]\n\r", ch)
        for command, _, desc in HELP_TABLE:
            send_to_char("%-10.10s -%s\n\r" % (capitalize(command), desc), ch)
        return False
    for command, structure, _ in HELP_TABLE:  # "Find the command, show changeable data."
        if arg[0] == command[0] and str_prefix(arg, command):
            if structure == "spec_table":
                show_spec_cmds(ch)
            elif structure == "liq_table":
                show_liqlist(ch)
            elif structure == "attack_table":
                show_damlist(ch)
            elif structure == "skill_table":
                if spell == "":
                    send_to_char("Syntax:  ? spells [ignore/attack/defend/self/object/all]\n\r", ch)
                    return False
                for word, tar in (("all", -1), ("ignore", C.TAR_IGNORE), ("attack", C.TAR_CHAR_OFFENSIVE),
                                  ("defend", C.TAR_CHAR_DEFENSIVE), ("self", C.TAR_CHAR_SELF),
                                  ("object", C.TAR_OBJ_INV)):
                    if str_prefix(spell, word):
                        show_skill_cmds(ch, tar)
                        break
                else:
                    send_to_char("Syntax:  ? spell [ignore/attack/defend/self/object/all]\n\r", ch)
            else:
                show_flag_cmds(ch, structure)
            return False
    show_help(ch, "")
    return False


# C: olc_act.c check_range
def check_range(lower: int, upper_: int) -> bool:
    """False if more than one area has an end of its range inside lower..upper."""
    cnt = 0
    for area in _game().index.areas:
        if lower <= area.min_vnum <= upper_ or lower <= area.max_vnum <= upper_:
            cnt += 1
        if cnt > 1:
            return False
    return True


# C: olc_act.c get_vnum_area
def get_vnum_area(vnum: int):
    return next((a for a in _game().index.areas if a.min_vnum <= vnum <= a.max_vnum), None)


def _area(ch):
    """EDIT_AREA: the area being edited."""
    return ch.desc.pEdit


# C: olc_act.c aedit_show
def aedit_show(ch, argument: str) -> bool:
    from charm.olc.save import _s

    area = _area(ch)
    send_to_char("Name:     [%5d] %s\n\r" % (area.vnum, _s(area.name)), ch)
    send_to_char("File:     %s\n\r" % _s(area.file_name), ch)
    send_to_char("Vnums:    [%d-%d]\n\r" % (area.min_vnum, area.max_vnum), ch)
    send_to_char("Age:      [%d]\n\r" % area.age, ch)
    send_to_char("Players:  [%d]\n\r" % area.nplayer, ch)
    send_to_char("Security: [%d]\n\r" % area.security, ch)
    send_to_char("Builders: [%s]\n\r" % _s(area.builders), ch)
    send_to_char("Credits : [%s]\n\r" % _s(area.credits), ch)
    send_to_char("Flags:    [%s]\n\r" % flag_string(F.AREA_FLAGS, area.area_flags), ch)
    return False


# C: olc_act.c aedit_reset
def aedit_reset(ch, argument: str) -> bool:
    from charm.entities.resets import reset_area

    reset_area(_game(), _area(ch))
    send_to_char("Area reset.\n\r", ch)
    return False


# C: olc_act.c aedit_create
def aedit_create(ch, argument: str) -> bool:
    from charm.olc.mem import new_area

    game = _game()
    area = new_area(game)
    game.index.areas.append(area)  # area_last->next = pArea
    ch.desc.pEdit = area
    area.area_flags |= C.AREA_ADDED
    send_to_char("Area Created.\n\r", ch)
    return False


# C: olc_act.c aedit_name
def aedit_name(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:   name [$name]\n\r", ch)
        return False
    _area(ch).name = argument
    send_to_char("Name set.\n\r", ch)
    return True


# C: olc_act.c aedit_credits
def aedit_credits(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:   credits [$credits]\n\r", ch)
        return False
    _area(ch).credits = argument
    send_to_char("Credits set.\n\r", ch)
    return True


def _isalnum(c: str) -> bool:
    return c.isascii() and c.isalnum()


# C: olc_act.c aedit_file
def aedit_file(ch, argument: str) -> bool:
    """The check counts the whole argument's length but looks at the first word (lower-cased), so a second word, a
    trailing space or a quote finds the end of the word and is refused as not a letter or number."""
    _, file = one_argument(argument)  # "Forces Lowercase"
    if argument == "":
        send_to_char("Syntax:  filename [$file]\n\r", ch)
        return False
    length = len(argument)
    if length > 8:
        send_to_char("No more than eight characters allowed.\n\r", ch)
        return False
    for i in range(length):  # "Allow only letters and numbers."
        if not _isalnum(file[i] if i < len(file) else "\0"):
            send_to_char("Only letters and numbers are valid.\n\r", ch)
            return False
    _area(ch).file_name = file + ".are"
    send_to_char("Filename set.\n\r", ch)
    return True


# C: olc_act.c aedit_age
def aedit_age(ch, argument: str) -> bool:
    _, age = one_argument(argument)
    if not is_number(age) or age == "":
        send_to_char("Syntax:  age [#xage]\n\r", ch)
        return False
    _area(ch).age = atoi(age)
    send_to_char("Age set.\n\r", ch)
    return True


# C: olc_act.c aedit_security
def aedit_security(ch, argument: str) -> bool:
    _, sec = one_argument(argument)
    if not is_number(sec) or sec == "":
        send_to_char("Syntax:  security [#xlevel]\n\r", ch)
        return False
    value = atoi(sec)
    if value > ch.pcdata.security or value < 0:
        if ch.pcdata.security != 0:
            send_to_char("Security is 0-%d.\n\r" % ch.pcdata.security, ch)
        else:
            send_to_char("Security is 0 only.\n\r", ch)
        return False
    _area(ch).security = value
    send_to_char("Security set.\n\r", ch)
    return True


# C: olc_act.c aedit_builder
def aedit_builder(ch, argument: str) -> bool:
    """A name found anywhere in the builders (strstr, so "Del" finds "Delver") is taken out; one that isn't is
    added, and the list's words capitalised. "Builder added." is followed by the list, with no line end."""
    from charm.olc.strings import string_proper, string_replace, string_unpad

    area = _area(ch)
    _, name = one_argument(argument)
    if name == "":
        send_to_char("Syntax:  builder [$name]  -toggles builder\n\r", ch)
        send_to_char("Syntax:  builder All      -allows everyone\n\r", ch)
        return False
    name = upper(name[0]) + name[1:]
    if name in area.builders:
        area.builders = string_unpad(string_replace(area.builders, name, ""))
        if area.builders == "":
            area.builders = "None"
        send_to_char("Builder removed.\n\r", ch)
        return True
    buf = ""
    if "None" in area.builders:
        area.builders = string_unpad(string_replace(area.builders, "None", ""))
    if area.builders != "":
        buf += area.builders + " "
    buf += name
    area.builders = string_proper(buf)
    send_to_char("Builder added.\n\r", ch)
    send_to_char(area.builders, ch)
    return True


def _range_refused(ch, area, lower: int, upper_: int) -> bool:
    if not check_range(lower, upper_):
        send_to_char("AEdit:  Range must include only this area.\n\r", ch)
        return True
    return False


# C: olc_act.c aedit_vnum
def aedit_vnum(ch, argument: str) -> bool:
    area = _area(ch)
    argument, lower = one_argument(argument)
    _, upper_ = one_argument(argument)
    if not is_number(lower) or lower == "" or not is_number(upper_) or upper_ == "":
        send_to_char("Syntax:  vnum [#xlower] [#xupper]\n\r", ch)
        return False
    ilower, iupper = atoi(lower), atoi(upper_)
    if ilower > iupper:
        send_to_char("AEdit:  Upper must be larger then lower.\n\r", ch)
        return False
    if _range_refused(ch, area, ilower, iupper):
        return False
    owner = get_vnum_area(ilower)
    if owner is not None and owner is not area:
        send_to_char("AEdit:  Lower vnum already assigned.\n\r", ch)
        return False
    area.min_vnum = ilower
    send_to_char("Lower vnum set.\n\r", ch)
    owner = get_vnum_area(iupper)
    if owner is not None and owner is not area:
        send_to_char("AEdit:  Upper vnum already assigned.\n\r", ch)
        return True  # "The lower value has been set."
    area.max_vnum = iupper
    send_to_char("Upper vnum set.\n\r", ch)
    return True


# C: olc_act.c aedit_lvnum
def aedit_lvnum(ch, argument: str) -> bool:
    area = _area(ch)
    _, lower = one_argument(argument)
    if not is_number(lower) or lower == "":
        send_to_char("Syntax:  min_vnum [#xlower]\n\r", ch)
        return False
    ilower, iupper = atoi(lower), area.max_vnum
    if ilower > iupper:
        send_to_char("AEdit:  Value must be less than the max_vnum.\n\r", ch)
        return False
    if _range_refused(ch, area, ilower, iupper):
        return False
    owner = get_vnum_area(ilower)
    if owner is not None and owner is not area:
        send_to_char("AEdit:  Lower vnum already assigned.\n\r", ch)
        return False
    area.min_vnum = ilower
    send_to_char("Lower vnum set.\n\r", ch)
    return True


# C: olc_act.c aedit_uvnum
def aedit_uvnum(ch, argument: str) -> bool:
    area = _area(ch)
    _, upper_ = one_argument(argument)
    if not is_number(upper_) or upper_ == "":
        send_to_char("Syntax:  max_vnum [#xupper]\n\r", ch)
        return False
    ilower, iupper = area.min_vnum, atoi(upper_)
    if ilower > iupper:
        send_to_char("AEdit:  Upper must be larger then lower.\n\r", ch)
        return False
    if _range_refused(ch, area, ilower, iupper):
        return False
    owner = get_vnum_area(iupper)
    if owner is not None and owner is not area:
        send_to_char("AEdit:  Upper vnum already assigned.\n\r", ch)
        return False
    area.max_vnum = iupper
    send_to_char("Upper vnum set.\n\r", ch)
    return True
