"""string.c: OLC's string editor and string helpers.

A connection in the string editor has a pString: the (object, attribute) pair it's editing, where the C has a
char ** (&pRoom->description). Every line it types then goes to string_add instead of the interpreter.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/string.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from charm.core.errors import CWouldCrash
from charm.core.strings import upper
from charm.data import constants as C


def _game():
    from charm.entities import game as game_module

    return game_module.current


def _fits(s: str, what: str) -> str:
    if len(s) >= C.MAX_STRING_LENGTH:
        raise CWouldCrash(f"string.c {what}: {len(s)} characters overflow its {C.MAX_STRING_LENGTH}-byte buffer")
    return s


# C: string.c string_replace
def string_replace(orig: str, old: str, new: str) -> str:
    """orig with its first old (a plain substring, as strstr finds it) replaced by new."""
    _fits(orig, "string_replace")
    i = orig.find(old)
    if i < 0:
        return orig
    return _fits(orig[:i] + new + orig[i + len(old):], "string_replace")


# C: string.c string_unpad
def string_unpad(argument: str) -> str:
    """Without leading and trailing spaces (only ' ', not other blanks)."""
    return _fits(argument.lstrip(" "), "string_unpad").rstrip(" ")


# C: string.c string_proper
def string_proper(argument: str) -> str:
    """Each word's first letter upper-cased (words split on ' ' only)."""
    out, start = [], True
    for c in argument:
        if c == " ":
            start = True
            out.append(c)
        else:
            out.append(upper(c) if start else c)
            start = False
    return "".join(out)


def _get(d) -> str | None:
    obj, attr = d.pString
    return getattr(obj, attr)


def _set(d, value: str) -> None:
    obj, attr = d.pString
    setattr(obj, attr, value)


# C: string.c string_append
def string_append(ch, target) -> None:
    """Put ch's connection in the string editor on target, an (object, attribute) pair."""
    from charm.net.output import send_to_char

    send_to_char("-=======- Entering APPEND Mode -========-\n\r", ch)
    send_to_char("    Type .h on a new line for help\n\r", ch)
    send_to_char(" Terminate with a ~ or @ on a blank line.\n\r", ch)
    send_to_char("-=======================================-\n\r", ch)
    obj, attr = target
    if getattr(obj, attr) is None:
        setattr(obj, attr, "")
    send_to_char(numlines(getattr(obj, attr)), ch)
    ch.desc.pString = target


# C: string.c string_add
def string_add(ch, argument: str) -> None:
    """A line typed in the string editor: a dot command, the end (@; a ~ was already made a - by smash_tilde, so it
    never ends it), or one more line of text. Ending a mob program's code gives it to every mob whose programs use
    that vnum (they hold a copy of the code, as the C's share its pointer)."""
    from charm.commands.interp import one_argument
    from charm.core.strings import atoi, smash_tilde, str_cmp
    from charm.net.output import send_to_char
    from charm.olc import ED_MPCODE

    d = ch.desc
    argument = smash_tilde(argument)  # "Thanks to James Seng"
    if argument[:1] == ".":
        argument, arg1 = one_argument(argument)
        argument, arg2 = first_arg(argument, False)
        tmparg3 = argument
        argument, arg3 = first_arg(argument, False)
        if str_cmp(arg1, ".c"):
            send_to_char("String cleared.\n\r", ch)
            _set(d, "")
        elif str_cmp(arg1, ".s"):
            send_to_char("String so far:\n\r", ch)
            send_to_char(numlines(_get(d)), ch)
        elif str_cmp(arg1, ".r"):
            if arg2 == "":
                send_to_char("usage:  .r \"old string\" \"new string\"\n\r", ch)
                return
            _set(d, string_replace(_get(d), arg2, arg3))
            send_to_char("'%s' replaced with '%s'.\n\r" % (arg2, arg3), ch)
        elif str_cmp(arg1, ".f"):
            _set(d, format_string(_get(d)))
            send_to_char("String formatted.\n\r", ch)
        elif str_cmp(arg1, ".ld"):
            _set(d, string_linedel(_get(d), atoi(arg2)))
            send_to_char("Line deleted.\n\r", ch)
        elif str_cmp(arg1, ".li"):
            _set(d, string_lineadd(_get(d), tmparg3, atoi(arg2)))
            send_to_char("Line inserted.\n\r", ch)
        elif str_cmp(arg1, ".lr"):
            _set(d, string_linedel(_get(d), atoi(arg2)))
            _set(d, string_lineadd(_get(d), tmparg3, atoi(arg2)))
            send_to_char("Line replaced.\n\r", ch)
        elif str_cmp(arg1, ".h"):
            for line in ("Sedit help (commands on blank line):   \n\r",
                         ".r 'old' 'new'   - replace a substring \n\r",
                         "                   (requires '', \"\") \n\r",
                         ".h               - get help (this info)\n\r",
                         ".s               - show string so far  \n\r",
                         ".f               - (word wrap) string  \n\r",
                         ".c               - clear string so far \n\r",
                         ".ld <num>        - delete line number <num>\n\r",
                         ".li <num> <str>  - insert <str> at line <num>\n\r",
                         ".lr <num> <str>  - replace line <num> with <str>\n\r",
                         "@                - end string          \n\r"):
                send_to_char(line, ch)
        else:
            send_to_char("SEdit:  Invalid dot command.\n\r", ch)
        return
    if argument[:1] in ("~", "@"):
        if d.editor == ED_MPCODE:  # "for the mobprogs"
            from charm.olc.save import _hash_order

            mpc = d.pEdit
            if mpc is not None:
                for mob in _hash_order(_game().index.mobs.values()):
                    for prog in mob.mprogs:
                        if prog.vnum == mpc.vnum:
                            send_to_char("Editting mob %d.\n\r" % mob.vnum, ch)
                            prog.code = mpc.code
        d.pString = None
        return
    current = _get(d)
    _fits(current, "string_add")  # strcpy (buf, *ch->desc->pString)
    # "Truncate strings to MAX_STRING_LENGTH."
    if len(current) + len(argument) >= C.MAX_STRING_LENGTH - 4:
        send_to_char("String too long, last line skipped.\n\r", ch)
        d.pString = None  # "Force character out of editing mode."
        return
    _set(d, current + argument + "\n\r")


class _Buf:
    """format_string's first buffer: the C reads back from i - 1, i - 2 and i - 3, and before the start of the
    buffer (undefined) when there are fewer characters than that."""

    def __init__(self):
        self.c: list[str] = []

    def at(self, k: int) -> str:
        if k < 0:
            raise CWouldCrash("string.c format_string: reads before the start of its buffer")
        return self.c[k] if k < len(self.c) else "\0"

    def put(self, k: int, ch: str) -> None:
        while len(self.c) <= k:
            self.c.append("\0")
        self.c[k] = ch


# C: string.c format_string
def format_string(oldstring: str) -> str:
    """Word-wrap a string: runs of spaces and line ends become one space, a sentence's end gets two spaces after it
    and capitalises what follows, then lines are broken at a space before column 77 (73 on the first line)."""
    from charm.core.log import bug

    xbuf, i, cap = _Buf(), 0, True
    s, n = oldstring, len(oldstring)
    r = 0
    while r < n:
        c = s[r]
        nxt = s[r + 1] if r + 1 < n else "\0"
        if c == "\n":
            if xbuf.at(i - 1) != " ":
                xbuf.put(i, " ")
                i += 1
        elif c == "\r":
            pass
        elif c == " ":
            if xbuf.at(i - 1) != " ":
                xbuf.put(i, " ")
                i += 1
        elif c == ")":
            if xbuf.at(i - 1) == " " and xbuf.at(i - 2) == " " and xbuf.at(i - 3) in ".?!":
                xbuf.put(i - 2, c)
                xbuf.put(i - 1, " ")
                xbuf.put(i, " ")
                i += 1
            else:
                xbuf.put(i, c)
                i += 1
        elif c in ".?!":
            if xbuf.at(i - 1) == " " and xbuf.at(i - 2) == " " and xbuf.at(i - 3) in ".?!":
                xbuf.put(i - 2, c)
                if nxt != '"':
                    xbuf.put(i - 1, " ")
                    xbuf.put(i, " ")
                    i += 1
                else:
                    xbuf.put(i - 1, '"')
                    xbuf.put(i, " ")
                    xbuf.put(i + 1, " ")
                    i += 2
                    r += 1
            else:
                xbuf.put(i, c)
                if nxt != '"':
                    xbuf.put(i + 1, " ")
                    xbuf.put(i + 2, " ")
                    i += 3
                else:
                    xbuf.put(i + 1, '"')
                    xbuf.put(i + 2, " ")
                    xbuf.put(i + 3, " ")
                    i += 4
                    r += 1
            cap = True
        else:
            if cap:
                cap = False
                c = upper(c)
            xbuf.put(i, c)
            i += 1
        if i >= C.MAX_STRING_LENGTH:
            raise CWouldCrash("string.c format_string: overflows its buffer")
        r += 1
    rdesc = "".join(xbuf.c[:i])  # xbuf[i] = 0; strcpy (xbuf2, xbuf)
    out = ""
    while True:
        if len(rdesc) < 77:
            break
        i = 76 if out else 73
        while i and rdesc[i] != " ":
            i -= 1
        if i:
            out += rdesc[:i] + "\n\r"
            rdesc = rdesc[i + 1:].lstrip(" ")
        else:
            bug("No spaces", 0)
            out += rdesc[:75] + "-\n\r"
            rdesc = rdesc[76:]  # the character at 75 is lost
    # The C's loop to trim trailing blanks starts on the terminator, so it trims nothing.
    out += rdesc
    if len(out) < 2:
        raise CWouldCrash("string.c format_string: a result under two characters is read before its start")
    if out[-2] != "\n":
        out += "\n\r"
    return _fits(out, "format_string")


# C: string.c first_arg
def first_arg(argument: str, fcase: bool) -> tuple[str, str]:
    """(the rest, the first argument): quotes (' " %) or parentheses group words; fcase lower-cases it."""
    from charm.core.strings import lower

    p, n = 0, len(argument)
    while p < n and argument[p] == " ":
        p += 1
    end = " "
    if p < n and argument[p] in "'\"%(":
        end = ")" if argument[p] == "(" else argument[p]
        p += 1
    word = []
    while p < n:
        if argument[p] == end:
            p += 1
            break
        word.append(lower(argument[p]) if fcase else argument[p])
        p += 1
    while p < n and argument[p] == " ":
        p += 1
    return argument[p:], "".join(word)


# C: string.c string_linedel
def string_linedel(string: str, line: int) -> str:
    """Without line number `line` (lines end in "\\n", with an "\\r" after it kept with it)."""
    out, cnt, p, n = [], 1, 0, len(string)
    while p < n:
        c = string[p]
        if cnt != line:
            out.append(c)
        if c == "\n":
            if p + 1 < n and string[p + 1] == "\r":
                p += 1
                if cnt != line:
                    out.append(string[p])
            cnt += 1
        p += 1
    return _fits("".join(out), "string_linedel")


# C: string.c string_lineadd
def string_lineadd(string: str, newstr: str, line: int) -> str:
    """newstr, and a line end, put in as line number `line`: before the line that has that number now, or at the
    end if it's one past the last line; any other number changes nothing."""
    out, cnt, done, p, n = [], 1, False, 0, len(string)
    while p < n or (not done and cnt == line):
        if cnt == line and not done:
            out.append(newstr + "\n\r")
            cnt += 1
            done = True
        if p >= n:  # the terminator: copied, and then the loop ends
            break
        c = string[p]
        out.append(c)
        if c == "\n":
            if p + 1 < n and string[p + 1] == "\r":
                p += 1
                out.append(string[p])
            cnt += 1
        p += 1
    return _fits("".join(out), "string_lineadd")


# C: string.c merc_getline
def merc_getline(string: str) -> tuple[str, str]:
    """(the rest, the first line without its "\\n" or "\\n\\r")."""
    k = string.find("\n")
    if k < 0:
        return "", string
    return string[k + (2 if string[k + 1:k + 2] == "\r" else 1):], string[:k]


# C: string.c numlines
def numlines(string: str) -> str:
    """Each line numbered: " 1. text\\n\\r"."""
    out, cnt = [], 1
    while string:
        string, line = merc_getline(string)
        out.append("%2d. %s\n\r" % (cnt, line))
        cnt += 1
    return "".join(out)
