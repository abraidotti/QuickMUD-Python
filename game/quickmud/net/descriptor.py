"""DESCRIPTOR_DATA: one connection, with its input and output buffers. And recycle.c's new_descriptor.

Text is a Python str in which each character is one byte of the C's (latin-1), so lengths and indexes match the
C's; it's encoded only at the socket.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/merc.h, src/recycle.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quickmud.data import constants as C

INBUF_SIZE = 4 * C.MAX_INPUT_LENGTH  # char inbuf[4 * MAX_INPUT_LENGTH]


@dataclass(eq=False)
class Descriptor:

    def __repr__(self) -> str:  # short: the dataclass default never ends (tests/test_reprs.py)
        name = self.character.name if self.character is not None else None
        return f"<Descriptor {self.fd} {name!r} connected={self.connected}>"

    sock: object = None  # a socket (send, recv, fileno, close)
    snoop_by: "Descriptor | None" = None
    character: object | None = None  # Char
    original: object | None = None  # Char
    ansi: bool = False
    host: str = ""
    connected: int = C.CON_GET_NAME
    fcommand: bool = False
    inbuf: str = ""
    incomm: str = ""
    inlast: str = ""
    repeat: int = 0
    outbuf: str = ""  # the first outtop bytes of the C's outbuf
    outsize: int = 2000
    showstr_head: str | None = None
    showstr_point: int | None = None  # an index into showstr_head (the C's pointer into it)
    pEdit: object | None = None  # OLC
    pString: object | None = None  # OLC
    editor: int = 0  # OLC
    game: object | None = field(default=None, repr=False)  # the Game it belongs to (for descriptor_list)
    closed: bool = field(default=False, repr=False)
    fd: int | None = field(default=None, repr=False)  # the C's descriptor number, where it isn't the socket's

    @property
    def outtop(self) -> int:
        return len(self.outbuf)

    @property
    def fileno(self) -> int:
        return self.fd if self.fd is not None else self.sock.fileno()


# C: recycle.c new_descriptor
def new_descriptor() -> Descriptor:
    return Descriptor(connected=C.CON_GET_NAME, outsize=2000)


def ch_of(d: Descriptor):
    """CH(d): the character behind the connection, the original one if it's switched into a mob."""
    return d.original if d.original is not None else d.character
