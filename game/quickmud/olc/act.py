"""olc_act.c: what each editor's commands do: the shared helpers (?, version, the lists ? shows, the vnum range
checks), and the area, room, object and mob editors (aedit_*, redit_*, oedit_*, medit_*).

Every editor command takes (ch, argument) and returns True if it changed the area, which the editor then marks
AREA_CHANGED.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/olc_act.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from quickmud.commands.interp import is_number, one_argument
from quickmud.core.strings import atoi, str_cmp, str_prefix, upper
from quickmud.data import constants as C
from quickmud.data import flags as F
from quickmud.data.attacks import ATTACK_TABLE
from quickmud.data.items import LIQ_TABLE
from quickmud.data.mobprogs import MPROG_FLAGS
from quickmud.data.skills import SKILL_TABLE
from quickmud.data.specials import SPEC_TABLE
from quickmud.net.output import page_to_char, send_to_char
from quickmud.olc.bits import flag_string

# olc.h
VERSION = "ILAB Online Creation [Beta 1.0, ROM 2.3 modified]\n\r     Port a ROM 2.4 v1.8\n\r"
AUTHOR = ("     By Jason(jdinkel@mines.colorado.edu)\n\r     Modified for use with ROM 2.3\n\r"
          "     By Hans Birkeland (hansbi@ifi.uio.no)\n\r     Modificado para uso en ROM 2.4b6\n\r"
          "     Por Ivan Toledo (itoledo@ctcreuna.cl)\n\r")
DATE = ("     (Apr. 7, 1995 - ROM mod, Apr 16, 1995)\n\r     (Port a ROM 2.4 - Nov 2, 1996)\n\r"
        "     Version actual : 1.8 - Sep 8, 1998\n\r")
CREDITS = "     Original by Surreality(cxw197@psu.edu) and Locke(locke@lm.com)"


def _game():
    from quickmud.entities import game as game_module

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
    from quickmud.persist.player import capitalize

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
    from quickmud.olc.save import _s

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
    from quickmud.entities.resets import reset_area

    reset_area(_game(), _area(ch))
    send_to_char("Area reset.\n\r", ch)
    return False


# C: olc_act.c aedit_create
def aedit_create(ch, argument: str) -> bool:
    from quickmud.olc.mem import new_area

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
    from quickmud.olc.strings import string_proper, string_replace, string_unpad

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
    from quickmud.persist.player import capitalize

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
    from quickmud.entities.handler import is_name

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
    from quickmud.entities.handler import is_name
    from quickmud.olc.bits import flag_value

    _, arg = one_argument(argument)
    if arg == "":
        send_to_char("Syntax:  olist <all/name/item_type>\n\r", ch)
        return False
    index = _game().index
    every = str_cmp(arg, "all")
    found = [p for p in _in_area(ch, index.get_obj_index)
             if every or is_name(arg, p.name) or flag_value(F.TYPE_FLAGS, arg) == p.item_type]
    return _list(ch, found, "Object(s) not found in this area.\n\r", lambda p: p.short_descr)


# C: olc_act.c redit_oshow
def redit_oshow(ch, argument: str) -> bool:
    """An object prototype shown as oedit's show shows it; pEdit is then the room (which redit never reads)."""
    if argument == "":
        send_to_char("Syntax:  oshow <vnum>\n\r", ch)
        return False
    if not is_number(argument):
        send_to_char("REdit: Must be a number.\n\r", ch)
        return False
    p = _game().index.get_obj_index(atoi(argument))
    if p is None:
        send_to_char("REdit:  That object does not exist.\n\r", ch)
        return False
    ch.desc.pEdit = p
    oedit_show(ch, argument)
    ch.desc.pEdit = ch.in_room
    return False


def _first_words(names) -> str:
    """The first word of each name (one_argument: lower-cased), space-separated, then "]", or "none]"."""
    words = [one_argument(n)[1] for n in names]
    return (" ".join(words) + "]" if words else "none]") + "\n\r"


# C: olc_act.c redit_show
def redit_show(ch, argument: str) -> bool:
    from quickmud.commands.move import DIR_NAME
    from quickmud.core.strings import str_infix
    from quickmud.data.clans import CLAN_TABLE
    from quickmud.olc.save import _s
    from quickmud.persist.player import capitalize

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
    from quickmud.core.errors import CWouldCrash

    return CWouldCrash(f"olc_act.c change_exit: {what} an exit that leads nowhere (pToRoom is NULL)")


# C: olc_act.c change_exit
def change_exit(ch, argument: str, door: int) -> bool:
    """[direction] with flags, or delete, link, dig, room, key, name or desc; nothing moves that way. Exit flags
    are looked for in the whole line first, so a word like "door" anywhere in it toggles that flag instead."""
    from quickmud.commands.info import do_help
    from quickmud.commands.move import REV_DIR, move_char
    from quickmud.entities.handler import is_builder
    from quickmud.olc.bits import flag_value
    from quickmud.olc.mem import free_exit, new_exit
    from quickmud.olc.strings import string_append

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
            free_exit(to_room.exit[rev])
            to_room.exit[rev] = None
        free_exit(room.exit[door])
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
    from quickmud.entities.handler import is_name

    return next((ed for ed in room.extra_descr if is_name(keyword, ed.keyword)), None)


# C: olc_act.c redit_ed
def redit_ed(ch, argument: str) -> bool:
    from quickmud.olc.mem import new_extra_descr
    from quickmud.olc.strings import format_string, string_append

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
    from quickmud.entities.handler import is_builder
    from quickmud.olc.mem import new_room_index

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
    from quickmud.olc.strings import string_append

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
    from quickmud.world.lookup import clan_lookup

    _room(ch).clan = clan_lookup(argument)
    send_to_char("Clan set.\n\r", ch)
    return True


# C: olc_act.c redit_format
def redit_format(ch, argument: str) -> bool:
    from quickmud.olc.strings import format_string

    room = _room(ch)
    room.description = format_string(room.description)
    send_to_char("String formatted.\n\r", ch)
    return True


# C: olc_act.c redit_mreset
def redit_mreset(ch, argument: str) -> bool:
    from quickmud.entities.create import create_mobile
    from quickmud.entities.handler import char_to_room
    from quickmud.net.act import act
    from quickmud.olc.mem import new_reset_data
    from quickmud.olc.olc import add_reset
    from quickmud.persist.player import capitalize

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
    from quickmud.core.errors import CWouldCrash
    from quickmud.core.rng import number_fuzzy, number_range
    from quickmud.entities.create import create_object
    from quickmud.entities.handler import equip_char, get_char_room, get_eq_char, get_obj_list, obj_to_char, \
        obj_to_obj, obj_to_room
    from quickmud.net.act import act
    from quickmud.olc.bits import flag_value
    from quickmud.olc.mem import new_reset_data
    from quickmud.olc.olc import add_reset
    from quickmud.persist.player import capitalize

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
    from quickmud.olc.bits import flag_value

    value = flag_value(F.ROOM_FLAGS, argument)
    if value == C.NO_FLAG:
        send_to_char("Sintaxis: room [flags]\n\r", ch)
        return False
    _room(ch).room_flags ^= value
    send_to_char("Room flags toggled.\n\r", ch)
    return True


# C: olc_act.c redit_sector
def redit_sector(ch, argument: str) -> bool:
    from quickmud.olc.bits import flag_value

    value = flag_value(F.SECTOR_FLAGS, argument)
    if value == C.NO_FLAG:
        send_to_char("Sintaxis: sector [tipo]\n\r", ch)
        return False
    _room(ch).sector_type = value
    send_to_char("Sector type set.\n\r", ch)
    return True


# -- the object editor (OEDIT): every command edits the prototype in ch->desc->pEdit (EDIT_OBJ) --


def _obj(ch):
    return ch.desc.pEdit


def _skill(sn: int) -> str:
    from quickmud.olc.save import _s

    return _s(SKILL_TABLE[sn].name) if sn != -1 else "none"


# C: olc_act.c show_obj_values
def show_obj_values(ch, obj) -> None:
    from quickmud.olc.save import _s

    v, t = obj.value, obj.item_type
    index = _game().index
    if t == C.ITEM_LIGHT:
        if v[2] == -1 or v[2] == 999:  # "ROM OLC"
            send_to_char("[v2] Light:  Infinite[-1]\n\r", ch)
        else:
            send_to_char("[v2] Light:  [%d]\n\r" % v[2], ch)
    elif t in (C.ITEM_WAND, C.ITEM_STAFF):
        send_to_char("[v0] Level:          [%d]\n\r[v1] Charges Total:  [%d]\n\r[v2] Charges Left:   [%d]\n\r"
                     "[v3] Spell:          %s\n\r" % (v[0], v[1], v[2], _skill(v[3])), ch)
    elif t == C.ITEM_PORTAL:
        send_to_char("[v0] Charges:        [%d]\n\r[v1] Exit Flags:     %s\n\r[v2] Portal Flags:   %s\n\r"
                     "[v3] Goes to (vnum): [%d]\n\r" % (v[0], flag_string(F.EXIT_FLAGS, v[1]),
                                                       flag_string(F.PORTAL_FLAGS, v[2]), v[3]), ch)
    elif t == C.ITEM_FURNITURE:
        send_to_char("[v0] Max people:      [%d]\n\r[v1] Max weight:      [%d]\n\r[v2] Furniture Flags: %s\n\r"
                     "[v3] Heal bonus:      [%d]\n\r[v4] Mana bonus:      [%d]\n\r"
                     % (v[0], v[1], flag_string(F.FURNITURE_FLAGS, v[2]), v[3], v[4]), ch)
    elif t in (C.ITEM_SCROLL, C.ITEM_POTION, C.ITEM_PILL):
        send_to_char("[v0] Level:  [%d]\n\r[v1] Spell:  %s\n\r[v2] Spell:  %s\n\r[v3] Spell:  %s\n\r"
                     "[v4] Spell:  %s\n\r" % (v[0], _skill(v[1]), _skill(v[2]), _skill(v[3]), _skill(v[4])), ch)
    elif t == C.ITEM_ARMOR:  # "ARMOR for ROM"
        send_to_char("[v0] Ac pierce       [%d]\n\r[v1] Ac bash         [%d]\n\r[v2] Ac slash        [%d]\n\r"
                     "[v3] Ac exotic       [%d]\n\r" % (v[0], v[1], v[2], v[3]), ch)
    elif t == C.ITEM_WEAPON:  # "WEAPON changed in ROM"
        send_to_char("[v0] Weapon class:   %s\n\r" % flag_string(F.WEAPON_CLASS, v[0]), ch)
        send_to_char("[v1] Number of dice: [%d]\n\r" % v[1], ch)
        send_to_char("[v2] Type of dice:   [%d]\n\r" % v[2], ch)
        send_to_char("[v3] Type:           %s\n\r" % _s(ATTACK_TABLE[v[3]].name), ch)
        send_to_char("[v4] Special type:   %s\n\r" % flag_string(F.WEAPON_TYPE2, v[4]), ch)
    elif t == C.ITEM_CONTAINER:
        key = index.get_obj_index(v[2])
        send_to_char("[v0] Weight:     [%d kg]\n\r[v1] Flags:      [%s]\n\r[v2] Key:     %s [%d]\n\r"
                     "[v3] Capacity    [%d]\n\r[v4] Weight Mult [%d]\n\r"
                     % (v[0], flag_string(F.CONTAINER_FLAGS, v[1]), _s(key.short_descr) if key else "none", v[2],
                        v[3], v[4]), ch)
    elif t == C.ITEM_DRINK_CON:
        send_to_char("[v0] Liquid Total: [%d]\n\r[v1] Liquid Left:  [%d]\n\r[v2] Liquid:       %s\n\r"
                     "[v3] Poisoned:     %s\n\r" % (v[0], v[1], _s(LIQ_TABLE[v[2]].liq_name),
                                                   "Yes" if v[3] != 0 else "No"), ch)
    elif t == C.ITEM_FOUNTAIN:
        send_to_char("[v0] Liquid Total: [%d]\n\r[v1] Liquid Left:  [%d]\n\r[v2] Liquid:        %s\n\r"
                     % (v[0], v[1], _s(LIQ_TABLE[v[2]].liq_name)), ch)
    elif t == C.ITEM_FOOD:
        send_to_char("[v0] Food hours: [%d]\n\r[v1] Full hours: [%d]\n\r[v3] Poisoned:   %s\n\r"
                     % (v[0], v[1], "Yes" if v[3] != 0 else "No"), ch)
    elif t == C.ITEM_MONEY:
        send_to_char("[v0] Gold:   [%d]\n\r" % v[0], ch)


def _flag_or_zero(table, argument: str) -> int:
    """ALT_FLAGVALUE_SET's value: the flags, or 0 for none."""
    from quickmud.olc.bits import flag_value

    value = flag_value(table, argument)
    return 0 if value == C.NO_FLAG else value


# per item type: the help topic for a value it has no setting for, and for each value: (message, how it's set),
# where how is "atoi", "skill", "attack", "liquid", "poison", a flag table to set, or ("toggle", table)
_ATOI, _SKILL = "atoi", "skill"
_SETTERS = {
    C.ITEM_LIGHT: ("ITEM_LIGHT", {2: ("HOURS OF LIGHT SET.\n\r\n\r", _ATOI)}),
    C.ITEM_WAND: ("ITEM_STAFF_WAND", {0: ("SPELL LEVEL SET.\n\r\n\r", _ATOI),
                                      1: ("TOTAL NUMBER OF CHARGES SET.\n\r\n\r", _ATOI),
                                      2: ("CURRENT NUMBER OF CHARGES SET.\n\r\n\r", _ATOI),
                                      3: ("SPELL TYPE SET.\n\r", _SKILL)}),
    C.ITEM_SCROLL: ("ITEM_SCROLL_POTION_PILL", {0: ("SPELL LEVEL SET.\n\r\n\r", _ATOI),
                                                1: ("SPELL TYPE 1 SET.\n\r\n\r", _SKILL),
                                                2: ("SPELL TYPE 2 SET.\n\r\n\r", _SKILL),
                                                3: ("SPELL TYPE 3 SET.\n\r\n\r", _SKILL),
                                                4: ("SPELL TYPE 4 SET.\n\r\n\r", _SKILL)}),
    C.ITEM_ARMOR: ("ITEM_ARMOR", {0: ("AC PIERCE SET.\n\r\n\r", _ATOI), 1: ("AC BASH SET.\n\r\n\r", _ATOI),
                                  2: ("AC SLASH SET.\n\r\n\r", _ATOI), 3: ("AC EXOTIC SET.\n\r\n\r", _ATOI)}),
    C.ITEM_WEAPON: ("ITEM_WEAPON", {0: ("WEAPON CLASS SET.\n\r\n\r", F.WEAPON_CLASS),
                                    1: ("NUMBER OF DICE SET.\n\r\n\r", _ATOI),
                                    2: ("TYPE OF DICE SET.\n\r\n\r", _ATOI),
                                    3: ("WEAPON TYPE SET.\n\r\n\r", "attack"),
                                    4: ("SPECIAL WEAPON TYPE TOGGLED.\n\r\n\r", ("toggle", F.WEAPON_TYPE2))}),
    C.ITEM_PORTAL: ("ITEM_PORTAL", {0: ("CHARGES SET.\n\r\n\r", _ATOI), 1: ("EXIT FLAGS SET.\n\r\n\r", F.EXIT_FLAGS),
                                    2: ("PORTAL FLAGS SET.\n\r\n\r", F.PORTAL_FLAGS),
                                    3: ("EXIT VNUM SET.\n\r\n\r", _ATOI)}),
    C.ITEM_FURNITURE: ("ITEM_FURNITURE", {0: ("NUMBER OF PEOPLE SET.\n\r\n\r", _ATOI),
                                          1: ("MAX WEIGHT SET.\n\r\n\r", _ATOI),
                                          2: ("FURNITURE FLAGS TOGGLED.\n\r\n\r", ("toggle", F.FURNITURE_FLAGS)),
                                          3: ("HEAL BONUS SET.\n\r\n\r", _ATOI),
                                          4: ("MANA BONUS SET.\n\r\n\r", _ATOI)}),
    C.ITEM_DRINK_CON: ("ITEM_DRINK", {0: ("MAXIMUM AMOUT OF LIQUID HOURS SET.\n\r\n\r", _ATOI),
                                      1: ("CURRENT AMOUNT OF LIQUID HOURS SET.\n\r\n\r", _ATOI),
                                      2: ("LIQUID TYPE SET.\n\r\n\r", "liquid"),
                                      3: ("POISON VALUE TOGGLED.\n\r\n\r", "poison")}),
    C.ITEM_FOUNTAIN: ("ITEM_FOUNTAIN", {0: ("MAXIMUM AMOUT OF LIQUID HOURS SET.\n\r\n\r", _ATOI),
                                        1: ("CURRENT AMOUNT OF LIQUID HOURS SET.\n\r\n\r", _ATOI),
                                        2: ("LIQUID TYPE SET.\n\r\n\r", "liquid")}),
    C.ITEM_FOOD: ("ITEM_FOOD", {0: ("HOURS OF FOOD SET.\n\r\n\r", _ATOI), 1: ("HOURS OF FULL SET.\n\r\n\r", _ATOI),
                                3: ("POISON VALUE TOGGLED.\n\r\n\r", "poison")}),
    C.ITEM_MONEY: ("ITEM_MONEY", {0: ("GOLD AMOUNT SET.\n\r\n\r", _ATOI), 1: ("SILVER AMOUNT SET.\n\r\n\r", _ATOI)}),
}
_SETTERS[C.ITEM_STAFF] = _SETTERS[C.ITEM_WAND]
_SETTERS[C.ITEM_POTION] = _SETTERS[C.ITEM_PILL] = _SETTERS[C.ITEM_SCROLL]


# C: olc_act.c set_obj_values
def set_obj_values(ch, obj, value_num: int, argument: str) -> bool:
    """Set value number value_num of obj as its item type reads it, then show the values. A value the type has no
    setting for shows the type's help instead; a type with no values at all just shows them (and is True)."""
    from quickmud.commands.info import do_help
    from quickmud.olc.bits import flag_value
    from quickmud.world.lookup import attack_lookup, liq_lookup, skill_lookup

    index = _game().index
    v = obj.value
    if obj.item_type == C.ITEM_CONTAINER:  # its own checks
        if value_num == 0:
            send_to_char("WEIGHT CAPACITY SET.\n\r\n\r", ch)
            v[0] = atoi(argument)
        elif value_num == 1:
            value = flag_value(F.CONTAINER_FLAGS, argument)
            if value == C.NO_FLAG:
                do_help(ch, "ITEM_CONTAINER")
                return False
            v[1] ^= value
            send_to_char("CONTAINER TYPE SET.\n\r\n\r", ch)
        elif value_num == 2:
            if atoi(argument) != 0:
                key = index.get_obj_index(atoi(argument))
                if key is None:
                    send_to_char("THERE IS NO SUCH ITEM.\n\r\n\r", ch)
                    return False
                if key.item_type != C.ITEM_KEY:
                    send_to_char("THAT ITEM IS NOT A KEY.\n\r\n\r", ch)
                    return False
            send_to_char("CONTAINER KEY SET.\n\r\n\r", ch)
            v[2] = atoi(argument)
        elif value_num == 3:
            send_to_char("CONTAINER MAX WEIGHT SET.\n\r", ch)
            v[3] = atoi(argument)
        elif value_num == 4:
            send_to_char("WEIGHT MULTIPLIER SET.\n\r\n\r", ch)
            v[4] = atoi(argument)
        else:
            do_help(ch, "ITEM_CONTAINER")
            return False
    elif obj.item_type in _SETTERS:
        topic, setters = _SETTERS[obj.item_type]
        if value_num not in setters:
            do_help(ch, topic)
            return False
        message, how = setters[value_num]
        send_to_char(message, ch)
        if how == _ATOI:
            v[value_num] = atoi(argument)
        elif how == _SKILL:
            v[value_num] = skill_lookup(argument)
        elif how == "attack":
            v[value_num] = attack_lookup(argument)
        elif how == "liquid":
            v[value_num] = liq_lookup(argument) if liq_lookup(argument) != -1 else 0
        elif how == "poison":
            v[value_num] = 1 if v[value_num] == 0 else 0
        elif how[0] == "toggle":  # ALT_FLAGVALUE_TOGGLE (a flag table is a tuple too, of FlagType)
            v[value_num] ^= _flag_or_zero(how[1], argument)
        else:  # ALT_FLAGVALUE_SET
            v[value_num] = _flag_or_zero(how, argument)
    show_obj_values(ch, obj)
    return True


# C: olc_act.c oedit_show
def oedit_show(ch, argument: str) -> bool:
    from quickmud.olc.save import _s

    p = _obj(ch)
    send_to_char("Name:        [%s]\n\rArea:        [%5d] %s\n\r"
                 % (_s(p.name), -1 if p.area is None else p.area.vnum,
                    "No Area" if p.area is None else _s(p.area.name)), ch)
    send_to_char("Vnum:        [%5d]\n\rType:        [%s]\n\r" % (p.vnum, flag_string(F.TYPE_FLAGS, p.item_type)), ch)
    send_to_char("Level:       [%5d]\n\r" % p.level, ch)
    send_to_char("Wear flags:  [%s]\n\r" % flag_string(F.WEAR_FLAGS, p.wear_flags), ch)
    send_to_char("Extra flags: [%s]\n\r" % flag_string(F.EXTRA_FLAGS, p.extra_flags), ch)
    send_to_char("Material:    [%s]\n\r" % _s(p.material), ch)  # "ROM"
    send_to_char("Condition:   [%5d]\n\r" % p.condition, ch)  # "ROM"
    send_to_char("Weight:      [%5d]\n\rCost:        [%5d]\n\r" % (p.weight, p.cost), ch)
    if p.extra_descr:
        send_to_char("Ex desc kwd: ", ch)
        for ed in p.extra_descr:
            send_to_char("[", ch)
            send_to_char(ed.keyword, ch)
            send_to_char("]", ch)
        send_to_char("\n\r", ch)
    send_to_char("Short desc:  %s\n\rLong desc:\n\r     %s\n\r" % (_s(p.short_descr), _s(p.description)), ch)
    for cnt, paf in enumerate(p.affected):
        if cnt == 0:
            send_to_char("Number Modifier Affects\n\r", ch)
            send_to_char("------ -------- -------\n\r", ch)
        send_to_char("[%4d] %-8d %s\n\r" % (cnt, paf.modifier, flag_string(F.APPLY_FLAGS, paf.location)), ch)
    show_obj_values(ch, p)
    return False


def _new_affect(location: int, modifier: int, where: int, bitvector: int, level: int):
    """new_affect, filled in as addaffect and addapply do (type and duration -1)."""
    from quickmud.world.index import Affect

    return Affect(where=where, type=-1, level=level, duration=-1, location=location, modifier=modifier,
                  bitvector=bitvector)


# C: olc_act.c oedit_addaffect
def oedit_addaffect(ch, argument: str) -> bool:
    from quickmud.olc.bits import flag_value

    p = _obj(ch)
    argument, loc = one_argument(argument)
    _, mod = one_argument(argument)
    if loc == "" or mod == "" or not is_number(mod):
        send_to_char("Syntax:  addaffect [location] [#xmod]\n\r", ch)
        return False
    value = flag_value(F.APPLY_FLAGS, loc)
    if value == C.NO_FLAG:  # "Hugin"
        send_to_char("Valid affects are:\n\r", ch)
        show_help(ch, "apply")
        return False
    p.affected.insert(0, _new_affect(value, atoi(mod), C.TO_OBJECT, 0, p.level))
    send_to_char("Affect added.\n\r", ch)
    return True


# bitvector_type, by the apply type's value: the table its bits are named from, and the ? topic that lists them
BITVECTOR_TYPE = ((F.AFFECT_FLAGS, "affect"), (F.APPLY_FLAGS, "apply"), (F.IMM_FLAGS, "imm"), (F.RES_FLAGS, "res"),
                  (F.VULN_FLAGS, "vuln"), (F.WEAPON_TYPE2, "weapon"))


# C: olc_act.c oedit_addapply
def oedit_addapply(ch, argument: str) -> bool:
    """An affect with bits. The type's value picks the table the bits are named from (bitvector_type[typ]), so
    "object" names them from the apply locations."""
    from quickmud.olc.bits import flag_value

    p = _obj(ch)
    argument, kind = one_argument(argument)
    argument, loc = one_argument(argument)
    argument, mod = one_argument(argument)
    _, bvector = one_argument(argument)
    typ = flag_value(F.APPLY_TYPES, kind) if kind != "" else C.NO_FLAG
    if typ == C.NO_FLAG:
        send_to_char("Invalid apply type. Valid apply types are:\n\r", ch)
        show_help(ch, "apptype")
        return False
    value = flag_value(F.APPLY_FLAGS, loc) if loc != "" else C.NO_FLAG
    if value == C.NO_FLAG:
        send_to_char("Valid applys are:\n\r", ch)
        show_help(ch, "apply")
        return False
    table, topic = BITVECTOR_TYPE[typ]
    bv = flag_value(table, bvector) if bvector != "" else C.NO_FLAG
    if bv == C.NO_FLAG:
        send_to_char("Invalid bitvector type.\n\r", ch)
        send_to_char("Valid bitvector types are:\n\r", ch)
        show_help(ch, topic)
        return False
    if mod == "" or not is_number(mod):
        send_to_char("Syntax:  addapply [type] [location] [#xmod] [bitvector]\n\r", ch)
        return False
    p.affected.insert(0, _new_affect(value, atoi(mod), F.APPLY_TYPES[typ].bit, bv, p.level))
    send_to_char("Apply added.\n\r", ch)
    return True


# C: olc_act.c oedit_delaffect
def oedit_delaffect(ch, argument: str) -> bool:
    """Remove affect number n, counting from 0 as show lists them."""
    p = _obj(ch)
    _, affect = one_argument(argument)
    if not is_number(affect) or affect == "":
        send_to_char("Syntax:  delaffect [#xaffect]\n\r", ch)
        return False
    value = atoi(affect)
    if value < 0:
        send_to_char("Only non-negative affect-numbers allowed.\n\r", ch)
        return False
    if not p.affected:
        send_to_char("OEdit:  Non-existant affect.\n\r", ch)
        return False
    if value >= len(p.affected):
        send_to_char("No such affect.\n\r", ch)
        return False
    p.affected.pop(value)
    send_to_char("Affect removed.\n\r", ch)
    return True


# C: olc_act.c oedit_name
def oedit_name(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  name [string]\n\r", ch)
        return False
    _obj(ch).name = argument
    send_to_char("Name set.\n\r", ch)
    return True


# C: olc_act.c oedit_short
def oedit_short(ch, argument: str) -> bool:
    from quickmud.core.strings import lower

    if argument == "":
        send_to_char("Syntax:  short [string]\n\r", ch)
        return False
    _obj(ch).short_descr = lower(argument[0]) + argument[1:]
    send_to_char("Short description set.\n\r", ch)
    return True


# C: olc_act.c oedit_long
def oedit_long(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  long [string]\n\r", ch)
        return False
    _obj(ch).description = upper(argument[0]) + argument[1:]
    send_to_char("Long description set.\n\r", ch)
    return True


# C: olc_act.c set_value
def set_value(ch, obj, argument: str, value: int) -> bool:
    if argument == "":
        set_obj_values(ch, obj, -1, "")  # "'\0' changed to "" -- Hugin"
        return False
    return set_obj_values(ch, obj, value, argument)


# C: olc_act.c oedit_values
def oedit_values(ch, argument: str, value: int) -> bool:
    return set_value(ch, _obj(ch), argument, value)


# C: olc_act.c oedit_value0
def oedit_value0(ch, argument: str) -> bool:
    return oedit_values(ch, argument, 0)


# C: olc_act.c oedit_value1
def oedit_value1(ch, argument: str) -> bool:
    return oedit_values(ch, argument, 1)


# C: olc_act.c oedit_value2
def oedit_value2(ch, argument: str) -> bool:
    return oedit_values(ch, argument, 2)


# C: olc_act.c oedit_value3
def oedit_value3(ch, argument: str) -> bool:
    return oedit_values(ch, argument, 3)


# C: olc_act.c oedit_value4
def oedit_value4(ch, argument: str) -> bool:
    return oedit_values(ch, argument, 4)


def _number_field(ch, argument: str, field: str, syntax: str, done: str) -> bool:
    if argument == "" or not is_number(argument):
        send_to_char(syntax, ch)
        return False
    setattr(_obj(ch), field, atoi(argument))
    send_to_char(done, ch)
    return True


# C: olc_act.c oedit_weight
def oedit_weight(ch, argument: str) -> bool:
    return _number_field(ch, argument, "weight", "Syntax:  weight [number]\n\r", "Weight set.\n\r")


# C: olc_act.c oedit_cost
def oedit_cost(ch, argument: str) -> bool:
    return _number_field(ch, argument, "cost", "Syntax:  cost [number]\n\r", "Cost set.\n\r")


# C: olc_act.c oedit_create
def oedit_create(ch, argument: str) -> bool:
    """A new object prototype at the vnum given, made the one being edited. (top_vnum_obj, which this raises, is
    read by nothing.)"""
    from quickmud.entities.handler import is_builder
    from quickmud.olc.mem import new_obj_index

    index = _game().index
    value = atoi(argument)
    if argument == "" or value == 0:
        send_to_char("Syntax:  oedit create [vnum]\n\r", ch)
        return False
    area = get_vnum_area(value)
    if area is None:
        send_to_char("OEdit:  That vnum is not assigned an area.\n\r", ch)
        return False
    if not is_builder(ch, area):
        send_to_char("OEdit:  Vnum in an area you cannot build in.\n\r", ch)
        return False
    if index.get_obj_index(value) is not None:
        send_to_char("OEdit:  Object vnum already exists.\n\r", ch)
        return False
    p = new_obj_index(area)
    p.vnum = value
    index.objs[value] = p  # the head of its hash chain: the newest
    ch.desc.pEdit = p
    send_to_char("Object Created.\n\r", ch)
    return True


# C: olc_act.c oedit_ed
def oedit_ed(ch, argument: str) -> bool:
    from quickmud.olc.mem import new_extra_descr
    from quickmud.olc.strings import format_string, string_append

    p = _obj(ch)
    argument, command = one_argument(argument)
    _, keyword = one_argument(argument)
    if command == "":
        send_to_char("Syntax:  ed add [keyword]\n\r", ch)
        send_to_char("         ed delete [keyword]\n\r", ch)
        send_to_char("         ed edit [keyword]\n\r", ch)
        send_to_char("         ed format [keyword]\n\r", ch)
        return False
    for sub in ("add", "edit", "delete", "format"):
        if not str_cmp(command, sub):
            continue
        if keyword == "":
            send_to_char("Syntax:  ed %s [keyword]\n\r" % sub, ch)
            return False
        if sub == "add":
            ed = new_extra_descr()
            ed.keyword = keyword
            p.extra_descr.insert(0, ed)
            string_append(ch, (ed, "description"))
            return True
        ed = _find_ed(p, keyword)
        if ed is None:
            send_to_char("OEdit:  Extra description keyword not found.\n\r", ch)
            return False
        if sub == "edit":
            string_append(ch, (ed, "description"))
        elif sub == "delete":
            p.extra_descr.remove(ed)
            send_to_char("Extra description deleted.\n\r", ch)
        else:
            ed.description = format_string(ed.description)
            send_to_char("Extra description formatted.\n\r", ch)
        return True
    oedit_ed(ch, "")
    return False


def _toggle_flags(ch, argument: str, table, field: str, done: str, syntax: str) -> bool:
    from quickmud.olc.bits import flag_value

    if argument != "":
        value = flag_value(table, argument)
        if value != C.NO_FLAG:
            p = _obj(ch)
            setattr(p, field, getattr(p, field) ^ value)
            send_to_char(done, ch)
            return True
    send_to_char(syntax, ch)
    return False


# C: olc_act.c oedit_extra
def oedit_extra(ch, argument: str) -> bool:
    return _toggle_flags(ch, argument, F.EXTRA_FLAGS, "extra_flags", "Extra flag toggled.\n\r",
                         "Syntax:  extra [flag]\n\rType '? extra' for a list of flags.\n\r")


# C: olc_act.c oedit_wear
def oedit_wear(ch, argument: str) -> bool:
    return _toggle_flags(ch, argument, F.WEAR_FLAGS, "wear_flags", "Wear flag toggled.\n\r",
                         "Syntax:  wear [flag]\n\rType '? wear' for a list of flags.\n\r")


# C: olc_act.c oedit_type
def oedit_type(ch, argument: str) -> bool:
    from quickmud.olc.bits import flag_value

    if argument != "":
        value = flag_value(F.TYPE_FLAGS, argument)
        if value != C.NO_FLAG:
            p = _obj(ch)
            p.item_type = value
            send_to_char("Type set.\n\r", ch)
            p.value[:] = [0, 0, 0, 0, 0]  # "Clear the values."
            return True
    send_to_char("Syntax:  type [flag]\n\rType '? type' for a list of flags.\n\r", ch)
    return False


# C: olc_act.c oedit_material
def oedit_material(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  material [string]\n\r", ch)
        return False
    _obj(ch).material = argument
    send_to_char("Material set.\n\r", ch)
    return True


# C: olc_act.c oedit_level
def oedit_level(ch, argument: str) -> bool:
    return _number_field(ch, argument, "level", "Syntax:  level [number]\n\r", "Level set.\n\r")


# C: olc_act.c oedit_condition
def oedit_condition(ch, argument: str) -> bool:
    if argument != "" and 0 <= atoi(argument) <= 100:
        _obj(ch).condition = atoi(argument)
        send_to_char("Condition set.\n\r", ch)
        return True
    send_to_char("Syntax:  condition [number]\n\rWhere number can range from 0 (ruined) to 100 (perfect).\n\r", ch)
    return False


# -- the mob editor (MEDIT): every command edits the prototype in ch->desc->pEdit (EDIT_MOB) --


def _mob(ch):
    return ch.desc.pEdit


# C: olc_act.c medit_show
def medit_show(ch, argument: str) -> bool:
    from quickmud.data.races import RACE_TABLE
    from quickmud.olc.save import _s
    from quickmud.systems.mobcmds import mprog_type_to_name
    from quickmud.world.lookup import spec_name

    p = _mob(ch)
    w = lambda text: send_to_char(text, ch)  # noqa: E731
    w("Name:        [%s]\n\rArea:        [%5d] %s\n\r" % (_s(p.player_name), -1 if p.area is None else p.area.vnum,
                                                          "No Area" if p.area is None else _s(p.area.name)))
    w("Act:         [%s]\n\r" % flag_string(F.ACT_FLAGS, p.act))
    sex = ("male   " if p.sex == C.SEX_MALE else "female " if p.sex == C.SEX_FEMALE else "random " if p.sex == 3
           else "neutral")
    w("Vnum:        [%5d] Sex:   [%s]   Race: [%s]\n\r" % (p.vnum, sex, _s(RACE_TABLE[p.race].name)))
    w("Level:       [%2d]    Align: [%4d]      Hitroll: [%2d] Dam Type:    [%s]\n\r"
      % (p.level, p.alignment, p.hitroll, _s(ATTACK_TABLE[p.dam_type].name)))
    if p.group:
        w("Group:       [%5d]\n\r" % p.group)
    w("Hit dice:    [%2dd%-3d+%4d] " % p.hit)
    w("Damage dice: [%2dd%-3d+%4d] " % p.damage)
    w("Mana dice:   [%2dd%-3d+%4d]\n\r" % p.mana)
    w("Affected by: [%s]\n\r" % flag_string(F.AFFECT_FLAGS, p.affected_by))
    w("Armor:       [pierce: %d  bash: %d  slash: %d  magic: %d]\n\r" % p.ac)
    w("Form:        [%s]\n\r" % flag_string(F.FORM_FLAGS, p.form))
    w("Parts:       [%s]\n\r" % flag_string(F.PART_FLAGS, p.parts))
    w("Imm:         [%s]\n\r" % flag_string(F.IMM_FLAGS, p.imm_flags))
    w("Res:         [%s]\n\r" % flag_string(F.RES_FLAGS, p.res_flags))
    w("Vuln:        [%s]\n\r" % flag_string(F.VULN_FLAGS, p.vuln_flags))
    w("Off:         [%s]\n\r" % flag_string(F.OFF_FLAGS, p.off_flags))
    w("Size:        [%s]\n\r" % flag_string(F.SIZE_FLAGS, p.size))
    w("Material:    [%s]\n\r" % _s(p.material))
    w("Start pos.   [%s]\n\r" % flag_string(F.POSITION_FLAGS, p.start_pos))
    w("Default pos  [%s]\n\r" % flag_string(F.POSITION_FLAGS, p.default_pos))
    w("Wealth:      [%5d]\n\r" % p.wealth)
    if p.spec_fun:
        w("Spec fun:    [%s]\n\r" % _s(spec_name(p.spec_fun)))
    w("Short descr: %s\n\rLong descr:\n\r%s" % (_s(p.short_descr), _s(p.long_descr)))
    w("Description:\n\r%s" % _s(p.description))
    if p.shop is not None:
        shop = p.shop
        w("Shop data for [%5d]:\n\r  Markup for purchaser: %d%%\n\r  Markdown for seller:  %d%%\n\r"
          % (shop.keeper, shop.profit_buy, shop.profit_sell))
        w("  Hours: %d to %d.\n\r" % (shop.open_hour, shop.close_hour))
        for i in range(C.MAX_TRADE):
            if shop.buy_type[i] != 0:
                if i == 0:  # (so the heading is left out when the first slot is empty)
                    w("  Number Trades Type\n\r")
                    w("  ------ -----------\n\r")
                w("  [%4d] %s\n\r" % (i, flag_string(F.TYPE_FLAGS, shop.buy_type[i])))
    if p.mprogs:
        w("\n\rMOBPrograms for [%5d]:\n\r" % p.vnum)
        for cnt, prog in enumerate(p.mprogs):
            if cnt == 0:
                w(" Number Vnum Trigger Phrase\n\r")
                w(" ------ ---- ------- ------\n\r")
            w("[%5d] %4d %7s %s\n\r" % (cnt, prog.vnum, mprog_type_to_name(prog.trig_type), _s(prog.trig_phrase)))
    return False


# C: olc_act.c medit_create
def medit_create(ch, argument: str) -> bool:
    """A new mob prototype at the vnum given, made the one being edited. (top_vnum_mob is read by nothing.)"""
    from quickmud.entities.handler import is_builder
    from quickmud.olc.mem import new_mob_index

    index = _game().index
    value = atoi(argument)
    if argument == "" or value == 0:
        send_to_char("Syntax:  medit create [vnum]\n\r", ch)
        return False
    area = get_vnum_area(value)
    if area is None:
        send_to_char("MEdit:  That vnum is not assigned an area.\n\r", ch)
        return False
    if not is_builder(ch, area):
        send_to_char("MEdit:  Vnum in an area you cannot build in.\n\r", ch)
        return False
    if index.get_mob_index(value) is not None:
        send_to_char("MEdit:  Mobile vnum already exists.\n\r", ch)
        return False
    p = new_mob_index(area)
    p.vnum = value
    p.act = C.ACT_IS_NPC
    index.mobs[value] = p  # the head of its hash chain: the newest
    ch.desc.pEdit = p
    send_to_char("Mobile Created.\n\r", ch)
    return True


# C: olc_act.c medit_spec
def medit_spec(ch, argument: str) -> bool:
    from quickmud.world.lookup import spec_lookup

    p = _mob(ch)
    if argument == "":
        send_to_char("Syntax:  spec [special function]\n\r", ch)
        return False
    if str_cmp(argument, "none"):
        p.spec_fun = None
        send_to_char("Spec removed.\n\r", ch)
        return True
    if spec_lookup(argument):
        p.spec_fun = spec_lookup(argument)
        send_to_char("Spec set.\n\r", ch)
        return True
    send_to_char("MEdit: No such special function.\n\r", ch)
    return False


# C: olc_act.c medit_damtype
def medit_damtype(ch, argument: str) -> bool:
    from quickmud.world.lookup import attack_lookup

    if argument == "":
        send_to_char("Syntax:  damtype [damage message]\n\r", ch)
        send_to_char("For a list of damage types, type '? weapon'.\n\r", ch)
        return False
    _mob(ch).dam_type = attack_lookup(argument)
    send_to_char("Damage type set.\n\r", ch)
    return True


def _mob_number(ch, argument: str, field: str, syntax: str, done: str) -> bool:
    if argument == "" or not is_number(argument):
        send_to_char(syntax, ch)
        return False
    setattr(_mob(ch), field, atoi(argument))
    send_to_char(done, ch)
    return True


# C: olc_act.c medit_align
def medit_align(ch, argument: str) -> bool:
    return _mob_number(ch, argument, "alignment", "Syntax:  alignment [number]\n\r", "Alignment set.\n\r")


# C: olc_act.c medit_level
def medit_level(ch, argument: str) -> bool:
    return _mob_number(ch, argument, "level", "Syntax:  level [number]\n\r", "Level set.\n\r")


# C: olc_act.c medit_desc
def medit_desc(ch, argument: str) -> bool:
    from quickmud.olc.strings import string_append

    if argument == "":
        string_append(ch, (_mob(ch), "description"))
        return True
    send_to_char("Syntax:  desc    - line edit\n\r", ch)
    return False


# C: olc_act.c medit_long
def medit_long(ch, argument: str) -> bool:
    if argument == "":
        send_to_char("Syntax:  long [string]\n\r", ch)
        return False
    text = argument + "\n\r"
    _mob(ch).long_descr = upper(text[0]) + text[1:]
    send_to_char("Long description set.\n\r", ch)
    return True


def _mob_text(ch, argument: str, field: str, syntax: str, done: str) -> bool:
    if argument == "":
        send_to_char(syntax, ch)
        return False
    setattr(_mob(ch), field, argument)
    send_to_char(done, ch)
    return True


# C: olc_act.c medit_short
def medit_short(ch, argument: str) -> bool:
    return _mob_text(ch, argument, "short_descr", "Syntax:  short [string]\n\r", "Short description set.\n\r")


# C: olc_act.c medit_name
def medit_name(ch, argument: str) -> bool:
    return _mob_text(ch, argument, "player_name", "Syntax:  name [string]\n\r", "Name set.\n\r")


_NO_SHOP = "MEdit:  You must create the shop first (shop assign).\n\r"


# C: olc_act.c medit_shop
def medit_shop(ch, argument: str) -> bool:
    """shop hours, profit, type, assign and remove. (The C keeps shops in a list too, shop_first to shop_last, which
    nothing else here reads; removing a shop from a mob that has none walks it with a NULL shop and crashes.)"""
    from dataclasses import replace

    from quickmud.core.errors import CWouldCrash
    from quickmud.olc.bits import flag_value
    from quickmud.olc.mem import free_shop, new_shop

    argument, command = one_argument(argument)
    argument, arg1 = one_argument(argument)
    p = _mob(ch)
    if command == "":
        send_to_char("Syntax:  shop hours [#xopening] [#xclosing]\n\r", ch)
        send_to_char("         shop profit [#xbuying%] [#xselling%]\n\r", ch)
        send_to_char("         shop type [#x0-4] [item type]\n\r", ch)
        send_to_char("         shop assign\n\r", ch)
        send_to_char("         shop remove\n\r", ch)
        return False
    if str_cmp(command, "hours"):
        if arg1 == "" or not is_number(arg1) or argument == "" or not is_number(argument):
            send_to_char("Syntax:  shop hours [#xopening] [#xclosing]\n\r", ch)
            return False
        if p.shop is None:
            send_to_char(_NO_SHOP, ch)
            return False
        p.shop.open_hour, p.shop.close_hour = atoi(arg1), atoi(argument)
        send_to_char("Shop hours set.\n\r", ch)
        return True
    if str_cmp(command, "profit"):
        if arg1 == "" or not is_number(arg1) or argument == "" or not is_number(argument):
            send_to_char("Syntax:  shop profit [#xbuying%] [#xselling%]\n\r", ch)
            return False
        if p.shop is None:
            send_to_char(_NO_SHOP, ch)
            return False
        p.shop.profit_buy, p.shop.profit_sell = atoi(arg1), atoi(argument)
        send_to_char("Shop profit set.\n\r", ch)
        return True
    if str_cmp(command, "type"):
        if arg1 == "" or not is_number(arg1) or argument == "":
            send_to_char("Syntax:  shop type [#x0-4] [item type]\n\r", ch)
            return False
        if atoi(arg1) >= C.MAX_TRADE:
            send_to_char("MEdit:  May sell %d items max.\n\r" % C.MAX_TRADE, ch)
            return False
        if p.shop is None:
            send_to_char(_NO_SHOP, ch)
            return False
        value = flag_value(F.TYPE_FLAGS, argument)
        if value == C.NO_FLAG:
            send_to_char("MEdit:  That type of item is not known.\n\r", ch)
            return False
        if atoi(arg1) < 0:
            raise CWouldCrash("olc_act.c medit_shop: shop type with a negative slot writes before buy_type")
        types = list(p.shop.buy_type)
        types[atoi(arg1)] = value
        p.shop = replace(p.shop, buy_type=tuple(types))
        send_to_char("Shop type set.\n\r", ch)
        return True
    if str_prefix(command, "assign"):  # "shop assign && shop delete by Phoenix"
        if p.shop is not None:
            send_to_char("Mob already has a shop assigned to it.\n\r", ch)
            return False
        p.shop = new_shop()
        p.shop.keeper = p.vnum
        send_to_char("New shop assigned to mobile.\n\r", ch)
        return True
    if str_prefix(command, "remove"):
        if p.shop is None:
            raise CWouldCrash("olc_act.c medit_shop: shop remove with no shop walks shop_first with a NULL shop")
        free_shop(p.shop)
        p.shop = None
        send_to_char("Mobile is no longer a shopkeeper.\n\r", ch)
        return True
    medit_shop(ch, "")
    return False


def _mob_flag(ch, argument: str, table, field: str, done: str, syntax: str, toggle: bool = True) -> bool:
    from quickmud.olc.bits import flag_value

    if argument != "":
        value = flag_value(table, argument)
        if value != C.NO_FLAG:
            p = _mob(ch)
            setattr(p, field, getattr(p, field) ^ value if toggle else value)
            send_to_char(done, ch)
            return True
    send_to_char(syntax, ch)
    return False


# C: olc_act.c medit_sex
def medit_sex(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.SEX_FLAGS, "sex", "Sex set.\n\r",
                     "Syntax: sex [sex]\n\rType '? sex' for a list of flags.\n\r", toggle=False)


# C: olc_act.c medit_act
def medit_act(ch, argument: str) -> bool:
    if _mob_flag(ch, argument, F.ACT_FLAGS, "act", "Act flag toggled.\n\r",
                 "Syntax: act [flag]\n\rType '? act' for a list of flags.\n\r"):
        _mob(ch).act |= C.ACT_IS_NPC
        return True
    return False


# C: olc_act.c medit_affect
def medit_affect(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.AFFECT_FLAGS, "affected_by", "Affect flag toggled.\n\r",
                     "Syntax: affect [flag]\n\rType '? affect' for a list of flags.\n\r")


# C: olc_act.c medit_ac
def medit_ac(ch, argument: str) -> bool:
    """ac pierce [bash [slash [exotic]]]: the ones left out keep their values."""
    p = _mob(ch)
    while argument != "":  # "So that I can use break and send the syntax in one place"
        argument, arg = one_argument(argument)
        if not is_number(arg):
            break
        values = [atoi(arg)]
        argument, arg = one_argument(argument)
        bad = False
        for k in (C.AC_BASH, C.AC_SLASH, C.AC_EXOTIC):
            if arg != "":
                if not is_number(arg):
                    bad = True
                    break
                values.append(atoi(arg))
                if k != C.AC_EXOTIC:
                    argument, arg = one_argument(argument)
            else:
                values.append(p.ac[k])
        if bad:
            break
        p.ac = tuple(values)
        send_to_char("Ac set.\n\r", ch)
        return True
    send_to_char("Syntax:  ac [ac-pierce [ac-bash [ac-slash [ac-exotic]]]]\n\r"
                 "help MOB_AC  gives a list of reasonable ac-values.\n\r", ch)
    return False


# C: olc_act.c medit_form
def medit_form(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.FORM_FLAGS, "form", "Form toggled.\n\r",
                     "Syntax: form [flags]\n\rType '? form' for a list of flags.\n\r")


# C: olc_act.c medit_part
def medit_part(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.PART_FLAGS, "parts", "Parts toggled.\n\r",
                     "Syntax: part [flags]\n\rType '? part' for a list of flags.\n\r")


# C: olc_act.c medit_imm
def medit_imm(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.IMM_FLAGS, "imm_flags", "Immunity toggled.\n\r",
                     "Syntax: imm [flags]\n\rType '? imm' for a list of flags.\n\r")


# C: olc_act.c medit_res
def medit_res(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.RES_FLAGS, "res_flags", "Resistance toggled.\n\r",
                     "Syntax: res [flags]\n\rType '? res' for a list of flags.\n\r")


# C: olc_act.c medit_vuln
def medit_vuln(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.VULN_FLAGS, "vuln_flags", "Vulnerability toggled.\n\r",
                     "Syntax: vuln [flags]\n\rType '? vuln' for a list of flags.\n\r")


# C: olc_act.c medit_material
def medit_material(ch, argument: str) -> bool:
    return _mob_text(ch, argument, "material", "Syntax:  material [string]\n\r", "Material set.\n\r")


# C: olc_act.c medit_off
def medit_off(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.OFF_FLAGS, "off_flags", "Offensive behaviour toggled.\n\r",
                     "Syntax: off [flags]\n\rType '? off' for a list of flags.\n\r")


# C: olc_act.c medit_size
def medit_size(ch, argument: str) -> bool:
    return _mob_flag(ch, argument, F.SIZE_FLAGS, "size", "Size set.\n\r",
                     "Syntax: size [size]\n\rType '? size' for a list of sizes.\n\r", toggle=False)


def _dice_parts(argument: str) -> tuple[str, str, str]:
    """The three numbers of "2d6+10" as the C cuts them: a run of digits, then everything up to the next digit is
    dropped, twice; the third run ends at the first non-digit."""
    def run(s, k):
        start = k
        while k < len(s) and "0" <= s[k] <= "9":
            k += 1
        return s[start:k], k

    def skip(s, k):
        while k < len(s) and not ("0" <= s[k] <= "9"):
            k += 1
        return k

    num, k = run(argument, 0)
    k = skip(argument, k)
    kind, k = run(argument, k)
    k = skip(argument, k)
    bonus, _ = run(argument, k)
    return num, kind, bonus


def _dice(ch, argument: str, field: str, syntax: str, done: str) -> bool:
    if argument == "":
        send_to_char(syntax, ch)
        return False
    num, kind, bonus = _dice_parts(argument)
    if (not is_number(num) or atoi(num) < 1 or not is_number(kind) or atoi(kind) < 1
            or not is_number(bonus) or atoi(bonus) < 0):
        send_to_char(syntax, ch)
        return False
    setattr(_mob(ch), field, (atoi(num), atoi(kind), atoi(bonus)))
    send_to_char(done, ch)
    return True


# C: olc_act.c medit_hitdice
def medit_hitdice(ch, argument: str) -> bool:
    return _dice(ch, argument, "hit", "Syntax:  hitdice <number> d <type> + <bonus>\n\r", "Hitdice set.\n\r")


# C: olc_act.c medit_manadice
def medit_manadice(ch, argument: str) -> bool:
    return _dice(ch, argument, "mana", "Syntax:  manadice <number> d <type> + <bonus>\n\r", "Manadice set.\n\r")


# C: olc_act.c medit_damdice
def medit_damdice(ch, argument: str) -> bool:
    return _dice(ch, argument, "damage", "Syntax:  damdice <number> d <type> + <bonus>\n\r", "Damdice set.\n\r")


# C: olc_act.c medit_race
def medit_race(ch, argument: str) -> bool:
    """The race, and its flags added (never taken away: the old race's stay)."""
    from quickmud.data.races import RACE_TABLE
    from quickmud.world.lookup import race_lookup

    if argument != "":
        race = race_lookup(argument)
        if race != 0:
            p = _mob(ch)
            rt = RACE_TABLE[race]
            p.race = race
            p.act |= rt.act
            p.affected_by |= rt.aff
            p.off_flags |= rt.off
            p.imm_flags |= rt.imm
            p.res_flags |= rt.res
            p.vuln_flags |= rt.vuln
            p.form |= rt.form
            p.parts |= rt.parts
            send_to_char("Race set.\n\r", ch)
            return True
    if argument[:1] == "?":
        send_to_char("Available races are:", ch)
        for race, rt in enumerate(RACE_TABLE):
            if race % 3 == 0:  # non-negative: an index
                send_to_char("\n\r", ch)
            send_to_char(" %-15s" % rt.name, ch)
        send_to_char("\n\r", ch)
        return False
    send_to_char("Syntax:  race [race]\n\rType 'race ?' for a list of races.\n\r", ch)
    return False


# C: olc_act.c medit_position
def medit_position(ch, argument: str) -> bool:
    from quickmud.olc.bits import flag_value

    argument, arg = one_argument(argument)
    for letter, word, field, done in (("s", "start", "start_pos", "Start position set.\n\r"),
                                      ("d", "default", "default_pos", "Default position set.\n\r")):
        if arg[:1] in (letter, upper(letter)) and str_prefix(arg, word):
            value = flag_value(F.POSITION_FLAGS, argument)
            if value != C.NO_FLAG:
                setattr(_mob(ch), field, value)
                send_to_char(done, ch)
                return True
    send_to_char("Syntax:  position [start/default] [position]\n\rType '? position' for a list of positions.\n\r", ch)
    return False


# C: olc_act.c medit_gold
def medit_gold(ch, argument: str) -> bool:
    return _mob_number(ch, argument, "wealth", "Syntax:  wealth [number]\n\r", "Wealth set.\n\r")


# C: olc_act.c medit_hitroll
def medit_hitroll(ch, argument: str) -> bool:
    return _mob_number(ch, argument, "hitroll", "Syntax:  hitroll [number]\n\r", "Hitroll set.\n\r")


# C: olc_act.c medit_group
def medit_group(ch, argument: str) -> bool:
    """group <number>, or group show <number>: the mobs in a group, by vnum (the C looks at vnums 0 to 65535)."""
    from quickmud.olc.save import _s

    p = _mob(ch)
    if argument == "":
        send_to_char("Syntax: group [number]\n\r", ch)
        send_to_char("        group show [number]\n\r", ch)
        return False
    if is_number(argument):
        p.group = atoi(argument)
        send_to_char("Group set.\n\r", ch)
        return True
    argument, arg = one_argument(argument)
    if arg == "show" and is_number(argument):
        if atoi(argument) == 0:
            send_to_char("Are you crazy?\n\r", ch)
            return False
        index = _game().index
        found = [m for v, m in sorted(index.mobs.items()) if 0 <= v < 65536 and m.group == atoi(argument)]
        if found:
            page_to_char("".join("[%5d] %s\n\r" % (m.vnum, _s(m.player_name)) for m in found), ch)
        else:
            send_to_char("No mobs in that group.\n\r", ch)
        return False
    return False


# C: olc_act.c medit_addmprog
def medit_addmprog(ch, argument: str) -> bool:
    """addmprog <vnum> <trigger> <phrase>: the phrase is one word, lower-cased (one_argument)."""
    from quickmud.data.mobprogs import MPROG_FLAGS
    from quickmud.olc.bits import flag_value
    from quickmud.world.index import MobProgRef

    p = _mob(ch)
    argument, num = one_argument(argument)
    argument, trigger = one_argument(argument)
    argument, phrase = one_argument(argument)
    if not is_number(num) or trigger == "" or phrase == "":
        send_to_char("Syntax:   addmprog [vnum] [trigger] [phrase]\n\r", ch)
        return False
    value = flag_value(MPROG_FLAGS, trigger)
    if value == C.NO_FLAG:
        send_to_char("Valid flags are:\n\r", ch)
        show_help(ch, "mprog")
        return False
    code = _game().index.get_mprog_index(atoi(num))
    if code is None:
        send_to_char("No such MOBProgram.\n\r", ch)
        return False
    p.mprog_flags |= value
    p.mprogs.insert(0, MobProgRef(value, atoi(num), phrase, code))
    send_to_char("Mprog Added.\n\r", ch)
    return True


# C: olc_act.c medit_delmprog
def medit_delmprog(ch, argument: str) -> bool:
    """Remove mob program number n (from 0, as show lists them), and its trigger's bit, even when another program
    still has that trigger."""
    p = _mob(ch)
    _, mprog = one_argument(argument)
    if not is_number(mprog) or mprog == "":
        send_to_char("Syntax:  delmprog [#mprog]\n\r", ch)
        return False
    value = atoi(mprog)
    if value < 0:
        send_to_char("Only non-negative mprog-numbers allowed.\n\r", ch)
        return False
    if not p.mprogs:
        send_to_char("MEdit:  Non existant mprog.\n\r", ch)
        return False
    if value >= len(p.mprogs):
        send_to_char("No such mprog.\n\r", ch)
        return False
    gone = p.mprogs.pop(value)
    p.mprog_flags &= ~gone.trig_type
    send_to_char("Mprog removed.\n\r", ch)
    return True


# C: olc_act.c redit_mshow
def redit_mshow(ch, argument: str) -> bool:
    """A mob prototype shown as medit's show shows it; pEdit is then the room (which redit never reads)."""
    if argument == "":
        send_to_char("Syntax:  mshow <vnum>\n\r", ch)
        return False
    if not is_number(argument):
        send_to_char("REdit: Must be a number.\n\r", ch)
        return False
    p = _game().index.get_mob_index(atoi(argument))
    if p is None:
        send_to_char("REdit:  That mobile does not exist.\n\r", ch)
        return False
    ch.desc.pEdit = p
    medit_show(ch, argument)
    ch.desc.pEdit = ch.in_room
    return False
