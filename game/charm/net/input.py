"""Input: reading from a connection into its input buffer, and taking one command line out of it.

Ported line by line from comm.c, quirks included:
- only printable ASCII is kept
- a backspace removes the last character kept
- a line over MAX_INPUT_LENGTH - 2 characters is cut, with "Line too long.", and the rest of the buffer is lost
- an empty line becomes " "
- "!" repeats the last command
- 25 repeats of one command in a row count as spamming
- a NUL byte ends what's in the buffer, as the C's strlen does

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

import os
import sys

from charm.core.log import log_string
from charm.data import constants as C
from charm.net.descriptor import INBUF_SIZE, Descriptor
from charm.net.output import write_to_descriptor


# C: comm.c read_from_descriptor
def read_from_descriptor(d: Descriptor) -> bool:
    if d.incomm != "":  # hold horses if pending command already
        return True
    start = len(d.inbuf)
    if start >= INBUF_SIZE - 10:  # check for overflow
        log_string(f"{d.host} input overflow!")
        write_to_descriptor(d.sock, "\n\r*** PUT A LID ON IT!!! ***\n\r")
        return False
    while True:
        room = INBUF_SIZE - 10 - start
        try:
            data = d.sock.recv(room) if room > 0 else b""
        except BlockingIOError:
            break
        except OSError as e:
            print(f"Read_from_descriptor: {os.strerror(e.errno) if e.errno else e}", file=sys.stderr)
            return False
        if data:
            text = data.decode("latin-1")
            d.inbuf += text
            start += len(text)
            if text[-1] in "\n\r":
                break
        else:
            log_string("EOF encountered on read.")
            return False
    d.inbuf = d.inbuf.split("\0", 1)[0]  # everything from a NUL on is gone at the next strlen
    return True


def _printable(c: str) -> bool:
    return " " <= c <= "~"  # isascii && isprint


# C: comm.c read_from_buffer
def read_from_buffer(d: Descriptor) -> None:
    from charm.entities.handler import get_trust
    from charm.net.wiznet import wiznet

    if d.incomm != "":  # hold horses if pending command already
        return
    buf = d.inbuf
    for c in buf:  # look for at least one new line
        if c in "\n\r":
            break
    else:
        return

    k, comm = 0, []
    i = 0
    while buf[i] not in "\n\r":  # canonical input processing
        if k >= C.MAX_INPUT_LENGTH - 2:
            write_to_descriptor(d.sock, "Line too long.\n\r")
            while i < len(buf) and buf[i] not in "\n\r":  # skip the rest of the line
                i += 1
            buf = buf[:i] + "\n"  # inbuf[i] = '\n', inbuf[i + 1] = '\0': the rest of the buffer goes too
            break
        c = buf[i]
        if c == "\b" and k > 0:
            k -= 1
            comm.pop()
        elif _printable(c):
            comm.append(c)
            k += 1
        i += 1

    if k == 0:  # finish off the line
        comm.append(" ")
        k = 1
    d.incomm = "".join(comm)

    # deal with bozos with #repeat 1000 ...
    if k > 1 or d.incomm[0] == "!":
        if d.incomm[0] != "!" and d.incomm != d.inlast:
            d.repeat = 0
        else:
            d.repeat += 1
            if d.repeat >= 25 and d.character is not None and d.connected == C.CON_PLAYING:
                log_string(f"{d.host} input spamming!")
                game, ch = d.game, d.character
                wiznet(game, "Spam spam spam $N spam spam spam spam spam!", ch, None, C.WIZ_SPAM, 0,
                       get_trust(ch))
                wiznet(game, d.inlast if d.incomm[0] == "!" else d.incomm, ch, None, C.WIZ_SPAM, 0,
                       get_trust(ch))
                d.repeat = 0

    if d.incomm[0] == "!":  # do '!' substitution
        d.incomm = d.inlast
    else:
        d.inlast = d.incomm

    while i < len(buf) and buf[i] in "\n\r":  # shift the input buffer
        i += 1
    d.inbuf = buf[i:]
