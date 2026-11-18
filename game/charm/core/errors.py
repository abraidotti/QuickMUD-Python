"""NotPorted, raised on a branch that isn't ported yet (#25, decision 3); and CWouldCrash, where the C would crash.

A partial port fails loudly where it doesn't yet match the C game, instead of quietly doing something else. The
function carries a "# C: <file>.c <function> [partial]" marker, so charm_tools port status counts it as partial.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""


class NotPorted(NotImplementedError):
    """A C branch the port hasn't reached: NotPorted("nanny.c nanny: CON_GET_OLD_PASSWORD with a bad hash")."""


class CWouldCrash(RuntimeError):
    """A path where the C game would crash or read past the end of memory (a NULL dereference, say). Python can't
    copy that, so it stops: CWouldCrash("comm.c colour: a personal colour code with no character")."""
