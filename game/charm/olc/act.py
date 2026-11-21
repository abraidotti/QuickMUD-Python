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


# -- the room editor (REDIT): every command edits the room the builder stands in (EDIT_ROOM is ch->in_room) --


def _room(ch):
    return ch.in_room


def _list(ch, protos, header_found: str, show) -> bool:
    """rlist, mlist and olist's loop: three to a line, "[vnum] name" each, paged."""
    from charm.persist.player import capitalize

    out, col = [], 0
    for p in protos:
        out.append("[%5d] %-17.16s" % (p.vnum, capitalize(show(p))))
        col += 1
        if col % 3 == 0:  # non-negative: a count
            out.append("\n\r")
    if col == 0:
        send_to_char(header_found, ch)
        return False
    if col % 3 != 0:  # non-negative: a count
        out.append("\n\r")
    page_to_char("".join(out), ch)
    return False


def _in_area(ch, get):
    area = ch.in_room.area
    for vnum in range(area.min_vnum, area.max_vnum + 1):
        p = get(vnum)
        if p is not None:
            yield p


# C: olc_act.c redit_rlist
def redit_rlist(ch, argument: str) -> bool:
    index = _game().index
    return _list(ch, list(_in_area(ch, index.get_room_index)), "Room(s) not found in this area.\n\r",
                 lambda r: r.name)


# C: olc_act.c redit_mlist
def redit_mlist(ch, argument: str) -> bool:
    from charm.entities.handler import is_name

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:  mlist <all/name>\n\r", ch)
        return False
    index = _game().index
    every = str_cmp(arg, "all")
    found = [p for p in _in_area(ch, index.get_mob_index) if every or is_name(arg, p.player_name)]
    return _list(ch, found, "Mobile(s) not found in this area.\n\r", lambda p: p.short_descr)


# C: olc_act.c redit_olist
def redit_olist(ch, argument: str) -> bool:
    from charm.entities.handler import is_name
    from charm.olc.bits import flag_value

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:  olist <all/name/item_type>\n\r", ch)
        return False
    index = _game().index
    every = str_cmp(arg, "all")
    found = [p for p in _in_area(ch, index.get_obj_index)
             if every or is_name(arg, p.name) or flag_value(F.TYPE_FLAGS, arg) == p.item_type]
    return _list(ch, found, "Object(s) not found in this area.\n\r", lambda p: p.short_descr)


def _show_proto(ch, argument: str, get, what: str, show_name: str) -> bool:
    from charm.core.errors import NotPorted

    if argument == "":
        send_to_char("Syntax:  %sshow <vnum>\n\r" % what[0], ch)
        return False
    if not is_number(argument):
        send_to_char("REdit: Must be a number.\n\r", ch)
        return False
    if get(atoi(argument)) is None:
        send_to_char("REdit:  That %s does not exist.\n\r" % what, ch)
        return False
    raise NotPorted(f"olc_act.c {show_name}")


# C: olc_act.c redit_mshow [partial]
def redit_mshow(ch, argument: str) -> bool:
    """[partial]: a mob that exists is shown by medit_show, which raises NotPorted until the mob editor (PR 4)."""
    return _show_proto(ch, argument, _game().index.get_mob_index, "mobile", "medit_show")


# C: olc_act.c redit_oshow [partial]
def redit_oshow(ch, argument: str) -> bool:
    """[partial]: an object that exists is shown by oedit_show, which raises NotPorted until the object editor."""
    return _show_proto(ch, argument, _game().index.get_obj_index, "object", "oedit_show")


def _first_words(names) -> str:
    """The first word of each name (one_argument: lower-cased), space-separated, then "]", or "none]"."""
    words = [one_argument(n)[1] for n in names]
    return (" ".join(words) + "]" if words else "none]") + "\n\r"


# C: olc_act.c redit_show
def redit_show(ch, argument: str) -> bool:
    from charm.commands.move import DIR_NAME
    from charm.core.strings import str_infix
    from charm.data.clans import CLAN_TABLE
    from charm.olc.save import _s
    from charm.persist.player import capitalize

    room = _room(ch)
    out = ["Description:\n\r%s" % _s(room.description),
           "Name:       [%s]\n\rArea:       [%5d] %s\n\r" % (_s(room.name), room.area.vnum, _s(room.area.name)),
           "Vnum:       [%5d]\n\rSector:     [%s]\n\r" % (room.vnum, flag_string(F.SECTOR_FLAGS, room.sector_type)),
           "Room flags: [%s]\n\r" % flag_string(F.ROOM_FLAGS, room.room_flags)]
    if room.heal_rate != 100 or room.mana_rate != 100:
        out.append("Health rec: [%d]\n\rMana rec  : [%d]\n\r" % (room.heal_rate, room.mana_rate))
    if room.clan > 0:
        out.append("Clan      : [%d] %s\n\r" % (room.clan, CLAN_TABLE[room.clan].name))
    if room.owner:
        out.append("Owner     : [%s]\n\r" % room.owner)
    if room.extra_descr:
        out.append("Desc Kwds:  [" + " ".join(ed.keyword for ed in room.extra_descr) + "]\n\r")
    out.append("Characters: [" + _first_words(rch.name for rch in room.people))
    out.append("Objects:    [" + _first_words(obj.name for obj in room.contents))
    for door in range(C.MAX_DIR):
        ex = room.exit[door]
        if ex is None:
            continue
        out.append("-%-5s to [%5d] Key: [%5d] " % (capitalize(DIR_NAME[door]),
                                                  ex.to_room.vnum if ex.to_room is not None else 0, ex.key))
        # "Capitalize all flags that are not part of the reset info."
        reset_state = flag_string(F.EXIT_FLAGS, ex.rs_flags)
        words = flag_string(F.EXIT_FLAGS, ex.exit_info).split()
        out.append(" Exit flags: [" + " ".join(w if str_infix(w, reset_state) else upper(w) for w in words)
                   + "]\n\r")
        if ex.keyword:
            out.append("Kwds: [%s]\n\r" % ex.keyword)
        if ex.description:
            out.append(ex.description)
    send_to_char("".join(out), ch)
    return False


def _no_room_beyond(what: str):
    from charm.core.errors import CWouldCrash

    return CWouldCrash(f"olc_act.c change_exit: {what} an exit that leads nowhere (pToRoom is NULL)")


# C: olc_act.c change_exit
def change_exit(ch, argument: str, door: int) -> bool:
    """[direction] with flags, or delete, link, dig, room, key, name or desc; nothing moves that way. Exit flags
    are looked for in the whole line first, so a word like "door" anywhere in it toggles that flag instead."""
    from charm.commands.info import do_help
    from charm.commands.move import REV_DIR, move_char
    from charm.entities.handler import is_builder
    from charm.olc.bits import flag_value
    from charm.olc.mem import new_exit
    from charm.olc.strings import string_append

    index = _game().index
    room = _room(ch)
    value = flag_value(F.EXIT_FLAGS, argument)  # "Set the exit flags, needs full argument."
    if value != C.NO_FLAG:
        ex = room.exit[door]
        if ex is None:
            send_to_char("Exit doesn't exist.\n\r", ch)
            return False
        ex.rs_flags ^= value
        ex.exit_info = ex.rs_flags  # "Don't toggle exit_info because it can be changed by players."
        to_room = ex.to_room
        if to_room is None:
            raise _no_room_beyond("toggling a flag on")
        back = to_room.exit[REV_DIR[door]]
        if back is not None:
            back.rs_flags, back.exit_info = ex.rs_flags, ex.exit_info
        send_to_char("Exit flag toggled.\n\r", ch)
        return True

    argument, command = one_argument(argument)
    _, arg = one_argument(argument)
    if command == "" and argument == "":  # "Move command."
        move_char(ch, door, True)
        return False
    if command[0] == "?":
        do_help(ch, "EXIT")
        return False
    if str_cmp(command, "delete"):
        ex = room.exit[door]
        if ex is None:
            send_to_char("REdit:  Cannot delete a null exit.\n\r", ch)
            return False
        rev, to_room = REV_DIR[door], ex.to_room
        if to_room is None:
            raise _no_room_beyond("deleting")
        if to_room.exit[rev] is not None:  # "Remove ToRoom Exit."
            to_room.exit[rev] = None
        room.exit[door] = None  # "Remove this exit."
        send_to_char("Exit unlinked.\n\r", ch)
        return True
    if str_cmp(command, "link"):
        if arg == "" or not is_number(arg):
            send_to_char("Syntax:  [direction] link [vnum]\n\r", ch)
            return False
        to_room = index.get_room_index(atoi(arg))
        if to_room is None:
            send_to_char("REdit:  Cannot link to non-existant room.\n\r", ch)
            return False
        if not is_builder(ch, to_room.area):
            send_to_char("REdit:  Cannot link to that area.\n\r", ch)
            return False
        if to_room.exit[REV_DIR[door]] is not None:
            send_to_char("REdit:  Remote side's exit already exists.\n\r", ch)
            return False
        if room.exit[door] is None:
            room.exit[door] = new_exit()
        room.exit[door].to_room, room.exit[door].orig_door = to_room, door
        door = REV_DIR[door]
        back = new_exit()
        back.to_room, back.orig_door = room, door
        to_room.exit[door] = back
        send_to_char("Two-way link established.\n\r", ch)
        return True
    if str_cmp(command, "dig"):
        if arg == "" or not is_number(arg):
            send_to_char("Syntax: [direction] dig <vnum>\n\r", ch)
            return False
        redit_create(ch, arg)
        change_exit(ch, "link %s" % arg, door)
        return True
    if str_cmp(command, "room"):
        if arg == "" or not is_number(arg):
            send_to_char("Syntax:  [direction] room [vnum]\n\r", ch)
            return False
        to_room = index.get_room_index(atoi(arg))
        if to_room is None:
            send_to_char("REdit:  Cannot link to non-existant room.\n\r", ch)
            return False
        if room.exit[door] is None:
            room.exit[door] = new_exit()
        room.exit[door].to_room, room.exit[door].orig_door = to_room, door
        send_to_char("One-way link established.\n\r", ch)
        return True
    if str_cmp(command, "key"):
        if arg == "" or not is_number(arg):
            send_to_char("Syntax:  [direction] key [vnum]\n\r", ch)
            return False
        if room.exit[door] is None:
            send_to_char("Exit doesn't exist.\n\r", ch)
            return False
        key = index.get_obj_index(atoi(arg))
        if key is None:
            send_to_char("REdit:  Key doesn't exist.\n\r", ch)
            return False
        if key.item_type != C.ITEM_KEY:
            send_to_char("REdit:  Object is not a key.\n\r", ch)
            return False
        room.exit[door].key = atoi(arg)
        send_to_char("Exit key set.\n\r", ch)
        return True
    if str_cmp(command, "name"):
        if arg == "":
            send_to_char("Syntax:  [direction] name [string]\n\r", ch)
            send_to_char("         [direction] name none\n\r", ch)
            return False
        if room.exit[door] is None:
            send_to_char("Exit doesn't exist.\n\r", ch)
            return False
        room.exit[door].keyword = "" if str_cmp(arg, "none") else arg
        send_to_char("Exit name set.\n\r", ch)
        return True
    if str_prefix(command, "description"):
        if arg == "":
            if room.exit[door] is None:
                send_to_char("Exit doesn't exist.\n\r", ch)
                return False
            string_append(ch, (room.exit[door], "description"))
            return True
        send_to_char("Syntax:  [direction] desc\n\r", ch)
        return False
    return False


# C: olc_act.c redit_north
def redit_north(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_NORTH)


# C: olc_act.c redit_south
def redit_south(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_SOUTH)


# C: olc_act.c redit_east
def redit_east(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_EAST)


# C: olc_act.c redit_west
def redit_west(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_WEST)


# C: olc_act.c redit_up
def redit_up(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_UP)


# C: olc_act.c redit_down
def redit_down(ch, argument: str) -> bool:
    return change_exit(ch, argument, C.DIR_DOWN)


def _find_ed(room, keyword: str):
    from charm.entities.handler import is_name

    return next((ed for ed in room.extra_descr if is_name(keyword, ed.keyword)), None)


# C: olc_act.c redit_ed
def redit_ed(ch, argument: str) -> bool:
    from charm.olc.mem import new_extra_descr
    from charm.olc.strings import format_string, string_append

    room = _room(ch)
    argument, command = one_argument(argument)
    _, keyword = one_argument(argument)
    if command == "" or keyword == "":
        send_to_char("Syntax:  ed add [keyword]\n\r", ch)
        send_to_char("         ed edit [keyword]\n\r", ch)
        send_to_char("         ed delete [keyword]\n\r", ch)
        send_to_char("         ed format [keyword]\n\r", ch)
        return False
    if str_cmp(command, "add"):
        ed = new_extra_descr()
        ed.keyword = keyword
        room.extra_descr.insert(0, ed)
        string_append(ch, (ed, "description"))
        return True
    if str_cmp(command, "edit"):
        ed = _find_ed(room, keyword)
        if ed is None:
            send_to_char("REdit:  Extra description keyword not found.\n\r", ch)
            return False
        string_append(ch, (ed, "description"))
        return True
    if str_cmp(command, "delete"):
        ed = _find_ed(room, keyword)
        if ed is None:
            send_to_char("REdit:  Extra description keyword not found.\n\r", ch)
            return False
        room.extra_descr.remove(ed)
        send_to_char("Extra description deleted.\n\r", ch)
        return True
    if str_cmp(command, "format"):
        ed = _find_ed(room, keyword)
        if ed is None:
            send_to_char("REdit:  Extra description keyword not found.\n\r", ch)
            return False
        ed.description = format_string(ed.description)
        send_to_char("Extra description formatted.\n\r", ch)
        return True
    redit_ed(ch, "")
    return False


# C: olc_act.c redit_create
def redit_create(ch, argument: str) -> bool:
    """A new room at the vnum given, in the area whose range has it. It's made the connection's pEdit, but the
    room editor edits the room the builder stands in, so edit room create moves the builder there. (top_vnum_room,
    which this raises, is read by nothing.)"""
    from charm.entities.handler import is_builder
    from charm.olc.mem import new_room_index

    index = _game().index
    value = atoi(argument)
    if argument == "" or value <= 0:
        send_to_char("Syntax:  create [vnum > 0]\n\r", ch)
        return False
    area = get_vnum_area(value)
    if area is None:
        send_to_char("REdit:  That vnum is not assigned an area.\n\r", ch)
        return False
    if not is_builder(ch, area):
        send_to_char("REdit:  Vnum in an area you cannot build in.\n\r", ch)
        return False
    if index.get_room_index(value) is not None:
        send_to_char("REdit:  Room vnum already exists.\n\r", ch)
        return False
    room = new_room_index()
    room.area, room.vnum = area, value
    index.rooms[value] = room  # the head of its hash chain: the newest
    ch.desc.pEdit = room
    send_to_char("Room created.\n\r", ch)
    return True


# C: olc_act.c redit_name
def redit_name(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  name [name]\n\r", ch)
        return False
    _room(ch).name = argument
    send_to_char("Name set.\n\r", ch)
    return True


# C: olc_act.c redit_desc
def redit_desc(ch, argument: str) -> bool:
    from charm.olc.strings import string_append

    if argument == "":
        string_append(ch, (_room(ch), "description"))
        return True
    send_to_char("Syntax:  desc\n\r", ch)
    return False


# C: olc_act.c redit_heal
def redit_heal(ch, argument: str) -> bool:
    if is_number(argument):
        _room(ch).heal_rate = atoi(argument)
        send_to_char("Heal rate set.\n\r", ch)
        return True
    send_to_char("Syntax: heal <#xnumber>\n\r", ch)
    return False


# C: olc_act.c redit_mana
def redit_mana(ch, argument: str) -> bool:
    if is_number(argument):
        _room(ch).mana_rate = atoi(argument)
        send_to_char("Mana rate set.\n\r", ch)
        return True
    send_to_char("Syntax: mana <#xnumber>\n\r", ch)
    return False


# C: olc_act.c redit_clan
def redit_clan(ch, argument: str) -> bool:
    from charm.world.lookup import clan_lookup

    _room(ch).clan = clan_lookup(argument)
    send_to_char("Clan set.\n\r", ch)
    return True


# C: olc_act.c redit_format
def redit_format(ch, argument: str) -> bool:
    from charm.olc.strings import format_string

    room = _room(ch)
    room.description = format_string(room.description)
    send_to_char("String formatted.\n\r", ch)
    return True


# C: olc_act.c redit_mreset
def redit_mreset(ch, argument: str) -> bool:
    from charm.entities.create import create_mobile
    from charm.entities.handler import char_to_room
    from charm.net.act import act
    from charm.olc.mem import new_reset_data
    from charm.olc.olc import add_reset
    from charm.persist.player import capitalize

    game = _game()
    room = _room(ch)
    argument, arg = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg == "" or not is_number(arg):
        send_to_char("Syntax:  mreset <vnum> <max #x> <mix #x>\n\r", ch)
        return False
    p = game.index.get_mob_index(atoi(arg))
    if p is None:
        send_to_char("REdit: No mobile has that vnum.\n\r", ch)
        return False
    if p.area is not room.area:
        send_to_char("REdit: No such mobile in this area.\n\r", ch)
        return False
    rs = new_reset_data()  # "Create the mobile reset."
    rs.command, rs.arg1 = "M", p.vnum
    rs.arg2 = atoi(arg2) if is_number(arg2) else 1  # MAX_MOB
    rs.arg3 = room.vnum
    rs.arg4 = atoi(argument) if is_number(argument) else 1
    add_reset(room, rs, 0)  # "Last slot"
    newmob = create_mobile(game, p)  # "Create the mobile."
    char_to_room(newmob, room)
    send_to_char("%s (%d) has been loaded and added to resets.\n\rThere will be a maximum of %d loaded to this "
                 "room.\n\r" % (capitalize(p.short_descr), p.vnum, rs.arg2), ch)
    act("$n has created $N!", ch, None, newmob, C.TO_ROOM)
    return True


# wear_table: (wear_loc, the wear flag an object needs for it); a light needs ITEM_LIGHT, the item type (1), which
# is ITEM_TAKE's bit
WEAR_TABLE = ((C.WEAR_NONE, C.ITEM_TAKE), (C.WEAR_LIGHT, C.ITEM_LIGHT), (C.WEAR_FINGER_L, C.ITEM_WEAR_FINGER),
              (C.WEAR_FINGER_R, C.ITEM_WEAR_FINGER), (C.WEAR_NECK_1, C.ITEM_WEAR_NECK),
              (C.WEAR_NECK_2, C.ITEM_WEAR_NECK), (C.WEAR_BODY, C.ITEM_WEAR_BODY), (C.WEAR_HEAD, C.ITEM_WEAR_HEAD),
              (C.WEAR_LEGS, C.ITEM_WEAR_LEGS), (C.WEAR_FEET, C.ITEM_WEAR_FEET), (C.WEAR_HANDS, C.ITEM_WEAR_HANDS),
              (C.WEAR_ARMS, C.ITEM_WEAR_ARMS), (C.WEAR_SHIELD, C.ITEM_WEAR_SHIELD),
              (C.WEAR_ABOUT, C.ITEM_WEAR_ABOUT), (C.WEAR_WAIST, C.ITEM_WEAR_WAIST),
              (C.WEAR_WRIST_L, C.ITEM_WEAR_WRIST), (C.WEAR_WRIST_R, C.ITEM_WEAR_WRIST), (C.WEAR_WIELD, C.ITEM_WIELD),
              (C.WEAR_HOLD, C.ITEM_HOLD))


# C: olc_act.c wear_bit
def wear_bit(loc: int) -> int:
    return next((bit for wear_loc, bit in WEAR_TABLE if wear_loc == loc), 0)


_SHOP_LEVELS = {C.ITEM_PILL: (0, 10), C.ITEM_POTION: (0, 10), C.ITEM_SCROLL: (5, 15), C.ITEM_WAND: (10, 20),
                C.ITEM_STAFF: (15, 25), C.ITEM_ARMOR: (5, 15)}


# C: olc_act.c redit_oreset
def redit_oreset(ch, argument: str) -> bool:
    """An object reset: into the room, into an object here, or onto a mob here at a wear location. For a mob the C
    makes the object twice; the first one is left in the object list, never placed (#96). It reads the target's
    prototype, so a player as the target crashes it."""
    from charm.core.errors import CWouldCrash
    from charm.core.rng import number_fuzzy, number_range
    from charm.entities.create import create_object
    from charm.entities.handler import equip_char, get_char_room, get_eq_char, get_obj_list, obj_to_char, \
        obj_to_obj, obj_to_room
    from charm.net.act import act
    from charm.olc.bits import flag_value
    from charm.olc.mem import new_reset_data
    from charm.olc.olc import add_reset
    from charm.persist.player import capitalize

    game = _game()
    room = _room(ch)
    olevel = 0
    argument, arg1 = one_argument(argument)
    argument, arg2 = one_argument(argument)
    if arg1 == "" or not is_number(arg1):
        send_to_char("Syntax:  oreset <vnum> <args>\n\r", ch)
        send_to_char("        -no_args               = into room\n\r", ch)
        send_to_char("        -<obj_name>            = into obj\n\r", ch)
        send_to_char("        -<mob_name> <wear_loc> = into mob\n\r", ch)
        return False
    p = game.index.get_obj_index(atoi(arg1))
    if p is None:
        send_to_char("REdit: No object has that vnum.\n\r", ch)
        return False
    if p.area is not room.area:
        send_to_char("REdit: No such object in this area.\n\r", ch)
        return False

    if arg2 == "":  # "Load into room."
        rs = new_reset_data()
        rs.command, rs.arg1, rs.arg2, rs.arg3, rs.arg4 = "O", p.vnum, 0, room.vnum, 0
        add_reset(room, rs, 0)
        newobj = create_object(game, p, number_fuzzy(olevel))
        obj_to_room(newobj, room)
        send_to_char("%s (%d) has been loaded and added to resets.\n\r" % (capitalize(p.short_descr), p.vnum), ch)
    elif argument == "" and (to_obj := get_obj_list(ch, arg2, room.contents)) is not None:
        rs = new_reset_data()  # "Load into object's inventory."
        rs.command, rs.arg1, rs.arg2, rs.arg3, rs.arg4 = "P", p.vnum, 0, to_obj.index.vnum, 1
        add_reset(room, rs, 0)
        newobj = create_object(game, p, number_fuzzy(olevel))
        newobj.cost = 0
        obj_to_obj(newobj, to_obj)
        send_to_char("%s (%d) has been loaded into %s (%d) and added to resets.\n\r"
                     % (capitalize(newobj.short_descr), newobj.index.vnum, to_obj.short_descr, to_obj.index.vnum),
                     ch)
    elif (to_mob := get_char_room(ch, arg2)) is not None:  # "Load into mobile's inventory."
        wear_loc = flag_value(F.WEAR_LOC_FLAGS, argument)
        if wear_loc == C.NO_FLAG:
            send_to_char("REdit: Invalid wear_loc.  '? wear-loc'\n\r", ch)
            return False
        if not p.wear_flags & wear_bit(wear_loc):  # "Disallow loading a sword(WEAR_WIELD) into WEAR_HEAD."
            send_to_char("%s (%d) has wear flags: [%s]\n\r" % (capitalize(p.short_descr), p.vnum,
                                                               flag_string(F.WEAR_FLAGS, p.wear_flags)), ch)
            return False
        if get_eq_char(to_mob, wear_loc) is not None:  # "Can't load into same position."
            send_to_char("REdit:  Object already equipped.\n\r", ch)
            return False
        rs = new_reset_data()
        rs.arg1 = p.vnum
        rs.arg2 = wear_loc  # (the limit, which it should be, is the wear location)
        rs.command = "G" if rs.arg2 == C.WEAR_NONE else "E"
        rs.arg3 = wear_loc
        add_reset(room, rs, 0)
        olevel = max(0, min(to_mob.level - 2, C.LEVEL_HERO))
        create_object(game, p, number_fuzzy(olevel))  # made, and left in the object list
        if to_mob.index is None:
            raise CWouldCrash("olc_act.c redit_oreset: a player's pIndexData is NULL")
        if to_mob.index.shop is not None:  # "Shop-keeper?"
            if p.item_type in _SHOP_LEVELS:
                olevel = number_range(*_SHOP_LEVELS[p.item_type])
            elif p.item_type == C.ITEM_WEAPON:
                olevel = number_range(5, 15) if rs.command == "G" else number_fuzzy(olevel)
            else:
                olevel = 0
            newobj = create_object(game, p, olevel)
            if rs.arg2 == C.WEAR_NONE:
                newobj.extra_flags |= C.ITEM_INVENTORY
        else:
            newobj = create_object(game, p, number_fuzzy(olevel))
        obj_to_char(newobj, to_mob)
        if rs.command == "E":
            equip_char(to_mob, newobj, rs.arg3)
        send_to_char("%s (%d) has been loaded %s of %s (%d) and added to resets.\n\r"
                     % (capitalize(p.short_descr), p.vnum, flag_string(F.WEAR_LOC_STRINGS, rs.arg3),
                        to_mob.short_descr, to_mob.index.vnum), ch)
    else:
        send_to_char("REdit:  That mobile isn't here.\n\r", ch)  # "Display Syntax"
        return False
    act("$n has created $p!", ch, newobj, None, C.TO_ROOM)
    return True


# C: olc_act.c redit_owner
def redit_owner(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  owner [owner]\n\r", ch)
        send_to_char("         owner none\n\r", ch)
        return False
    _room(ch).owner = "" if str_cmp(argument, "none") else argument
    send_to_char("Owner set.\n\r", ch)
    return True


# C: olc_act.c redit_room
def redit_room(ch, argument: str) -> bool:
    from charm.olc.bits import flag_value

    value = flag_value(F.ROOM_FLAGS, argument)
    if value == C.NO_FLAG:
        send_to_char("Sintaxis: room [flags]\n\r", ch)
        return False
    _room(ch).room_flags ^= value
    send_to_char("Room flags toggled.\n\r", ch)
    return True


# C: olc_act.c redit_sector
def redit_sector(ch, argument: str) -> bool:
    from charm.olc.bits import flag_value

    value = flag_value(F.SECTOR_FLAGS, argument)
    if value == C.NO_FLAG:
        send_to_char("Sintaxis: sector [tipo]\n\r", ch)
        return False
    _room(ch).sector_type = value
    send_to_char("Sector type set.\n\r", ch)
    return True
