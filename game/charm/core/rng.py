"""The game's random numbers: glibc's random(), and db.c's number_mm, number_range and the rest built on it.

Charm is built without OLD_RAND, so number_mm is random() >> 6 and init_mm seeds with srandom(). Python's own
random module would give different numbers; this reproduces glibc's TYPE_3 generator (the one srandom() sets up:
a 31-word additive feedback generator, seeded by a Park-Miller LCG and run 310 steps before use), so the same seed
gives the same fights as the C game. Checked against the game's own functions by charm_tools port rng.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/db.c. Licence terms: README.md#licence-terms and doc/.
"""

import os
import sys
import time

from charm.core.cint import c_div, c_mod, int32, uint32

_DEG = 31  # TYPE_3: degree of the generator
_SEP = 3  # TYPE_3: separation between the front and rear pointers


class GlibcRandom:
    """glibc's random_r state for TYPE_3, the default for srandom()/random()."""

    def __init__(self, seed=1):
        self.srandom(seed)

    def srandom(self, seed):
        # glibc random_r.c __srandom_r: seed 0 becomes 1; the seed is stored as an int32_t, so 2^32-1 is -1, and
        # the LCG below uses C division (truncating), which matters for negative words.
        seed = uint32(seed) or 1
        word = int32(seed)
        state = [word]
        for _ in range(1, _DEG):
            hi = c_div(word, 127773)
            lo = c_mod(word, 127773)
            word = 16807 * lo - 2836 * hi
            if word < 0:
                word += 2147483647
            state.append(word)
        self.state = [uint32(w) for w in state]
        self.front = _SEP
        self.rear = 0
        for _ in range(_DEG * 10):
            self.random()

    def random(self):
        # glibc random_r.c __random_r, TYPE_3: *fptr += *rptr (as uint32_t); the result drops the low bit.
        s = self.state
        val = (s[self.front] + s[self.rear]) & 0xFFFFFFFF
        s[self.front] = val
        self.front += 1
        if self.front >= _DEG:
            self.front = 0
            self.rear += 1
        else:
            self.rear += 1
            if self.rear >= _DEG:
                self.rear = 0
        return val >> 1


# The game has one generator, as the C game has one random() state.
_rng = GlibcRandom()


def srandom(seed):
    _rng.srandom(seed)


def random():
    return _rng.random()


# C: db.c init_mm
def init_mm(environ=None, log=None):
    """Seed the generator from CHARM_SEED if it's set and valid, otherwise from the clock; log and return the seed.

    log takes one line of text; it defaults to stderr until log_string is ported.
    """
    environ = os.environ if environ is None else environ
    log = log or (lambda line: print(line, file=sys.stderr))
    env = environ.get("CHARM_SEED", "")
    if env:
        # The C side uses strtoul: optional leading whitespace and '+', decimal digits, nothing after.
        text = env.lstrip(" \t\n\r\f\v")
        digits = text[1:] if text[:1] == "+" else text
        if env[0] != "-" and digits.isascii() and digits.isdigit() and int(digits) <= 0xFFFFFFFF:
            seed = int(digits)
            srandom(seed)
            log(f"Random seed: {seed} (CHARM_SEED)")
            return seed
        log(f"CHARM_SEED={env[:20]} isn't a number from 0 to 4294967295; using the clock.")
    seed = uint32(int(time.time()) ^ os.getpid())
    srandom(seed)
    log(f"Random seed: {seed} (clock)")
    return seed


# C: db.c number_mm
def number_mm():
    return random() >> 6


# C: db.c number_fuzzy
def number_fuzzy(number):
    bits = number_bits(2)
    if bits == 0:
        number -= 1
    elif bits == 3:
        number += 1
    return max(1, number)


# C: db.c number_range
def number_range(from_, to):
    if from_ == 0 and to == 0:
        return 0
    to = to - from_ + 1
    if to <= 1:
        return from_
    power = 2
    while power < to:
        power <<= 1
    while True:
        number = number_mm() & (power - 1)
        if number < to:
            return from_ + number


# C: db.c number_percent
def number_percent():
    while True:
        percent = number_mm() & (128 - 1)
        if percent <= 99:
            return 1 + percent


# C: db.c number_door
def number_door():
    while True:
        door = number_mm() & (8 - 1)
        if door <= 5:
            return door


# C: db.c number_bits
def number_bits(width):
    return number_mm() & ((1 << width) - 1)


# C: db.c dice
def dice(number, size):
    if size == 0:
        return 0
    if size == 1:
        return number
    total = 0
    for _ in range(number):
        total += number_range(1, size)
    return total
