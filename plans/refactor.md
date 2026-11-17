# Plan: refactor Charm's code

Status: proposed, 2026-11-17. Nothing started.

## Goal

Make the QuickMUD code safe and testable to change, so new game work can go in with confidence. This plan is about
the code. Gameplay changes come later, after the assessments in [tools-port.md](tools-port.md) say what needs
changing.

## Ground rules

- **Behaviour first.** Until R6, every phase preserves gameplay. A refactor that changes numbers, messages or area
  loading is a bug. The safety net is the tools: Explorer's tables and bug checks should be unchanged before and
  after, and Sim's trials should be clean on both sides.
- **Credits and licences stay.** Copyright headers in `src/` aren't touched. The greeting, `credits`, `help diku`,
  `help merc` and `help rom` keep what the licences require (see the README's licence section). The game is never
  called ROM.
- **Small, reviewable changes.** One concern per PR. Large mechanical changes (formatting, renames) go in their own
  commits and are listed in `.git-blame-ignore-revs`.
- **Issue first** for anything with a judgement call. The decisions below are the first such issues.

## Starting point

Measured on master (364c26f), 2026-11-17:

- C, about 64k lines in `src/`. `merc.h` alone is 85 KB, and `imc.c` is 228 KB.
- Builds with `gcc -O -g3 -Wall`, linked with `-lcrypt`. The Dockerfile uses `ubuntu:14.04`. It hasn't been built on
  a current compiler for this plan yet.
- `area/startup` is a csh script. The binary is `area/rom` and runs from `area/`.
- Paths are compile-time constants (`PLAYER_DIR "../player/"`, `GOD_DIR`, `TEMP_FILE`, `EXE_FILE "../area/rom"`).
- Legacy string handling: 744 `sprintf`, 435 `strcat` and 76 `strcpy` calls into fixed buffers
  (`MAX_STRING_LENGTH` is 4608).
- Passwords use DES `crypt()` salted with the character's name (`nanny.c`, `act_info.c` `do_password`). DES uses
  only the first 8 characters.
- 66 `macintosh`/`MSDOS` preprocessor branches across 40 files, and four Makefiles.
- IMC2 (with `sha256.c`, used only by IMC2) is built in by default.
- No unit tests, no formatter, no CI, and no `.gitignore` for `src/obj/` or `area/rom`.

## Decisions (recommended answers first)

1. **C or C++?** *Recommended: stay in C (C17) for now.* Modernise in place, and revisit once the tests and tools
   exist. Xania's move to C++ worked out, but it went along with unit tests and CI that Charm doesn't have yet. Moving early
   would also change every line Explorer's table readers depend on. Alternative: compile as C++ from R5 and adopt it
   gradually.
2. **IMC2.** *Recommended: remove it.* Turn it off in the Makefile in R2, check nothing else depends on it, then
   delete `imc.c`, `imc.h`, `imccfg.h`, `sha256.*` and `imc/` in a later commit. Credits for IMC2 stay in the
   README's lineage. Alternative: keep it behind the existing `-DIMC` flag, off by default.
3. **Password hashing.** *Recommended: libxcrypt's `crypt()` with a modern method (yescrypt or SHA-512 `$6$`) and a
   random salt, rehashing on the next successful login.* Old DES hashes keep working until then. Alternative: a
   bundled PBKDF2. SHA-256 on its own isn't a password hash.
4. **Unit test framework.** *Recommended: a small single-header C test framework with a permissive licence (to pick
   in R4), or a tiny in-house runner.* Tests build against the game's object files minus `main`.
5. **Formatter.** *Recommended: `clang-format` with a checked-in `.clang-format`, run once over `src/` in R5* (not
   earlier, so the pruning in R2 doesn't fight the reformat). The tables in `const.c` and `tables.c` stay hand-laid
   with `// clang-format off` if the formatter mangles them.
6. **Tables in C or in data files?** *Recommended: keep them in C during this plan.* Moving class, skill and race
   tables into data files would help balance work, but it's a gameplay-facing change with its own issue later, and
   Explorer's readers follow whichever form exists.

## Phases

| Phase | What | Done when |
|---|---|---|
| **R0 Baseline** | Build on a current gcc and clang (WSL and an updated Dockerfile). Record every warning. Add `.gitignore` for `src/obj/`, `area/rom`, logs and test player files. Replace `area/startup` with a POSIX `sh` script (keep the csh one until the new one is proven). Write down the manual smoke test: boot, create a character, save, quit, log back in, copyover. | Clean build on both compilers (warnings listed, not yet fixed); smoke test passes |
| **R1 Runnable by tools** | Command-line options or environment variables for the area dir, player dir, god dir, temp file, log file and executable path (for copyover), defaulting to today's values. A clean shutdown on SIGTERM. A test `qmconfig.rc` with the ANSI prompt off. A wait-state prompt token (for example `%W`), the one game-facing change here, so bots can see lag as they do on Xania. | Two instances on different ports with separate player dirs run side by side; Sim T4 can start one |
| **R2 Prune** | Remove the `macintosh`/`MSDOS` branches and the extra Makefiles. Decision 2 for IMC2. Drop dead code flagged by the compiler and by Builder's index (unused functions, unreachable `#if 0` blocks). | Builds and smoke test unchanged; Explorer output unchanged |
| **R3 Memory and string safety** | Debug build with `-fsanitize=address,undefined`. Replace unbounded `sprintf`/`strcat`/`strcpy` with `snprintf` and `strlcpy`/`strlcat` (already licensed in `imc/STRLCPY-STRLCAT-LICENSE`), file by file, starting with input paths: `comm.c`, `nanny.c`, `interp.c`, then `act_*.c`. Decision 3 for passwords. Fix whatever the sanitizers and Sim's lobby, churn and hunt trials find, each as its own issue and PR. | Sanitizer build runs every Sim trial clean; no unbounded string writes left in input-handling code |
| **R4 Tests** | Decision 4. A test target in the Makefile, then tests for pure functions first: dice and number ranges, `str_prefix` and argument parsing, flag conversions, `act()` formatting, area loading of every stock area with zero `bug()` lines. Builder's gate gains unit tests and the before/after step. | `make test` runs in the gate; every R3 fix after this point comes with a test |
| **R5 Structure** | Decision 5 (one formatting commit). Split `merc.h` into headers by area (characters, objects, rooms, combat, tables, descriptors) while `merc.h` still includes them all. Group the `do_*` commands by topic. Make warnings errors in CI. Add a CI workflow (build both compilers, sanitizers, tests, Sim smoke). | CI green on every push; `merc.h` is an index of smaller headers |
| **R6 Identity** | Rename the game to Charm in the greeting, `help charm`, `version` and the who list, with the Diku, Merc and ROM credits kept on the login screen as the licences require. This is the first deliberately visible change. | Greeting fits a 24-line terminal with all required credits; licence checklist ticked in the PR |

R0 and R1 come first because the tools need them. R2-R6 run through Builder's gate once tools-port T6 exists; before
then, through the Sim trials from T4-T5 and an Explorer before/after diff.

## Risks

- **Copyover.** It re-executes the binary with open descriptors. R1's path changes and R3's string changes both touch
  it. Keep a copyover trial in Sim from the start, including the half-created-character case Blake Pell fixed.
- **Player file compatibility.** R3's password change and any later save-format change must read old files. Keep
  Shemp's file as a fixture.
- **Area file round-trips.** OLC's `asave` rewrites area files (`#AREADATA` header). A test should load, save and
  reload an area and compare.
- **Licence drift.** Renaming the game (R6) is the point where credits tend to get lost. The PR checks the login
  screen, `credits` and the three help entries against the licences.
