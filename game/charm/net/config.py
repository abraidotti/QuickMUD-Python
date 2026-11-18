"""qmconfig_read: QuickMUD's settings file, area/qmconfig.rc (the ANSI question, colour, telnet go-ahead).

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_wiz.c, src/comm.c. Licence terms: README.md#licence-terms and doc/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from charm.core.log import log_f
from charm.world.areafile.reader import Reader


@dataclass
class Config:
    """comm.c's mud_ansiprompt, mud_ansicolor, mud_telnetga (0 unless the file sets them) and mud_ipaddress."""

    ansiprompt: int = 0
    ansicolor: int = 0
    telnetga: int = 0
    ipaddress: str = "0.0.0.0"


# C: act_wiz.c qmconfig_read
def qmconfig_read(path: Path, config: Config | None = None) -> Config:
    """Read the file the C reads as ../area/qmconfig.rc (from the area directory it runs in)."""
    config = config or Config()
    log_f("Loading configuration settings from ../area/qmconfig.rc.")
    if not path.is_file():
        log_f("qmconfig.rc not found. Using compiled-in defaults.")
        return config
    r = Reader.from_path(path)
    keys = {"ansicolor": "ansicolor", "ansiprompt": "ansiprompt", "telnetga": "telnetga"}
    while True:
        word = "END" if r.at_eof else r.read_word()
        first = word[:1].upper()
        if first in ("#", "*"):  # a comment line
            r.read_to_eol()
            continue
        if first == "E" and word.lower() == "end":
            return config
        # KEY(): the case's names only, and str_cmp ignores case
        name = keys.get(word.lower()) if first in ("A", "T") else None
        if name is not None:
            setattr(config, name, r.read_number())
            continue
        log_f("qmconfig_read: no match for %s!", word)
        r.read_to_eol()
