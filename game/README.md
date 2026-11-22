# game/: Charm's game, in Python

This is the game. It's a port of QuickMUD's C game, following [plans/python-port.md](../plans/python-port.md), and
it's at parity with it: every C function is ported (`port status`: 950 of 950), and 122 scenarios, the Sim trials
and every live check came out the same on both games before the C was removed (#112). The C game is at the
`c-final` tag. Its known bugs are kept, filed with the label "after cut-over", and are fixed from `v1.0` on.

## Licence

The game is derived from DikuMUD, Merc and ROM 2.4, and the Python port is too. It's under their terms, not under
the MIT licence of `tools/`. The licence texts are in [doc/](../doc/): `license.doc` (Diku), `license.txt` (Merc)
and `rom.license` and `rom.credits` (ROM). The lineage, and what each licence asks of us, are in the
[README](../README.md#licence-terms). Every module starts with a short header naming the copyright holders and
pointing there, and saying which C files it was ported from (at `c-final`). `tests/test_guards.py` checks it.

## Running it

`python -m charm --port N --root DIR` runs the game from DIR (which holds `area/`, `player/`, `gods/`, `notes/` and
`log/`), as the C ran from its area directory. It boots, listens, and stops cleanly on SIGTERM or Ctrl-C (Ctrl-Break
on Windows), saving everyone. `area/startup.sh` runs it in a restart loop, as the Docker image does. Copyover
re-executes the game with its connections open, which needs Linux. `CHARM_SEED` seeds the random numbers, and
`CHARM_UPDATES` names the per-pulse updates to run (`area,violence`, or `all`; unset, all of them; #74).

## Layout

The code is organised by topic, not by C file:

| Package | What | Imports from |
|---|---|---|
| `core/` | C-faithful primitives: integer behaviour (`cint`), random numbers (`rng`), strings, crypt, logging | nothing else in `charm` |
| `data/` | static tables: classes, races, skills, the command table, flags | `core` |
| `world/` | the static world: area files, rooms and the prototypes, name lookups | `core`, `data` |
| `entities/` | characters and objects at run time, moving them around, making them, resets, boot | |
| `net/` | the game loop, descriptors, output, `act()`, login | |
| `persist/` | player files, notes, bans | |
| `commands/` | the interpreter and the commands, by topic | |
| `systems/` | what runs every pulse: fighting, magic, updates, specials, mob programs | |
| `olc/` | the online builder | |
| `testing/` | the scenario player and the test watchdog (not game code) | |

The import rules for the first three are checked by `tests/test_guards.py`. The rest follow the C game's circular
calls for now; untangling them is refactor work (plans/refactor.md).

`data/` was generated from the C (`const.c`, `tables.c`, `special.c` and `merc.h`) by `charm_tools port data` until
cut-over. It's the source now: edit it by hand.

## Scenarios

Scenarios (#35) check state as well as output, with no network and no real clock. A scenario is a text file in
`tests/data/scenarios/` (`NAME.scn`): lines of input for a connection, and `@` lines for the harness (`@connect`,
`@as`, `@return`, `@pulse N`, `@pulse until N TEXT` (pulses until a connection is sent TEXT, at most N), `@mob`,
`@charm` (the last mob follows, charmed; `@charm pet` makes it a pet too), `@obj` (with the object's five values, if
given), `@owner` (the last object's owner, as a player's corpse has), `@spec` (runs the last mob's special, as
`mobile_update` would), `@state`, `@file`, and before boot `@seed`, `@clock`, `@updates` and `@place` (a file from
`tools/fixtures/files`, such as a board's notes or a ban list, put where boot reads it). `charm.testing.scenario`
reads the format; the C driver that defined it, `tools/oracle/scenario.c`, is at `c-final`. A scenario with the
comment `# expect: stopped NotPorted` checks that the game stops there.

Each scenario prints each step's output, the random numbers drawn so far, and on `@state` the rooms' characters and
objects. `NAME.golden` is what the C game printed, and `tests/test_scenarios.py` replays it. A golden's first line
says where it came from: `c-final`, or `python` once a deliberate change has saved it again. After a bug fix, from
`tools/`, `python -m charm_tools port scenarios --save --only NAME` writes the affected goldens from the game, and
the PR shows their diff. `python -m charm_tools port coverage FILE.c` runs the tests and lists the lines of the
functions ported from FILE.c that nothing reaches (#39, decision 6).

## Checked against the C game

Besides the goldens, these compare the game with output the C game saved before cut-over:

- `port world`: the booted world, every prototype, room, mob and object, the log, and the random numbers drawn
- `port io`: comm.c's input and output cases (`tools/tests/data/iocases.txt`)
- `port crypt`: `core/crypt.py`, a stdlib-only port of the DES `crypt()` the C called, against glibc's answers
- `port players`: player files the C game saved, loaded and saved by the game, key by key
- `explore parity`: the loader's totals and boot log, and the broken-area cases
- `tests/test_rng.py`: 10,000 draws of each of the 8 random-number streams on 4 seeds (`tests/data/rng.json`)

A deliberate change updates the saved output it changes, in the same PR, so the diff shows what changed.

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

Something worth improving now the port matches the C has a `# LATER: <what>` comment where the change would go; the
cross-cutting ones are listed in the plan, under Improvements for later.

From `tools/`, `python -m charm_tools port status` turns the markers into a report per C file, against the list of
C functions frozen at `c-final` (`tools/charm_tools/port/c_functions.txt`): which are ported, and which Python
modules they went to. It also lists the C functions with no Python counterpart (`core/no_counterpart.py`), the ones
ported whole but for a difference kept on purpose (`core/kept_differences.py`), and the `# LATER:` notes. A marker
that names no C function fails it, and so does an empty `# LATER:`.

## Tests

```sh
cd game
python -m unittest discover -s tests
```
