"""C integer behaviour: fixed-width wrapping, and division and modulo that truncate toward zero.

Python ints don't overflow and // floors, so every place the C game relies on int, sh_int or / with a negative
operand goes through these.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""


def int32(n):
    """n as a C int (32 bits, two's complement)."""
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def uint32(n):
    """n as a C unsigned int."""
    return n & 0xFFFFFFFF


def sh_int(n):
    """n as ROM's sh_int (a C short: 16 bits, two's complement)."""
    n &= 0xFFFF
    return n - (1 << 16) if n & 0x8000 else n


def c_div(a, b):
    """a / b for C integers: the quotient truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def c_mod(a, b):
    """a % b for C integers: the remainder takes the sign of a, so a == c_div(a, b) * b + c_mod(a, b)."""
    return a - c_div(a, b) * b
