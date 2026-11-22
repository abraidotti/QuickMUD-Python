"""Character-level reader that mirrors ROM's ``fread_*`` functions (src/db.c).

Adapted from xania-explorer 90cfc79 areafile/reader.py; every function was re-checked against QuickMUD-Python's db.c, and
the ROM behaviour differs from Xania's in places (noted on each method). Positions behave like the C ``FILE *``:
``ungetc`` steps back one, so ``bug()``'s FILE/LINE numbers come out as the game prints them.

Fatal conditions (the C calls ``exit(1)``, or would hang or crash) raise AreaParseError. Conditions the C only
reports with ``bug()`` are recorded as Diagnostics.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quickmud.core.cint import int32, sh_int  # noqa: F401  (re-exported)

EOF = ""
_WS = " \t\n\r\v\f"  # C isspace() in the "C" locale


def isdigit(c: str) -> bool:
    return len(c) == 1 and "0" <= c <= "9"


def isalpha(c: str) -> bool:
    return len(c) == 1 and ("A" <= c <= "Z" or "a" <= c <= "z")


class AreaParseError(Exception):
    """A condition boot_db can't get past: ``exit(1)``, or a hang or crash the C would hit."""

    def __init__(self, message: str, file: str = "", line: int | None = None, log: list[str] | None = None):
        self.message = message
        self.file = file
        self.line = line
        self.log = log or []  # the bug() lines the game prints for this, if any
        where = f"{file}:{line}: " if file and line is not None else (f"{file}: " if file else "")
        super().__init__(where + message)


@dataclass(frozen=True)
class Diagnostic:
    """A ``bug()`` the game logs and carries on from.

    ``file``/``line`` are what bug() prints in its "[*****] FILE: x LINE: n" line, which it only prints while an
    area file is open (``fpArea``); fix_exits runs after, so its diagnostics have no file.
    """

    message: str
    file: str | None = None
    line: int | None = None

    def log_lines(self) -> list[str]:
        """Exactly what bug() writes to the log (without the timestamp)."""
        out = [f"[*****] FILE: {self.file} LINE: {self.line}"] if self.file is not None else []
        return out + [f"[*****] BUG: {self.message}"]

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.message}" if self.file else self.message


# C: db.c flag_convert
def flag_convert(letter: str) -> int:
    """``flag_convert`` (db.c:2790): A..Z -> 2^0..2^25, a..z -> 2^26..2^51, as a C long (64-bit)."""
    if "A" <= letter <= "Z":
        return 1 << (ord(letter) - ord("A"))
    if "a" <= letter <= "z":
        return 1 << (26 + ord(letter) - ord("a"))
    return 0


MAX_STRING = 1413120  # db.c's string space, in bytes
STRING_LINK = 8  # sizeof (char *): each boot string starts with a link to the next in its string_hash chain
MAX_STRING_LENGTH = 4608  # merc.h


class StringSpace:
    """db.c's string space while the world boots (fBootDb). fread_string and fread_string_eol keep each string
    once: one already there is shared (string_hash), and a new one takes a link, its text (with each "\\n" as
    "\\n\\r") and its terminator. memory's "Strings" line counts them. An empty string is str_empty, which takes
    nothing. Before each read the C checks there's room for one more of the longest strings, and stops the boot
    if there isn't."""

    def __init__(self):
        self.count = 0  # nAllocString
        self.used = 0  # sAllocString: top_string - string_space
        self._seen: set[str] = set()

    def check(self, r: "Reader") -> None:
        if self.used + STRING_LINK > MAX_STRING - MAX_STRING_LENGTH:
            raise r.error("Fread_string: MAX_STRING %d exceeded." % MAX_STRING)

    def keep(self, s: str | None) -> None:
        if not s or s in self._seen:
            return
        self._seen.add(s)
        self.count += 1
        self.used += STRING_LINK + len(s) + 1


class Reader:
    def __init__(self, text: str, filename: str = "<string>"):
        # Area files are LF in the repo; normalise CRLF defensively so a Windows checkout behaves like Linux.
        self.text = text.replace("\r\n", "\n")
        self.pos = 0
        self.filename = filename
        self.diagnostics: list[Diagnostic] = []
        self.space: StringSpace | None = None  # the boot's string space, when the game reads (not for tools)

    @classmethod
    def from_path(cls, path: Path) -> "Reader":
        # Raw bytes, as the C's getc() sees them: read_text() would turn a stray "\r" into a newline.
        return cls(path.read_bytes().decode("latin-1"), path.name)

    # -- primitives ---------------------------------------------------------
    def getc(self) -> str:
        if self.pos >= len(self.text):
            self.pos = len(self.text) + 1  # like EOF: a following ungetc lands back on the end
            return EOF
        c = self.text[self.pos]
        self.pos += 1
        return c

    def ungetc(self) -> None:
        self.pos -= 1

    @property
    def at_eof(self) -> bool:
        return self.pos >= len(self.text)

    # C: db.c bug
    def bug_line(self) -> int:
        """The LINE that ``bug()`` prints while an area file is open: how many lines start before the current
        position. The C counts them by reading from the start, a line at a time, with
        ``while (getc (fpArea) != '\n');``: if the position is past the file's last newline, that loop reads EOF
        forever and the game hangs, printing nothing more. (quickmud.core.log's bug is the rest of bug().)"""
        p = min(self.pos, len(self.text))
        if p > 0 and self.text.rfind("\n") + 1 < p:
            raise AreaParseError("bug() counts the lines up to here, and the last one has no newline: getc reads EOF "
                                 "forever and the game hangs", self.filename, self.line, log=[])
        return (1 if p > 0 else 0) + self.text.count("\n", 0, max(p - 1, 0))

    @property
    def line(self) -> int:
        """1-based line of the current position, for humans."""
        return self.text.count("\n", 0, min(self.pos, len(self.text))) + 1

    def error(self, message: str) -> AreaParseError:
        d = Diagnostic(message, self.filename, self.bug_line())
        return AreaParseError(message, self.filename, self.line, d.log_lines())

    def bug(self, message: str) -> None:
        self.diagnostics.append(Diagnostic(message, self.filename, self.bug_line()))

    def skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] in _WS:
            self.pos += 1

    # -- fread_* ports ------------------------------------------------------
    # C: db.c fread_letter
    def read_letter(self) -> str:
        """``fread_letter`` (db.c:2677): the next non-space character ("" at EOF)."""
        self.skip_ws()
        return self.getc()

    # C: db.c fread_number
    def read_number(self) -> int:
        """``fread_number`` (db.c:2695): optional sign, digits required (else fatal), ``a|b`` adds. Consumes one
        trailing space; any other terminator is pushed back."""
        self.skip_ws()
        c = self.getc()
        sign = False
        if c == "+":
            c = self.getc()
        elif c == "-":
            sign = True
            c = self.getc()
        if not isdigit(c):
            raise self.error("Fread_number: bad format.")
        n = 0
        while isdigit(c):
            n = int32(n * 10 + ord(c) - 48)
            c = self.getc()
        if sign:
            n = int32(-n)
        if c == "|":
            n = int32(n + self.read_number())
        elif c != " ":
            self.ungetc()
        return n

    # C: db.c fread_flag
    def read_flag(self) -> int:
        """``fread_flag`` (db.c:2743). Unlike Xania's, ROM's:

        - adds every letter, so a repeated letter counts twice ("AA" is A+A = B);
        - accepts a leading ``-`` that negates the whole value;
        - sums into a C ``int``, so ``f`` (2^31) wraps negative and ``g``..``z`` (2^32 and up) add nothing.
        """
        self.skip_ws()
        c = self.getc()
        negative = False
        if c == "-":
            negative = True
            c = self.getc()
        n = 0
        if not isdigit(c):
            while isalpha(c):
                n = int32(n + flag_convert(c))
                c = self.getc()
        while isdigit(c):
            n = int32(n * 10 + ord(c) - 48)
            c = self.getc()
        if c == "|":
            n = int32(n + self.read_flag())
        elif c != " ":
            self.ungetc()
        return -n if negative else n

    # C: db.c fread_string
    def read_string(self) -> str | None:
        """``fread_string`` (db.c:2822): text up to ``~``. The game turns ``\\n`` into ``\\n\\r`` and drops ``\\r``;
        this keeps plain ``\\n``. At EOF the game logs "Fread_string: EOF" and returns NULL, and so does this
        (None). Most loaders just store it; the ones that touch it crash (see Boot._text). With a string space,
        the string is kept there (StringSpace)."""
        if self.space is not None:
            self.space.check(self)
        self.skip_ws()
        end = self.text.find("~", self.pos)
        if end < 0:
            self.pos = len(self.text) + 1
            self.bug("Fread_string: EOF")
            return None
        s, self.pos = self.text[self.pos:end], end + 1
        s = s.replace("\r", "")
        if self.space is not None:
            self.space.keep(s.replace("\n", "\n\r"))
        return s

    # C: db.c fread_string_eol
    def read_string_eol(self) -> str:
        """``fread_string_eol`` (db.c:2926): rest of the line; the newline is consumed. EOF is fatal. With a string
        space, the string is kept there (StringSpace)."""
        if self.space is not None:
            self.space.check(self)
        self.skip_ws()
        if self.at_eof:
            raise self.error("Fread_string_eol  EOF")
        end = len(self.text)
        for i in range(self.pos, len(self.text)):
            if self.text[i] in "\n\r":
                end = i
                break
        else:
            raise self.error("Fread_string_eol  EOF")
        s, self.pos = self.text[self.pos:end], end + 1
        if self.space is not None:
            self.space.keep(s)
        return s

    # C: db.c fread_to_eol
    def read_to_eol(self) -> str:
        """``fread_to_eol`` (db.c:3029): skip to the end of the line and past any blank lines. Returns the skipped
        text (stripped), which in #RESETS is a human comment worth keeping. At EOF the C loops forever."""
        start = self.pos
        while True:
            c = self.getc()
            if c == EOF:
                raise self.error("fread_to_eol: end of file (the game would loop forever here)")
            if c in "\n\r":
                break
        rest = self.text[start:self.pos - 1]
        while True:
            c = self.getc()
            if c not in ("\n", "\r"):
                break
        self.ungetc()
        return rest.strip()

    # C: db.c fread_word
    def read_word(self) -> str:
        """``fread_word`` (db.c:3054): a whitespace-delimited word, or a quoted one if the *first* character is a
        quote (Xania's reader accepts a quote anywhere; ROM's doesn't). Words are capped at MAX_INPUT_LENGTH (256)
        characters; a longer one, or EOF, is fatal ("word too long": at EOF the C keeps reading EOF until then)."""
        self.skip_ws()
        c = self.getc()
        if c in ("'", '"'):
            end_char, word = c, []
        else:
            end_char, word = " ", [c]
            if c == EOF:
                raise self.error("Fread_word: word too long.")
        while len(word) < 256:
            c = self.getc()
            if c == EOF:
                raise self.error("Fread_word: word too long.")
            if (c in _WS) if end_char == " " else (c == end_char):
                if end_char == " ":
                    self.ungetc()
                return "".join(word)
            word.append(c)
        raise self.error("Fread_word: word too long.")
