# Plan: port Charm's game from C to Python

Status: decisions 1-7 answered (#19); R2 done (#22); P0 done (#24); P1 spike started 2026-11-17 (#25), time box
5 PRs or 2026-12-08. PR 1 of 5 done (#26): the tables and the loader move. PR 2 of 5 done (#27): the world and
resets (`charm_tools port world`). PR 3 of 5 done (#29): the loop, connections and output (`port io`, `port
greeting`); the checkpoint after it estimated 60% of the spike's functions ported, over #25's 40% line. PR 4 of 5
done (#31): login and player files (`port crypt`, `port login`, `port players`). PR 5 of 5 done (#33): the commands
(`port commands`, `sim smoke --python`, `sim bots`); the C game gained the test-only `CHARM_UPDATES=area`. P1 done:
the go/no-go (#34) answered go, with a speed checkpoint when the mob and combat updates run. P2, the differential
harness, started 2026-11-18 (#35), time box 3 PRs or 2026-11-26: PR 1 of 3 done (#36), the scenario player on both
sides (`tools/oracle/scenario.c`, `charm.testing.scenario`, `port scenarios`) and the first golden. PR 2 of 3: the
first scenarios, 14 in all.

## Goal

Charm's game would run as a Python program that behaves the same as today's C game: same area files, same player
files, same messages, same numbers. Gameplay changes come after that, as in the refactor plan. The aim is a codebase
where new game work is easy to write, test and review, sharing one language with `tools/`.

This plan only makes sense if it replaces most of [refactor.md](refactor.md) R3-R5. Hardening C strings and splitting
`merc.h` is wasted work if the C is then retired. That's why this plan is due now, before R2 and T2.

## Starting point

Measured on master (8cdcf11), 2026-11-17:

- **C to port.** `src/` is 74.8k lines. Without IMC2 (`imc.c`, `imc.h`, `imccfg.h`, `sha256.*`, about 9.3k lines,
  which refactor decision 2 recommends removing) it's about 65k. The largest files are `olc_act.c` (5.0k), `magic.c`
  (4.9k), `act_wiz.c` (4.8k), `db.c` (4.0k), `handler.c` (3.6k) and `fight.c` (3.3k).
- **Already ported.** T1's area loader in `tools/charm_tools/explore/areafile/` is a faithful port of `boot_db`'s
  area loading (about 1,100 lines of Python). It matches the game's `memory` totals and its `bug()` output exactly,
  including 11 broken-area cases.
- **A parity method that already works.** `charm_tools explore parity` boots the real game in Docker, captures its
  output and compares it with the Python side. The smoke test (`charm_tools sim smoke`) speaks telnet and doesn't care
  what language the server is in, so the same steps can run against both games.
- **The RNG.** Charm is built without `OLD_RAND`, so `number_mm` (`db.c:3599`) calls glibc's `random()`, seeded with
  `time(NULL) ^ getpid()` in `init_mm`. A port that wants identical fights needs glibc's `random()` in Python and a way
  to fix the seed on both sides.
- **Passwords.** Player files hold DES `crypt()` hashes. Python 3.13 removed the `crypt` module, so verifying them
  needs either `ctypes` and libcrypt, or a pure-Python DES.

## What Nostoi's port shows

[Nostoi/rom24-quickmud-python](https://github.com/Nostoi/rom24-quickmud-python) (read at 4595c95, 2026-10-22) is a
Python port of the same QuickMUD code. It's the best evidence we have of what a port costs and where it goes wrong.

**The cost.** Version 0.1.0 was on 2025-09-13 and 2.14.268 on 2026-07-05, with work continuing since. The engine
(`mud/`) is 78.7k lines of Python, the repo about 246k with its tests, and the README counts 6,127 tests and 69
differential scenarios. After all that, it still calls its parity "beta". Most of the work was done by AI agents
working from a tracker (`AGENTS.md`, `docs/sessions/`), much as Charm is worked on.

**Patterns worth borrowing:**

- **Divergence classes.** `docs/parity/DIVERGENCE_CLASS_ROSTER.md` lists the places where Python and C differ
  structurally, each with one way to check it. The list is a ready-made checklist for Charm:
  - RNG
  - C integer division and modulo (truncating toward zero, not flooring)
  - `int` and `sh_int` overflow
  - pointer identity versus Python's value `==` (they fixed it with `@dataclass(eq=False)` on every runtime entity)
  - linked lists that insert at the head, so order is last-in first-out (their "LIFO" finding fixed 15 places)
  - flags surviving the load
  - output ordering inside a tick
  - link-dead characters staying in the world

  Found in Charm so far (#25), and added to the list:
  - macros that evaluate an argument twice: `UMIN(number_fuzzy(level), LEVEL_HERO - 1)` draws two random numbers
    whenever the first is the smaller, and every reset after it depends on that
  - text read with newline translation: Python turned the stray `\n\r` in two area files into two newlines,
    where the C's `getc()` sees the bytes
  - undefined behaviour in the C: a `{` or `$` at the end of a string makes the C read past it, and a personal
    colour code with no `PC_DATA` dereferences NULL. Python can't copy those; it stops there, and raises
    `CWouldCrash` where the C would crash
  - what the transport can't see: the C closes a connection that sends urgent (out-of-band) data, because it polls
    for exceptional conditions; `selectors` has no such set, so the Python game doesn't. Accepted as a known
    difference (#29)

  Differences kept on purpose:
  - the startup log line says "Charm is ready to rock on port N", where the C says "ROM is ready to rock" (#29)
  - the MOTD's last line says "Welcome to Charm.", where the C says "Welcome to ROM 2.4." (#30)
  - save says "Remember that Charm has automatic saving now.", where the C says ROM (#32)
  - a connection that sends out-of-band data stays open (above)

  The pointer identity class above showed up in Charm too (#30): fwrite_obj and fwrite_pet write a string when
  its pointer differs from the prototype's, and a string read from a player file is always a new one. The port
  records which strings are an object's own (`own_strings`) instead of comparing Python strings with `is`. The
  fields mark themselves (a descriptor, `things._OwnString`): assigning one after construction makes it the
  object's own, as a new pointer would be, and `create_object` and `create_mobile` clear the set. So code ported
  later (restrings, a pet's neck tag) can't forget to mark it. Reading one of those fields costs about 80 ns more
  than a plain attribute.
- **Guard tests that scan the source.** Where a rule is "always go through one function" (the RNG, flag constants,
  wear slots), a test greps the code for anything that bypasses it. A regression then fails the test suite instead of
  waiting to be noticed.
- **A differential harness.** An extra C `main` (`src/diff_shim/diffmain.c`, additive, no game source changed) runs
  scripted scenarios with a fixed seed. Their scenarios are JSON files with meta-commands such as `__seed=N`,
  `__mload=VNUM` and `__tick`. The goldens it writes are committed, so everyday tests replay them in pure Python
  without a C build.
- **A per-C-file audit tracker.** Each C file gets a row and a status, so "how much is ported" has an answer.

**Patterns to avoid:**

- **Async game logic.** Three of their divergence classes came from game code awaiting in the middle of a tick:
  messages delivered twice or not at all, a prompt rendered before a death clamp, and link-dead handling. C's tick runs
  to the end in one go. Ours should too.
- **A different data format before parity.** They load JSON converted from `.are`, and store players with SQLAlchemy.
  That added a divergence class (flags lost in the conversion) and a stack of dependencies before parity was reached.
- **Features before parity.** WebSocket and SSH servers, accounts, a web client. Each is reasonable, but each also
  moves the target.

**Why not adopt their code.** It's 246k lines written to their own conventions, it doesn't have Charm's fixes
(#4-#9), and it ships under MIT. A port of ROM is still a derivative of ROM, so we'd treat it as bound by the Diku,
Merc and ROM terms whatever its LICENSE says. Taking it would leave Charm unsure what licence its own game is under.
Reading it for patterns is fine. Copying code from it isn't.

## Ground rules (if the port goes ahead)

- **Behaviour first.** The Python game matches the C game until cut-over, quirks included. A difference is a bug in
  the port unless it's a C bug we've filed and fixed in both.
- **The C game is the oracle.** It stays buildable and in Docker until cut-over. Parity is measured against it, never
  against our reading of it.
- **Licences.** The Python game is a derivative of Diku, Merc and ROM, and carries their terms: a header in each module
  naming the C file it came from and the original copyright notices, and the same credits on the login screen, in
  `credits` and in the three help entries. It's never called ROM. `tools/` stays MIT and separate.
- **Same files on disk.** The port reads and writes the same `.are` files, player files, `qmconfig.rc`, notes and
  bans as the C game. Changing a format is a later, separate issue.
- **Synchronous game logic.** One thread. The game code never awaits. Input is read and output is flushed around each
  pulse, as in `game_loop_unix`.
- **One checkpoint per C file.** A file is done when its tracker row says so and its parity checks pass. "Unknown" is
  reported as unknown.

## Decisions (answered in #19)

1. **Port at all?** *Answered: run a spike first (phase P1), then decide.* The spike ports enough to boot, log in,
   look, move, save and quit. It ends when `sim smoke` passes its login and save steps against the Python game, or at
   a time box, whichever comes first. The go/no-go issue then has real numbers: lines per C line, divergences found,
   and an estimate for the rest. Alternatives: commit to the port now, or stay in C and close this plan.
2. **Our own port or Nostoi's?** *Answered: our own, borrowing their patterns (see above).* Alternative: fork
   theirs and add Charm's fixes. That's faster to a running game, but it comes with their licence, their size and their
   data formats.
3. **How exact?** *Answered: identical given the same seed, the RNG included.* Port glibc's `random()` (the TYPE_3
   additive generator that `srandom()` sets up), and add a test-only `CHARM_SEED` environment variable to the C game
   so both sides can be fixed. Alternative: build the oracle with `-DOLD_RAND` as Nostoi did. That's less work, but
   then the oracle isn't the game players are on.
4. **Networking loop.** *Answered: stdlib `selectors`, a copy of `game_loop_unix`'s structure* (`comm.c:765`). Each
   pulse polls, reads, runs at most one command per descriptor in `descriptor_list` order, runs `update_handler()`,
   flushes output in list order and sleeps out the pulse. A write error (including `EAGAIN` on a full buffer)
   disconnects, as `write_to_descriptor` does. Copyover passes plain inheritable sockets through `os.execv`. Game
   code only touches a small descriptor interface (input buffer, output buffer, close), so the transport can be
   swapped for `asyncio` later, as its own issue, if a web client or SSH ever needs it. Rejected for now: `asyncio`,
   because input order across descriptors would follow the event loop rather than the list, writes would buffer
   without limit, copyover would need sockets detached from their transports, and async game code is where three of
   Nostoi's divergence classes came from.
5. **Dependencies.** *Answered: stdlib only, Python 3.12+, as for `tools/`.* Verify old DES hashes through `ctypes`
   and libcrypt, which is in the Docker image already. Refactor decision 3 (modern hashing) then becomes `hashlib.scrypt`
   with a rehash on login, as its own issue after cut-over.
6. **Where it lives.** *Answered: a `game/` directory holding a `charm` package, with its own tests.* T1's loader
   moves from `tools/` into `game/` and `tools/` imports it from there. Because the loader is a port of `db.c`, it then
   sits under the game's licences rather than MIT. Alternative: keep the two separate and maintain two loaders.
7. **What happens to `src/` at cut-over.** *Answered: a tag (`c-final`) and removal from master, once the parity
   suite and a full Sim run are green.* Alternative: keep `src/` on master as the reference.

## P0 decisions (answered in #23)

1. **Package.** `game/charm/`, run as `python -m charm`; tests in `game/tests/` with `unittest`. `charm_tools` makes
   it importable with `paths.use_game()`, which puts `game/` on `sys.path`.
2. **Licence headers.** Every module's docstring has a short header: the Diku, Merc and ROM copyright holders, the C
   file it was ported from (or "Written for Charm; no single C source"), and a pointer to the licence texts in
   `doc/` and the README's licence section. No `game/LICENSE`. `game/tests/test_guards.py` checks every module.
3. **Layout and tracker.** By topic, not by C file (see Layout below). Ported functions carry
   `# C: <file>.c <function>` above their `def`; `charm_tools port status` reports per C file from those markers,
   and fails on a marker that names no C function.
4. **`CHARM_SEED`.** An environment variable read by `init_mm`. The game logs the seed it used at every boot.
5. **RNG check.** `tools/oracle/rngcheck.c`, linked against the game's object files, prints 8 streams of 10,000
   draws on 4 seeds. `charm_tools port rng` captures them into `game/tests/data/rng.json`, and
   `game/tests/test_rng.py` checks the Python RNG against that file.

## Layout

```
game/charm/
  core/       C-faithful primitives: cint, rng, later text and flags       imports nothing else in charm
  data/       static tables: classes, races, skills, liquids, weapons      imports core
  world/      the static world: areafile/ (T1's loader), prototypes, lookups imports core, data
  entities/   characters and objects at run time, handler functions, resets
  net/        the selectors loop, descriptors, act() and output, login
  persist/    player files, notes, bans
  commands/   interp and the commands, one module per topic
  systems/    fight, magic, skills, update, specials, mob programs
  olc/        the online builder (P5)
```

The import rules for the first three layers are tested. The rest get rules once the port shows where the C game's
circular calls land (`update.c` calls `do_quit`, for one). The first to land: `handler.c`'s `equip_char` calls
`act()` from `comm.c`, so `entities/` imports `net/`. Resets are in `entities/`, not `world/`, because they make
characters and objects. Format code stays in three places: `world/areafile/`,
`persist/` and `data/`. A later change of file format only swaps readers and writers there.

## Improvements for later

Refactors and better structures noticed while porting. They wait until the port matches the C: until then every
change has to pass the line-by-line checks against the C game (`port world`, and P2's scenarios), and a cleanup
that changes behaviour would hide real divergences. Then they're weighed like the refactor plan's items, by impact
and effort.

Ones with a place in the code are `# LATER:` comments there, and `charm_tools port status` lists them with file
and line. Ones that cut across the code are here:

- **One model for the world, not two.** `world/areafile/` reads area files into Explorer's model (what the file
  says), and `world/index.py` copies that into the game's prototypes (what the C keeps). Once both are settled, one
  could derive from the other, or both from the JSON look's schema.
- **Where the game state lives.** `Game` holds what the C keeps in globals. When `net/`, `persist/` and `systems/`
  add theirs, it may split by topic, or become the one place every layer reads from.
- **A stronger password hash, in both games** (#30). Passwords are traditional DES crypt: 8 characters count, the
  salt is the first two letters of the name, and the hash is fast to attack. Moving both games to a modern hash
  (with old hashes upgraded at the next login) needs a C change too, so it goes through the refactor plan.

## Phases

| Phase | What | Done when |
|---|---|---|
| **P0 Groundwork** | Refactor R2 (pruning, and IMC2 per refactor decision 2) runs first, so there's less to port. The `game/` package, licence headers, the C-function tracker and `CHARM_SEED` in C. glibc `random()` and `db.c`'s RNG functions in Python, checked against the C game's own. | Tracker lists every C function; RNG matches C for 10k draws per stream on 4 seeds |
| **P1 Spike** | Move T1's loader into `game/`, then port: `area_update` and resets, the descriptor loop, `nanny.c`, `save.c` (load and save, round-trip with C's files), `interp.c`, `act()`, and the commands the smoke test uses (`look`, movement, `save`, `quit`, `score`, `title`). | `sim smoke` passes its login, save and quit steps on the Python game, or the time box ends. Go/no-go issue written with the numbers. |
| **P2 Differential harness** | Scenario files, an additive C driver, goldens, pure-Python replay in the tests. Guard tests for the divergence classes. | 10 scenarios replay green; guard tests run in the suite |
| **P3 Commands without RNG** | The rest of `act_info.c`, `act_move.c`, `act_obj.c`, `act_comm.c`, `act_enter.c`, `alias.c`, `ban.c`, `board.c`, `act_wiz.c`. | Their tracker rows done; full `sim smoke` passes on Python |
| **P4 RNG systems** | `fight.c`, `magic.c`, `magic2.c`, `skills.c`, `effects.c`, `update.c`, `special.c`, `healer.c`, `music.c`, `mob_prog.c`, `mob_cmds.c`. | Seeded scenarios (fights, spells, ticks, resets over time) match C step for step |
| **P5 OLC and the rest** | `olc*.c`, `hedit.c`, `string.c`, copyover (re-exec with inherited sockets via `os.execv`). | `asave` output byte-identical to C's for every stock area; copyover steps of `sim smoke` pass |
| **P6 Cut-over** | Sim lobby and churn trials on both games, compared. Docker image switched to Python. Decision 7 for `src/`. | Every tracker row done; trials show no new findings on Python; licence checklist ticked |

Each phase is one or more PRs, each with its parity proof, as for T1.

**Later, its own issue: JSON.** The files on disk stay as they are until cut-over (ground rules). Before then, a
cheap first look is possible: export each `.are` file to JSON from the loaded model, read it back and check that
nothing changed. That gives real JSON to judge the format by, for areas first and then skills, classes and the other
tables. The same issue takes up refactor decision 6 (tables in C or in data files).

## How the tools fit

The Xania tools come over in [tools-port.md](tools-port.md). A Python game changes what each one can lean on.

- **Explorer (assessments).** Until cut-over, Explorer reads the C: T2's table readers parse `const.c` and
  `tables.c`, and the same readers check `charm/data/` against them. After cut-over, Explorer imports the tables
  and the world from `charm` directly, so there's one source of truth. For formulas (to-hit, damage, XP, regen), an
  assessment that asks "what does the game do" calls the game's own pure functions. One that checks the game
  against its intent keeps an independent derivation, or it could only ever agree with the code. Source pointers
  name the Python function, and the marker gives its C origin.
- **Sim (testing bots).** The telnet bots work unchanged against both games. That's how P1-P6 are gated: the same
  trials on both, compared. The Python game adds an in-process mode, where Sim attaches bots through the descriptor
  interface with no sockets, a fixed seed and, after P2, a fixed clock. That makes trials fast, repeatable and
  runnable without Docker. Keeping `net/`'s descriptor interface small (#19, decision 4) is what makes it possible.
  P2's differential scenarios are Sim scenarios run against both games.
- **Companions.** Xania Companions are rule-based bots that play beside a player. They follow, fight and heal, and
  write their own legends, all built on Sim's session layer. On Charm they'd connect the same way, over telnet or
  in-process through a descriptor, and see only what a player sees. They never read game state directly, so they
  play by the same rules as people and don't tie themselves to the game's internals. They come after Sim's trials
  (T5) and aren't part of this plan, but the descriptor interface keeps the door open.

## Effect on the other plans

- **Refactor.** R2 runs before P0 either way: pruning helps the C game and shrinks the port. If the spike says go,
  R3-R5 are dropped for C and their goals (bounded strings, tests, structure, CI) come with the port. R6 (identity)
  applies to the Python game after cut-over. If it says no-go, the refactor plan continues as written.
- **Tools.** T2's C table readers still come first: they give the parity checks for `const.c` and `tables.c`, and they
  can generate the first Python tables. Once the Python game exists, T2-T3 assessments can read its tables directly.
  T4-T5 (Sim) run against both games, which is what P2-P6 need.

## Risks

- **It's the size of the whole game.** Nostoi's numbers suggest months of work before it's done, and no new gameplay
  while it happens. The spike exists so this is decided with data.
- **Two games at once.** Any bug fix during the port has to go into C and Python both, with the same test. Keep
  fixes small and rare until cut-over.
- **Quirks that are hard to see.** Integer overflow, order of insertion into lists, and `sh_int` fields wrapping.
  The guard tests and seeded scenarios are there for these. Missing a quirk shows up as a scenario diff, not a crash.
- **Speed.** Python is slower than C. ROM's pulse is 250 ms, and the stock world is small, so this is unlikely to
  matter, but P1 should time a pulse with all areas loaded.
- **Licence drift.** Porting is where headers get lost. Each module's header names its C source and keeps the notices;
  a guard test checks every module has one.
