# game/: Charm's game in Python

This is the Python port of the C game in `src/`, following [plans/python-port.md](../plans/python-port.md). It's in
phase P1, the spike (#25): so far the random numbers, the generated tables and the area loader. There's nothing to
play yet. The C game is the real one until the port matches it.

## Licence

The game is derived from DikuMUD, Merc and ROM 2.4, and the Python port is too. It's under their terms, not under
the MIT licence of `tools/`. The licence texts are in [doc/](../doc/): `license.doc` (Diku), `license.txt` (Merc)
and `rom.license` and `rom.credits` (ROM). The lineage, and what each licence asks of us, are in the
[README](../README.md#licence-terms). Every module starts with a short header naming the copyright holders and
pointing there. `tests/test_guards.py` checks it.

## Layout

The code is organised by topic, not by C file:

| Package | What | Imports from |
|---|---|---|
| `core/` | C-faithful primitives: integer behaviour (`cint`), random numbers (`rng`), later text and flags | nothing else in `charm` |
| `data/` | static tables: classes, races, skills, liquids, weapons | `core` |
| `world/` | the static world: area files, rooms and the prototypes, name lookups | `core`, `data` |
| `entities/` | characters and objects at run time, moving them around, making them, resets | (rules come with the port) |
| `net/` | the game loop, descriptors, output, `act()`, login | |
| `persist/` | player files, notes, bans | |
| `commands/` | the command table and the commands, by topic | |
| `systems/` | what runs every tick: fighting, magic, updates, specials, mob programs | |
| `olc/` | the online builder | |

So far there are `core/`, `data/`, `world/`, `entities/`, `net/`, `persist/` (player files and the boards),
`systems/` (`update_handler`, the skill groups, mob program triggers, and fighting: all of `fight.c` and
`effects.c`) and `commands/` (the interpreter, and the information, movement and talking commands). The import
rules for the
first three are checked by `tests/test_guards.py`; the rest get rules once the port shows where the C game's
circular calls land. The first one has: `equip_char` (`entities/`) calls `act()` (`net/`).

`python -m charm --port N --root DIR` runs the game from DIR (which holds `area/`), as the C does from its run
directory: it boots, listens, greets connections and stops cleanly on SIGTERM or Ctrl-C (Ctrl-Break on Windows).
Logging in works: new characters (customised or not), old ones from `player/`, the ANSI question, and the C's
checks on names and passwords. In the game, the interpreter takes the whole command table (generated, in the C's
order, so a prefix finds the same command), aliases and socials. The commands ported so far are all of
`act_info.c`'s (look, examine, who, where, score, practice, the auto toggles and the rest), all of `act_move.c`'s
and `act_enter.c`'s (the directions, the doors, the positions, sneak, recall, train, enter), all of `act_comm.c`'s
and `alias.c`'s (the channels, say, tell, emote, pose, follow, group, order, split, colour, alias, delete, save,
quit), all of `act_obj.c`'s (get, put, drop, give, wear, remove, food and drink, sacrifice, steal, the shops,
and the magic items, whose spells run if they're ported), all of `board.c`'s and `ban.c`'s (note, board and
writing a note; ban, permban and allow), all of `act_wiz.c`'s but copyover, which comes with OLC in P5 (goto,
at, transfer, stat, vnum, the wheres, sockets, the echoes, poofs, invis, prefix, wiznet; deny, disconnect, freeze,
the no- commands, pardon, log, protect, snoop, switch; load, clone, purge, advance, trust, restore, peace; set,
string, force, the locks, shutdown, reboot and qmconfig), all of `fight.c`'s (kill, murder, flee, surrender,
slay and the fighting skills), `cast` and every spell (`magic.c` and `magic2.c`), `heal` (`healer.c`), `play`
(`music.c`), and what login calls; any other command raises `NotPorted`, which stops the game (#32). Every
per-pulse update runs, as the C's do: areas, songs, mobs (and their specials), fights, weather, characters, objects
and aggression. Mob programs run (`mob_prog.c`), with their `mob` commands (`mob_cmds.c`); no stock area has a
program, so the scenarios use two fixture areas, `tools/fixtures/files/mobprog.are` and `mobcmds.are`. `CHARM_UPDATES` names the ones to run in both games (`area,violence`, or `all`; unset, all of
them), as `@updates` does in a scenario (#74).
`charm_tools port commands` plays the same sessions on both games and compares them byte for byte; the C game runs
with `CHARM_UPDATES=area` for it, so its other updates are off too.

Scenarios (#35) check state as well as output, with no network and no real clock. A scenario is a text file in
`tests/data/scenarios/` (`NAME.scn`): lines of input for a connection, and `@` lines for the harness (`@connect`,
`@as`, `@return`, `@pulse N`, `@pulse until N TEXT` (pulses until a connection is sent TEXT, at most N), `@mob`,
`@charm` (the last mob follows, charmed; `@charm pet` makes it a pet too),
`@obj` (with the object's five values, if given), `@owner` (the last object's owner, as a player's
corpse has), `@spec` (runs the last mob's special, as `mobile_update` would), `@state`, `@file`, and before
boot `@seed`, `@clock`, `@updates` and `@place` (a file from `tools/fixtures/files`, such as a board's notes or a
ban list, put where boot reads it); the format is in `tools/oracle/scenario.c`). A scenario with the comment `# expect: stopped NotPorted` checks that unported code stops the Python game. The C driver
plays it through the C game's own code, and `charm.testing.scenario` through the Python game's. Both print each
step's output, the random numbers drawn so far, and on `@state` the rooms' characters and objects. The C's lines
are saved as `NAME.golden`, which `tests/test_scenarios.py` replays with no Docker. From `tools/`,
`python -m charm_tools port scenarios --docker charm:build --save` saves them again after a C change; a golden
names the C sources it came from, so a stale one fails. `python -m charm_tools port coverage FILE.c` runs the
tests and lists the lines of the functions ported from FILE.c that nothing reaches (#39, decision 6).

Player files are `persist/player.py`, line by line from `save.c`, so either game loads the other's files
(`charm_tools port players` checks it both ways). Passwords use `core/crypt.py`, a stdlib-only port of the DES
`crypt()` the C calls, checked against glibc (`port crypt`).

`charm.entities.boot.boot_db` boots the world the way the C game does: the seed, the clock and weather, the areas,
then a reset of every area. From `tools/`, `python -m charm_tools port world` boots it next to the C game's (Docker,
or the saved capture) and compares the two line by line: every prototype, room, mob and object, the log, and the
random numbers drawn.

`data/` is generated from the C (`const.c`, `tables.c`, `special.c` and `merc.h`), except its `__init__.py`. Don't
edit it by hand: change the C, then from `tools/` run `python -m charm_tools port data`. The tools' tests fail if it's
out of date, and check that the loader's tables built from it equal the ones read straight from the C.

## Guards

`tests/test_guards.py` also reads the source for the ways Python goes quietly different from the C (#35):

| Guard | The safe way | A line may instead carry |
|---|---|---|
| no `random`, `secrets` or `numpy` | `core/rng.py`, the C's `random()` | (nothing) |
| the real clock (`time.*`, `datetime`) | `game.current_time` | `# clock: <why>` |
| `//` and `%` on numbers | `c_div` and `c_mod` in `core/cint.py` | `# non-negative: <why>` or `# format: <why>` |
| `.lower()`, `.upper()` and the like | `lower`, `upper`, `str_cmp`, `str_prefix`, `str_suffix` in `core/strings.py` | `# not LOWER: <why>` |
| a `@dataclass` without `eq=False` | `@dataclass(eq=False)`: compared by identity, like the C's pointers | `# value: <why>` |
| `.append`, `.extend` or `+=` on a head-first list (`people`, `contents`, `carrying`, ...) | `.insert(0, ...)` | (nothing) |
| `async`, `await`, threads | one thread, as the C | (nothing) |

A failure lists every line it found. The area-file model (`world/areafile/`) is values and exempt from the
dataclass guard.

## Ported functions

A Python function that ports a C one carries a marker on the line above its `def`:

```python
# C: db.c number_range
def number_range(from_, to):
```

A function that's only partly ported so far says so, and raises `charm.core.errors.NotPorted` on any branch it
doesn't cover yet, so it fails loudly instead of doing something different from the C:

```python
# C: db2.c load_mobiles [partial]
```

Something worth improving once the port matches the C gets a `# LATER: <what>` comment where the change would
go; the cross-cutting ones are listed in the plan, under Improvements for later.

From `tools/`, `python -m charm_tools port status` turns the markers into a report per C file: how many of its
functions are ported, how many partly, and which Python modules they went to. It ends with the `# LATER:` list. A
marker that names no C function fails it, and so does an empty `# LATER:`.

## Tests

```sh
cd game
python -m unittest discover -s tests
```

`tests/test_rng.py` checks the random numbers against the C game's own: 10,000 draws of each of the 8 streams on 4
seeds, from `tests/data/rng.json`. To capture that file again from the C game (it needs Docker and the build-stage
image):

```sh
docker build -f tools/oracle/Dockerfile.c --target build -t charm:build .
cd tools
python -m charm_tools port rng --docker charm:build          # compare with the saved file
python -m charm_tools port rng --docker charm:build --save   # replace it
```
