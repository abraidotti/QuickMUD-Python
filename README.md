# QuickMUD-Python

QuickMUD-Python is an unofficial Python port of **QuickMUD**, a MUD (a text-based multiplayer game) derived from
**ROM 2.4b6**. It's at parity with QuickMUD's C game: the same game, the same files, bugs included (`v1.0`). The bugs
filed here are fixed first in stock ROM's C and in Charm (below), and then here. The C game is at the
[`c-final`](https://github.com/abraidotti/QuickMUD-Python/tree/c-final) tag. The tools were first developed for
[Xania](https://github.com/mattgodbolt/xania) (see [Roadmap](#roadmap)).

This repo was called Charm until #116. That name goes to a new repo: a Python port of stock ROM 2.4b6, derived from this
one, and checked against `2.4b6-fixed`, a C archive of stock ROM with its bugs fixed.

QuickMUD-Python stands on more than thirty years of other people's work. The [lineage](#lineage) below credits them, and the
[licence terms](#licence-terms) they set still apply to every copy of this code.

- [Lineage](#lineage)
- [Licence terms](#licence-terms)
- [Getting started](#getting-started)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)

## Lineage

Each generation is a derivative of the one before it and is bound by every earlier licence.

| Years | Codebase | Developers |
|---|---|---|
| 1990–1991 | **DikuMUD** (Gamma 0.0) | Sebastian Hammer (Quinn), Michael Seifert (Papi), Hans Henrik Stærfeldt (God), Tom Madsen (Stormbringer), Katja Nyboe (Superwoman), at DIKU, the Department of Computer Science, University of Copenhagen |
| 1992–1993 | **Merc 2.1** | Furey, Hatchet and Kahn: Michael Chastain, Michael Quan and Mitchell Tse |
| 1993–1998 | **ROM 2.4b6** (Rivers of Mud) | Russ Taylor (Alander), with the ROM consortium: Gabrielle Taylor and Brian Moore (Zump) |
| to 2007 | **QuickMUD** (called "FastROM" until 2000) | Jim Robinson (Flugh), maintainer, "and many others before me" |
| 2012 | QuickMUD 2007, warning fixes | Nick Di Mario (Trom Lios) |
| 2014–2018 | `avinson/rom24-quickmud` on GitHub, Docker image | Aaron Vinson (avinson), with fixes from Blake Pell (blakepell) |
| 2026– | **QuickMUD-Python** | [abraidotti](https://github.com/abraidotti) |

### DikuMUD (1990–1991)

DikuMUD was written at DIKU in Copenhagen. Its licence ([doc/license.doc](doc/license.doc)) is the root of every
term that follows. The in-game `help diku` and `credits` entries list the authors with their game names.

### Merc 2.1 (1993)

Merc was "a Diku Mud with many enhancements and contributions", built on Diku with the Copper and Alfa
enhancements. Its authors signed as Furey, Hatchet and Kahn. The Merc copyright names Michael Chastain, Michael Quan
and Mitchell Tse ([doc/license.txt](doc/license.txt), [README.merc](README.merc)). Their contributors, among them
Alander, Zrin, Grodyn, Diavolo, Vic, Abaddon, Morgenes and many area authors, are listed in
[doc/contrib.txt](doc/contrib.txt). Comments signed "-- Furey" appear throughout the C source (at `c-final`),
and `area/startup.sh` is a port of Furey's `startup` script, "with additions from Tony and Alander".

### ROM 2.4b6 (May 29, 1998)

ROM is Russ Taylor's reworking of Merc 2.1 for his Rivers of Mud; ROM 2.4 was developed during his time on Moosehead
mud. Alander did the changes to the Diku mob and object formats and to the Merc source himself. The ROM consortium
was Russ Taylor, Gabrielle Taylor and Brian Moore. Gabrielle Taylor's ideas gave ROM its privacy code, furniture and
wiznet. Seth Scott wrote the new poofin/poofout, and parts of Rusty's work on Moosehead remain.
[doc/rom.credits](doc/rom.credits) also credits:

- Kelsey and Liralen for the socials, and Liralen for the new Valhalla
- Seth for Puff's special procedure
- Ezra and Regnan (Olympus) for the maps and map shop
- Forstall for the Nirvana zone and Pinkfloyd for the Mob Factory (mobs rewritten by Alander)
- Onivel of Jedi for New Thalos and the ASCII flags used in area files
- Ken Blosser, Doug Araya and Sherene Neil for beta testing
- Shad Muegge, Jerome Despret, Phoenix, Will Hongach, Erwin S. Andreasen, Adam Debus and Gary Turkington (author
  of the ROM FAQ) for bug reports

[README.rom](README.rom) is Alander's original readme, and [README.version](README.version) gives the release date.

### Add-ons folded into QuickMUD

QuickMUD is "a Rom24b6 codebase" with these packages added. Each keeps its own credits in the source; the C
paths below are at the `c-final` tag, and each Python module names the C files it was ported from.

| Package | Authors | Where |
|---|---|---|
| OLC 1.81 (ILAB Online Creation) | Jason Dinkel; ported to ROM 2.3 by Hans Birkeland and to ROM 2.4b6 by Ivan Toledo; original by Surreality and Locke; distributed with The Isles 1.1 | `src/olc*.c`, `src/olc.h`, `src/bit.c`, [doc/changes.olc](doc/changes.olc) |
| MOBprograms for ROM 2.4 (v0.98g, 1996) | N'Atas-Ha and Kahn (Merc 2.2, 1993); ported to ROM 2.4 by Markku Nylander (Newt of Imperium Gothique); updated for 2.4b4 by Kermit | `src/mob_prog.c`, `src/mob_cmds.c`, [doc/MPDocs/](doc/MPDocs/) |
| ColoUr 2.0 | Lope | `src/act_comm.c`, `src/comm.c` |
| Copyover | Fusion of MUD++ (original idea); adapted to Diku and made a ROM patch by Erwin S. Andreasen | `do_copyover` in `src/act_wiz.c` |
| Note boards | Erwin S. Andreasen (1995–96) | `src/board.c` |
| Colour login | QuickMUD, after a snippet by Jaey of Crimson Souls | `src/nanny.c` |
| Help editor (hedit) | after Kermit's `hedit_1` snippet | `src/hedit.c` |
| IMC2 Freedom client (2004) | Roger Libiez (Samson), with Johnathan Walker (Xorith), Jesse Defer (Garil) and Rogel; credits Scion Altera, Shogar, Kratas, Tagith, Noplex, Senir, Trax and Ntanel StormBlade | Removed in R2 (#21); in git history before then |
| SHA-256 (used by IMC2) | Colin Percival (2005, BSD licence) | Removed with IMC2 (#21) |

### QuickMUD (to 2007)

QuickMUD began as "FastROM", a modified ROM its maintainer says he did not originate. It was renamed on April 30,
2000, after Snafu Life pointed out on the ROM list that the old name broke the ROM licence; the maintainer apologised
to Russ Taylor and chose QuickMUD with Hades_'s help. Jim Robinson (Flugh) signs the QuickMUD documentation as its
maintainer, "and many others before me". The changelog
([CHANGELOG.quickmud](CHANGELOG.quickmud)) credits Calath (string editor fix), Jaey (colour login), Mongbat (OLC
translation and a mobprog crash), Thermolog, PHyhan, Rait, Chil, Mike Cosby, Khakarot, Chris Litchfield of The Mage's
Lair (pet affect duplication), Fraktyl and Dingo, and fixes from Edwin's page. See [README.quickmud](README.quickmud)
and [doc/QuickMUD.txt](doc/QuickMUD.txt).

In 2012 Nick Di Mario (Trom Lios) removed the compiler warnings from the 2007 release, renamed `getline`, enabled the
`scan` command and moved the binary into `area/` ([doc/QuickMUD Fixes](<doc/QuickMUD Fixes>)).

### rom24-quickmud on GitHub (2014–2018)

Aaron Vinson (avinson) published the code as
[avinson/rom24-quickmud](https://github.com/avinson/rom24-quickmud), with a Dockerfile and a prebuilt image. Blake
Pell (blakepell) contributed a Makefile fix, the copyover path fix, a fix for a copyover bug that let half-created
characters log in (at level 0, or as anyone without a password), a shop memory leak fix and a help-logging fix.

### QuickMUD-Python (2026–)

QuickMUD-Python is a fork of `avinson/rom24-quickmud` at
[abraidotti/QuickMUD-Python](https://github.com/abraidotti/QuickMUD-Python), and was called Charm until #116. In 2026 it
was ported to Python ([plans/python-port.md](plans/python-port.md)) and checked against the C game function by
function, until the two matched: every C function ported, 122 scenarios and every live check the same on both. The C
was then removed (#112); `c-final` is the last commit with it, and `v1.0` the first without.

The Xania developers (The Moog, Death, Faramir, Rohan and Wandera) are thanked here too. Xania is a separate ROM
descendant, and QuickMUD-Python's tooling grew out of work on it. No Xania code is in this repository.

## Licence terms

QuickMUD-Python is not open source in the modern sense. Running it means following all three licences in `doc/`:

- **Diku** ([doc/license.doc](doc/license.doc)): no resale or operation for profit; the original authors' names must
  appear in the login sequence; the `credits` command must report the original authors; you must notify the Diku
  creators that you run a Diku MUD.
- **Merc** ([doc/license.txt](doc/license.txt)): copyrights stay in the source; `help merc` must report the Merc help
  text as shipped.
- **ROM** ([doc/rom.license](doc/rom.license)): the login screen must say the game is based on ROM 2.4 beta,
  copyright 1993–1996 Russ Taylor, visible on a 24-line terminal; the help files must keep the `ROM` entry unaltered;
  the game may not be called ROM or "something-ROM"; derivatives must keep all README and credits files; and before
  opening a ROM-based MUD you must email the author, so the author can keep track of sites.

### Licence checklist

Checked at cut-over (#112, decision 5; ticked for `v1.0`) and again at refactor R6, when QuickMUD-Python gets its own
identity:

- [x] The login screen names the Diku authors and says it's based on ROM 2.4 beta, copyright Russ Taylor, inside 24
  lines, on the Python game: 12 lines, the same bytes as the C sent (`port greeting`, until cut-over). The stock
  text says "1993-1998", which covers the licence's "1993 - 1996".
- [x] `credits` reports the original authors.
- [x] `help diku`, `help merc` and `help rom` are byte for byte as at `c-final`.
- [x] The game isn't called ROM, or "something-ROM", anywhere: the greeting, `version`, the who list, the README and
  the Docker image.
- [x] Every `game/` module keeps its copyright header (`game/tests/test_guards.py`).
- [x] `README*`, `CHANGELOG.quickmud` and `doc/`'s three licences are in the repo and the Docker image.
- The operator's steps, not the code's: whoever runs QuickMUD-Python publicly notifies the Diku creators that they run a Diku
  MUD, and emails the ROM author before opening (ROM licence, term 4).

IMC2, its strlcpy/strlcat and SHA-256 carried their own licences. QuickMUD-Python no longer ships them (#21), so their terms
no longer apply; their authors stay credited above. Leave every copyright header in `game/` as it is (each module's
licence header, and the C's own headers at `c-final`), and keep `help diku`, `help merc`, `help rom` and the
greeting's credits when QuickMUD-Python gets its own identity.

The QuickMUD maintainer's request still stands: "don't just download this code, compile it, and advertise it on MUD
websites as 'a highly modified ROM codebase'. Spend some time developing it."

## Getting started

### Docker

```sh
docker compose up -d --build
telnet 127.0.0.1 4000
```

This builds the game from this checkout (Ubuntu 26.04, Python 3.14) and runs it on port 4000. `player/`, `log/`,
`gods/` and `notes/` are mounted from the checkout, so they survive restarts; each run's log is `log/NNNN.log`. Stop it with
`docker compose down`.

`docker compose down` (or `docker stop`) shuts the game down cleanly: players are told, everyone is saved, and the
game exits 0.

To check a build, run the smoke test. It starts a throwaway container from the image and walks through these steps:
- create a character, and check that the `%W` prompt token shows `save`'s lag
- quit and log back in
- stop the container with a change unsaved, restart it, and check the change survived
- copyover as the level-60 fixture `tools/fixtures/player/Smokegod`, checking that a half-created login is dropped
  and that the immortal comes back

The container is always removed afterwards.

```sh
docker build -t quickmud .
python tools/smoke.py --docker quickmud   # exit 0 passed, 1 failed, 2 couldn't run
```

The C game's image was built from `tools/oracle/Dockerfile.c`, which is at the `c-final` tag with the C source.

### Running from the checkout

```sh
cd area
PYTHONPATH=../game ./startup.sh &  # restarts the game if it stops; a 'shutdown' in game stops it for good
telnet 127.0.0.1 4000
```

Or run it once, in the foreground: `PYTHONPATH=game python3 -m quickmud --port 4000` from the repo root. It needs Python
3.12 or later, and nothing else. Copyover needs Linux (WSL works).

### First immortal

A level 2 character named Shemp (password `psswrd`) is in `player/`. Edit the `Levl` line of that file, or play any
character to level 2 and edit its file, to make the first immortal. After that, use `advance`.

## Repository layout

| Path | Contents |
|---|---|
| `game/` | the game, in Python (Diku, Merc and ROM terms; see [game/README.md](game/README.md)) |
| `area/` | Area files, `area.lst`, `startup.sh`, `qmconfig.rc` |
| `doc/` | Diku, Merc, ROM, OLC and MOBprogram documentation and licences |
| `player/`, `log/` | Player files and logs |
| `plans/` | QuickMUD-Python's plans |
| `tools/` | `quickmud_tools`, the Python tools for working on QuickMUD-Python (MIT, see [tools/LICENSE](tools/LICENSE)) |

## Tools

`tools/` holds `quickmud_tools`. It's stdlib-only Python 3.12+, so there's nothing to install. Run it from `tools/`:

```sh
cd tools
python -m quickmud_tools doctor                     # Python, checkout, Docker and the quickmud image
python -m quickmud_tools explore areas              # load every area as the game does: counts and bug() lines
python -m quickmud_tools explore check              # data checks: never-spawned mobs, unreachable rooms, ...
python -m quickmud_tools explore parity           # compare the loader with the C game's saved capture
python -m quickmud_tools sim smoke --docker quickmud   # the smoke test on the image (also: python tools/smoke.py from the root)
python -m quickmud_tools sim smoke --python         # its mortal steps against the game, run here
python -m quickmud_tools sim bots --python --quick  # bots playing while the game times its pulses
python -m quickmud_tools sim lobby --python         # awkward replies at every login prompt
python -m quickmud_tools sim churn --python         # bots creating characters and quitting
python -m quickmud_tools port status                # the C functions ported (frozen at c-final), and where each went
python -m quickmud_tools port world                 # boot the world and compare it with the C game's capture
python -m quickmud_tools port io                    # comm.c's input and output cases, against the C game's results
python -m quickmud_tools port crypt                 # the game's password hashing against glibc's saved answers
python -m quickmud_tools port players               # the C game's saved player files, loaded and saved by the game
python -m quickmud_tools port scenarios             # scenario files against their goldens, step by step
python -m quickmud_tools port coverage act_move.c   # lines of the ported functions no test or scenario runs
python -m unittest discover -s tests -t .        # the tools' own tests
```

`explore` reads the area files the way the game's `boot_db` does, quirks included. `explore parity` checks that
against what the C game printed, captured before cut-over:
- The totals of the game's `memory` command and the `bug()` lines in its boot log must match.
- So must the game's exact log output for each deliberately broken area in `tools/fixtures/boot/cases/`.

The checks that ran the C game live (`port rng`, `greeting`, `login`, `commands`, `asave`, and the `--docker`
captures of the others) and `port data` are at the `c-final` tag. The saved captures they made are the tests now: a
deliberate change, such as a bug fix, updates the ones it changes in the same PR (`port scenarios --save` for the
goldens).

The tools are being ported from the Xania tools in stages; see [plans/tools-port.md](plans/tools-port.md).

## Roadmap

- [plans/tools-port.md](plans/tools-port.md): bring the assessment (Explorer), testing (Sim) and build (Builder) tools
  from the Xania work into this repository, so QuickMUD-Python can be developed on its own.
- [plans/refactor.md](plans/refactor.md): make the code safe and testable to work on, without breaking the
  credits and licences above.
- [plans/python-port.md](plans/python-port.md): port the game to Python, matching the C game first. Done at
  `v1.0`. Its last section is the plan after it: `2.4b6-fixed`, then Charm, then this repo's fixes.
