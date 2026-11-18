"""Output: the colour codes, a connection's output buffer, and the functions that fill and flush it.

Ported line by line from comm.c. The "{x" colour codes are turned into ANSI escapes for a character with
PLR_COLOUR, or a connection with ANSI on, and stripped otherwise. A "{" at the very end of a string makes the C
read past the end of it (undefined behaviour); here it ends the string, and the oracle's cases avoid it.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import os
import sys

from charm.core.errors import CWouldCrash
from charm.core.log import bug
from charm.data import constants as C
from charm.net.descriptor import Descriptor, ch_of

GO_AHEAD = "\xff\xf9"  # go_ahead_str: IAC GA

_FIXED = {
    "x": C.CLEAR, "b": C.C_BLUE, "c": C.C_CYAN, "g": C.C_GREEN, "m": C.C_MAGENTA, "r": C.C_RED, "w": C.C_WHITE,
    "y": C.C_YELLOW, "B": C.C_B_BLUE, "C": C.C_B_CYAN, "G": C.C_B_GREEN, "M": C.C_B_MAGENTA, "R": C.C_B_RED,
    "W": C.C_B_WHITE, "Y": C.C_B_YELLOW, "D": C.C_D_GREY, "*": "\a", "/": "\n\r", "-": "~", "{": "{",
}
# The personal codes: each is a (bright, colour, beep) triple in the player's PC_DATA.
_PERSONAL = {
    "p": "prompt", "s": "room_title", "S": "room_text", "d": "gossip", "9": "gossip_text", "Z": "wiznet",
    "o": "room_exits", "O": "room_things", "i": "immtalk_text", "I": "immtalk_type", "2": "fight_yhit",
    "3": "fight_ohit", "4": "fight_thit", "5": "fight_skill", "1": "fight_death", "6": "say", "7": "say_text",
    "k": "tell", "K": "tell_text", "l": "reply", "L": "reply_text", "n": "gtell_text", "N": "gtell_type",
    "a": "auction", "A": "auction_text", "q": "question", "Q": "question_text", "f": "answer", "F": "answer_text",
    "e": "music", "E": "music_text", "h": "quote", "H": "quote_text", "j": "info",
}


# C: comm.c colour
def colour(kind: str, ch) -> str:
    """The escape for one colour code ("" for a mob). kind "\\0" is the end of the string, which the C passes
    when a "{" is the last character: it gets the default, CLEAR."""
    if ch is not None and ch.is_npc:
        return ""
    if kind in _PERSONAL:
        col = ch.pcdata if ch is not None else None
        if col is None:
            raise CWouldCrash(f"comm.c colour: personal code '{{{kind}' with no PC_DATA (NULL dereference)")
        bright, hue, beep = getattr(col, _PERSONAL[kind])
        return f"\x1b[{bright};3{hue}m" + ("\a" if beep else "")
    return _FIXED.get(kind, C.CLEAR)


def _convert(txt: str, ch, colouring: bool, keep_newline_after_brace: bool = False) -> str:
    out: list[str] = []
    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c == "{":
            i += 1
            if i >= n:  # the C reads past the end here; stop instead
                if colouring:
                    out.append(colour("\0", ch))
                break
            if colouring and not (keep_newline_after_brace and txt[i] == "\n"):
                out.append(colour(txt[i], ch))
                i += 1
                continue
            if not colouring:
                i += 1
                continue
            c = txt[i]  # colourconv: "{" then a newline keeps the newline
        out.append(c)
        i += 1
    return "".join(out)


# C: comm.c colourconv
def colourconv(txt: str, ch) -> str | None:
    """None where the C leaves its buffer untouched (no character, connection or text)."""
    if ch is None or ch.desc is None or txt is None:
        return None
    return _convert(txt, ch, bool(ch.act & C.PLR_COLOUR), keep_newline_after_brace=True)


# C: comm.c write_to_buffer
def write_to_buffer(d: Descriptor, txt: str, length: int = 0) -> None:
    if length <= 0:
        length = len(txt.split("\0", 1)[0])  # strlen
    # strncpy: up to length characters, stopping at a NUL and padding with NULs to length
    chunk = txt.split("\0", 1)[0][:length].ljust(length, "\0")
    if d.outtop == 0 and not d.fcommand:  # initial \n\r if needed
        d.outbuf = "\n\r"
    while d.outtop + length >= d.outsize:  # expand the buffer as needed
        if d.outsize >= 32000:
            bug("Buffer overflow. Closing.\n\r", 0)
            from charm.net.server import close_socket
            close_socket(d)
            return
        d.outsize *= 2
    d.outbuf += chunk


# C: comm.c write_to_descriptor
def write_to_descriptor(sock, txt: str, length: int = 0) -> bool:
    data = txt.encode("latin-1")
    if length <= 0:
        data = data.split(b"\0", 1)[0]
        length = len(data)
    i = 0
    while i < length:
        block = min(length - i, 4096)
        try:
            n = sock.send(data[i:i + block])
        except OSError as e:
            print(f"Write_to_descriptor: {os.strerror(e.errno) if e.errno else e}", file=sys.stderr)
            return False
        i += n
    return True


# C: comm.c send_to_desc
def send_to_desc(txt: str | None, d: Descriptor | None) -> None:
    if txt is not None and d is not None:
        write_to_buffer(d, _convert(txt, None, d.ansi is True))


# C: comm.c send_to_char
def send_to_char(txt: str | None, ch) -> None:
    if txt is not None and ch.desc is not None:
        write_to_buffer(ch.desc, _convert(txt, ch, bool(ch.act & C.PLR_COLOUR)))


# C: comm.c send_to_char_bw
def send_to_char_bw(txt: str | None, ch) -> None:
    if txt is not None and ch.desc is not None:
        write_to_buffer(ch.desc, txt)


# C: comm.c page_to_char
def page_to_char(txt: str | None, ch) -> None:
    if txt is not None and ch.desc is not None:
        d = ch.desc
        d.showstr_head = _convert(txt, ch, bool(ch.act & C.PLR_COLOUR))
        d.showstr_point = 0
        show_string(d, "")


# C: comm.c show_string
def show_string(d: Descriptor, text: str) -> None:
    from charm.commands.interp import one_argument

    _, arg = one_argument(text)
    if arg != "":
        d.showstr_head = None
        d.showstr_point = None
        return
    show_lines = d.character.lines if d.character is not None else 0
    s, p = d.showstr_head, d.showstr_point
    lines, toggle, buf = 0, 1, []
    while True:
        c = s[p] if p < len(s) else "\0"
        if c in "\n\r":
            toggle = -toggle  # flipped only on a newline or carriage return, as the C's && short-circuits
        if c in "\n\r" and toggle < 0:
            lines += 1
        elif c == "\0" or (show_lines > 0 and lines >= show_lines):
            write_to_buffer(d, "".join(buf))
            q = p
            while q < len(s) and s[q] in " \t\n\v\f\r":
                q += 1
            if q >= len(s):
                d.showstr_head = None
                d.showstr_point = None
            else:
                d.showstr_point = p
            return
        buf.append(c)
        p += 1


_WOUNDS = ((100, "is in excellent condition."), (90, "has a few scratches."),
           (75, "has some small wounds and bruises."), (50, "has quite a few wounds."),
           (30, "has some big nasty wounds and scratches."), (15, "looks pretty hurt."),
           (0, "is in awful condition."))


# C: comm.c process_output
def process_output(d: Descriptor, prompt: bool) -> bool:
    from charm.core.cint import c_div
    from charm.entities.handler import can_see
    from charm.net.prompt import bust_a_prompt

    game_down = d.game is not None and d.game.merc_down
    if not game_down:
        if d.showstr_point is not None:
            write_to_buffer(d, "[Hit Return to continue]\n\r")
        elif prompt and d.pString is not None and d.connected == C.CON_PLAYING:
            write_to_buffer(d, "> ", 2)
        elif prompt and d.connected == C.CON_PLAYING:
            ch = d.character
            victim = ch.fighting
            if victim is not None and can_see(ch, victim):  # battle prompt
                percent = c_div(victim.hit * 100, victim.max_hit) if victim.max_hit > 0 else -1
                wound = next((w for limit, w in _WOUNDS if percent >= limit), "is bleeding to death.")
                buf = f"{victim.short_descr if victim.is_npc else victim.name} {wound} \n\r"
                buf = buf[0].upper() + buf[1:] if "a" <= buf[0] <= "z" else buf
                write_to_buffer(d, colourconv(buf, ch_of(d)) or "")
            ch = ch_of(d)
            if not ch.comm & C.COMM_COMPACT:
                write_to_buffer(d, "\n\r", 2)
            if ch.comm & C.COMM_PROMPT:
                bust_a_prompt(d.character)
            if ch.comm & C.COMM_TELNET_GA:
                write_to_buffer(d, GO_AHEAD)

    if d.outtop == 0:  # short-circuit if nothing to write
        return True
    if d.snoop_by is not None:  # snoop-o-rama
        if d.character is not None:
            write_to_buffer(d.snoop_by, d.character.name)
        write_to_buffer(d.snoop_by, "> ", 2)
        write_to_buffer(d.snoop_by, d.outbuf, d.outtop)
    ok = write_to_descriptor(d.sock, d.outbuf, d.outtop)
    d.outbuf = ""
    return ok
