"""The C functions ported whole except for a difference kept on purpose (#112, decision 2), each with the issue that
accepted it. They're the counterpart of no_counterpart.py: there the C function has no Python, here the Python is
the C function's, but for one thing it can't or shouldn't copy.

charm_tools port status counts them as whole and lists them apart. It fails on an entry that names no C function,
whose marker is missing or still says [partial], or whose reason cites no issue.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

# (C file, function): the difference kept, and the issue that accepted it. A plain literal, so port status can read
# it without importing.
KEPT_DIFFERENCES = {
    ("comm.c", "game_loop_unix"): "the C also polls for exceptional conditions and closes a connection that sends "
                                  "urgent (out-of-band) data; selectors has no such set, so it stays open (#29)",
    ("db.c", "do_memory"): "the Perms line counts Python's objects, as the C's alloc_perm blocks have no "
                           "counterpart (#91, decision 6)",
    ("db.c", "do_dump"): "mem.dmp's byte figures are Python's object sizes and its free lists are empty, where the "
                         "C's come from sizeof and its free lists (#91, decision 6)",
}
