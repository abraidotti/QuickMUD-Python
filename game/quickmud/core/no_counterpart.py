"""The C functions with no Python counterpart (#91, decision 5): ones that only manage the C's memory, which Python
manages itself, and a few whose whole work is done where the Python builds the thing in place.

quickmud_tools port status counts them as done and lists them apart, and fails on an entry that names no C function
or one that's also ported (with a "# C:" marker). An entry's reason says where its work went, if anywhere.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

# (C file, function): why there's nothing to port. A plain literal, so port status can read it without importing.
NO_COUNTERPART = {
    ("db.c", "alloc_mem"): "the C's own allocator (rgFreeList buckets); Python allocates",
    ("db.c", "free_mem"): "gives alloc_mem's memory back to its free list",
    ("db.c", "alloc_perm"): "the C's permanent blocks, never freed; their count is memory's Perms line, kept "
                            "different (do_memory)",
    ("db.c", "free_string"): "frees a string not in the string space; Python's strings are its own",
    ("db.c", "tail_chain"): "an empty function the C keeps for a tail-call trick",
    ("db.c", "new_reset"): "links a reset onto its room's list; the loader builds those lists (world/index.py "
                           "build_index), and OLC's add_reset is ported",
    ("recycle.c", "new_ban"): "a ban built in place (persist/bans.py)",
    ("recycle.c", "free_ban"): "memory only",
    ("recycle.c", "free_descriptor"): "memory only (closing the socket is close_socket's)",
    ("recycle.c", "free_gen_data"): "memory only",
    ("recycle.c", "free_extra_descr"): "memory only",
    ("recycle.c", "new_affect"): "an affect built in place (world/index.py Affect)",
    ("recycle.c", "free_affect"): "memory only",
    ("recycle.c", "free_obj"): "memory only; its INVALIDATE is extract_obj's Obj.valid",
    ("recycle.c", "free_pcdata"): "memory only",
    ("recycle.c", "free_buf"): "memory only",
    ("recycle.c", "buf_string"): "a buffer's text, which is Buffer.string",
    ("recycle.c", "new_mprog"): "a mob program trigger built in place (world/index.py MobProgRef)",
    ("recycle.c", "free_mprog"): "memory only",
    ("recycle.c", "free_help"): "memory only (hedit_delete takes the help out of its lists)",
}
