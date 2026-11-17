# game/: Charm's game in Python

This is the Python port of the C game in `src/`, following [plans/python-port.md](../plans/python-port.md). It's at
phase P0: the package, its rules and the random numbers. There's nothing to play yet. The C game is the real one
until the port matches it.

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
| `world/` | the static world: area files, rooms, prototypes, resets | `core`, `data` |
| `entities/` | characters and objects at run time, and moving them around | (rules come with the port) |
| `net/` | the game loop, descriptors, output, login | |
| `persist/` | player files, notes, bans | |
| `commands/` | the command table and the commands, by topic | |
| `systems/` | what runs every tick: fighting, magic, updates, specials, mob programs | |
| `olc/` | the online builder | |

Only `core/` exists so far. The import rules for the first three are checked by `tests/test_guards.py`; the rest get
rules once the port shows where the C game's circular calls land.

## Ported functions

A Python function that ports a C one carries a marker on the line above its `def`:

```python
# C: db.c number_range
def number_range(from_, to):
```

From `tools/`, `python -m charm_tools port status` turns the markers into a report per C file: how many of its
functions are ported, and which Python modules they went to. A marker that names no C function fails it.

## Tests

```sh
cd game
python -m unittest discover -s tests
```

`tests/test_rng.py` checks the random numbers against the C game's own: 10,000 draws of each of the 8 streams on 4
seeds, from `tests/data/rng.json`. To capture that file again from the C game (it needs Docker and the build-stage
image):

```sh
docker build --target build -t charm:build .
cd tools
python -m charm_tools port rng --docker charm:build          # compare with the saved file
python -m charm_tools port rng --docker charm:build --save   # replace it
```
