"""source: read facts out of Charm's C source (merc.h defines, const.c/tables.c/special.c tables).

Narrow readers that fail loudly: each finds one named thing and raises SourceError if it isn't where expected.
"""
