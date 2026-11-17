# Plan: bring the Xania tools into Charm

Status: T0 and T1 in review, 2026-11-17 (#16). Decisions 1-4 answered as recommended; Docker replaced WSL as the
place the game runs (decision 5, #1). Decisions 6-7 are still open.

## Goal

Charm should be workable on its own: open `charm/` and have assessment, testing and the research-gate-ship loop
available, with no `xania*` folders open. Today those tools live in three repositories, all aimed at Xania (C++):

| Tool | Repo (commit this plan was written against) | What it does for Xania |
|---|---|---|
| Explorer | `xania-explorer` (main, 90cfc79) | Reads area files and C++ tables; assesses 10 systems per level; bug checks; findings site |
| Sim | `xania-sim` (main, 8d403f2) | Isolated test MUD; bots that play over telnet; trials with `--json` and exit codes; findings database |
| Builder | `xania-builder` (main, cb7c692) | Research dossier, gate (builds, tests, before/after, Sim trials), ship a PR, dossier site |

End state: `charm/tools/` holds one Python package that does the same jobs for Charm's C code and ROM-format areas,
and `charm/` documents the working process the tools assume. The Xania repositories stay as they are and keep
serving Xania. Nothing here changes them.

## Decisions (recommended answers first)

1. **Package shape.** One package, `charm_tools`, with `explore`, `sim` and `build` subpackages and one CLI
   (`python -m charm_tools explore|sim|build ...`). *Recommended:* one repo, one version, no cross-repo API pinning.
   Alternative: three packages, as for Xania. This only pays off if the tools are later shared between MUDs.
2. **How code comes over.** Copy files in, adapted, with a provenance line in each module docstring
   (`Ported from xania-sim 8d403f2 core/telnet.py`). *Recommended* over `git subtree`, which would bring three
   histories of Xania-specific commits into Charm.
3. **Tool licence.** The tools are the user's own MIT-licensed code. Keep `tools/LICENSE` (MIT) separate from the
   Diku/Merc/ROM terms that bind the game code. The tools read the game's source but don't link or ship it.
   *Recommended:* yes.
4. **Constraints kept from Explorer.** Analysis stays stdlib-only, pure Python. *Recommended:* keep stdlib-only. Drop
   the Pyodide 60-second budget until Charm wants an in-browser explorer.
5. **Where the test MUD runs.** ROM is one process (`rom <port>`, no doorman), so it's simpler to host than Xania.
   *Recommended:* WSL or Linux first, as with Sim. Docker can come later as a portable gate backend (refactor R0
   updates the Dockerfile anyway).
6. **Level range.** ROM has mortal levels 1-50, hero 51, immortals 52-60 (`MAX_LEVEL 60`). *Recommended:* per-level
   stats over 1-51 and per class (mage, cleric, thief, warrior), the same convention as the Xania assessments.
7. **Site.** A static findings site (GitHub Pages on `abraidotti/charm`) or local HTML only. *Recommended:* local
   first, Pages once the first assessments are worth sharing.

## What carries over

| Piece | Verdict | Notes for Charm |
|---|---|---|
| Explorer `areafile/` reader, parser, model, world | **Adapt** | ROM 2.4 is the ancestor of Xania's format. Re-check every section against `db.c` (`#AREA`, `#AREADATA` from OLC saves, `#MOBILES`, `#MOBOLD`, `#OBJECTS`, `#OBJOLD`, `#ROOMS`, `#RESETS`, `#SHOPS`, `#SPECIALS`, `#HELPS`, `#MOBPROGS`, `#SOCIALS`). Stock areas use the new formats and no `#MOBPROGS`, but `asave` writes `#AREADATA`, so both header forms are needed. Stay faithful to `db.c` quirks. |
| Explorer `areafile/graph.py`, `flags.py` | **Adapt** | Graph code is format-neutral; flag letters come from `merc.h` and `tables.c`. |
| Explorer `source/` (C++ table readers) | **Rewrite** | Positional C initialisers in `const.c` (class, race, pc_race, title, liquid, weapon, attack tables), `tables.c` (flag tables) and `skill_table`. Same approach: narrow brace-matching readers that fail loudly. |
| Explorer `assess/` (10 systems) | **Rewrite formulas, keep structure** | `System` (needs/uses, isolation, "unknown" never "fixed") and `findings.Story` port as they are. Each formula is re-derived from ROM's `fight.c`, `magic.c`, `handler.c`, `update.c` and `db.c`, with source pointers. |
| Explorer `bugs/checks.py` | **Split** | Data checks port (unreachable rooms, never-spawn, unlisted, exit/shop nulls, unobtainable, vanish-on-save, fatal/load warnings). Code checks tied to Xania lines stay behind; their questions are asked again of ROM code (see "Re-test, don't assume"). |
| Explorer `site/`, `gen/` | **Adapt** | Findings-first pages, recommendations regenerated from data. Retitle and drop the upstream-vs-fork compare until Charm has two versions worth comparing. |
| Sim `core/telnet.py`, `session.py` | **Adapt** | ROM login asks about ANSI first unless `qmconfig ansiprompt` is off. Test config sets it off. The bot prompt uses ROM tokens: `<bot %h/%H %m/%M %v/%V %x %g>` (`bust_a_prompt` in `comm.c`). ROM has no wait-state token (Xania's `%c`); see refactor R1. |
| Sim `core/server.py` | **Rewrite** | Start `area/rom <port>` in a throwaway copy of `area/` with its own player dir. Needs refactor R1 (paths are compile-time `#define`s today: `PLAYER_DIR "../player/"`). |
| Sim `core/director.py` | **Adapt** | ROM player files use `Levl` too (`save.c`). Immortal commands differ in places; re-verify each wrapped command against `interp.c` and `act_wiz.c`. |
| Sim `record/` (events, findings, store, heartbeat, watchdog, result) | **Port as-is** | Format-neutral. Keep `TrialResult` JSON and exit codes (0 clean, 1 new findings, 2 couldn't run) stable for Builder. |
| Sim `activities/`, `players/`, `setup/` | **Adapt** | Text parsers change (ROM messages, ROM classes). Kits rebuilt from Charm's shops and objects. |
| Sim trials: smoke, lobby, churn, hunt, skill, weapon, area | **Adapt**, in that order | Lobby and churn are the cheapest bug finders and need the least game knowledge. |
| Sim `report/dispatch.py` | **Adapt** | Static findings site, as for Explorer. |
| Builder `source.py` (lexical index) | **Rewrite for C** | Simpler than C++: no classes or namespaces. Commands come from `cmd_table` in `interp.c` and `DECLARE_DO_FUN` in `interp.h`. |
| Builder `research.py`, `history.py`, `helps.py`, `idea.py` | **Adapt** | The seven-section dossier stays. The "idioms" list targets C (`sprintf`/`strcat`/fixed buffers as legacy; `snprintf`/`strlcpy` as modern). Helps come from `area/help.are`, `rom.are` and OLC's `olc.hlp`. |
| Builder `gate.py` | **Adapt, smaller at first** | Steps that exist now: builds (Release `-O2`; Debug with ASan and UBSan once R3 makes it usable), Sim trials, static detectors. Steps that wait for the refactor: format check (R5), unit tests and before/after (R4). |
| Builder `ship.py`, `site.py` | **Adapt** | Ship to `abraidotti/charm` only. `avinson/rom24-quickmud` has been quiet since 2018 and isn't an upstream for this work. |
| Companions (`xania-companions`) | **Out of scope** | Not part of this plan. |

### Stays behind

Doorman, `ctest`, `clang-format` CI parity, the `mattgodbolt/xania` upstream flow, Xania-specific content facts
(the lit war banner every new character holds, NewbiesOnly rooms, Xania's four classes and levels 1-91) and every
check that cites a Xania file and line.

### Re-test, don't assume

Several Xania bugs have ROM ancestors, but the C code differs. Treat each as a question for a Charm trial, not a known
bug:

- autoloot `get all corpse` (xania#1 came from C++ `string_view` indexing; ROM uses C strings)
- quit and descriptor lifetime around `extract_char` (xania#2)
- empty replies at login prompts (xania#3; QuickMUD's `nanny.c` and colour login differ)
- `practice ''` and `cast ''` (Xania fork #7)
- vampiric drain, harm's damage type, dark vision, level-loss asymmetry (Xania fork #9-#11 and Explorer checks)
- copyover with half-created characters (fixed by Blake Pell; keep a regression trial)

## Phases

Each phase ends with something runnable and its tests passing. Phases T1-T3 are static analysis and need only the
source. T4 onwards needs a running Charm, so it depends on the refactor plan's R0 and R1.

| Phase | Delivers | Depends on |
|---|---|---|
| **T0 Skeleton** | `tools/` with `pyproject.toml`, `charm_tools` package, CLI stub, test runner, stdlib-only test, `tools/LICENSE`, `doctor` (finds `src/`, `area/`, a built `area/rom`, Python version) | - |
| **T1 World** | ROM area parser with diagnostics matching `db.c` (`bug()` vs fatal), world validation, graph, data bug checks; a test that every stock area loads with the same counts `boot_db` logs | T0 |
| **T2 Tables and first systems** | C table readers; Characters, Mobs and Weapons systems with per-level, per-class tables and source pointers | T1 |
| **T3 Remaining systems and site** | Equipment, Combat & XP, Skills, Economy, Levelling, Difficulty, Bugs; findings, recommendations and local site | T2 |
| **T4 Sim core** | Telnet, session, isolated server, director, `smoke` and `lobby` trials, findings database, watchdog | T0, R0, R1 |
| **T5 Sim trials** | churn, hunt, skill, weapon, area trials; predicted vs observed via the T2/T3 models; dispatch site | T3, T4 |
| **T6 Builder** | C source index, research dossier, gate (builds + Sim + static), ship to the fork, dossier site; first pilot: a small, real Charm bug found in T4/T5 | T5 |
| **T7 Stand alone** | `charm/CLAUDE.md` with the process rules below; the README's tool section; closing the loop by opening only `charm/` and running doctor, an assessment, a trial and a gate | T6 |

Refactor phases after R1 (see [refactor.md](refactor.md)) are best run through the gate once T6 exists. Until then,
each one runs the T4/T5 trials before and after.

## Process rules to carry over

These are how the Xania tools are used. They go into `charm/CLAUDE.md` in T7 so they're in the repo, not only in
someone's memory:

- **Issue first for decisions.** A change with judgement calls starts as an issue with options and recommended
  answers. The PR comes after the questions are answered.
- **Bug issues** have Summary, How to reproduce, Faulty lines, Suggested fix and How this was found.
- **PRs** are thorough, verified and explainable, and link to the dossier site.
- **Every change** passes the gate on the fork before it's called done.
- **Live trials fail fast**: preflight with `--quick` before long runs; heartbeat, caps and `--fail-fast`.
- **Assessments** report per level (1-51) and per class where it matters. Prose is generated from data, and claims
  are checked against the numbers. Missing source is "unknown", never "fixed".
- **Recommendations** are regenerated from data, ranked by impact x effort, and written after the assessments.

## Gotchas learned on Xania

Most of these were found the hard way. They apply to Charm unless noted.

- On Windows, connect to `127.0.0.1`, not `localhost` (WSL doesn't forward `::1`).
- Pass shell scripts to `wsl.exe` on stdin as bytes. It expands `$VARS` in arguments, and text mode adds `\r`.
- WSL stops a distro when no `wsl.exe` session is attached, so the start script stays in the foreground.
- Killing Python on Windows can leave `wsl.exe`, `bash` and the server running. A leftover server on a port makes
  every later start on that port fail. Reap by owner pid and port, and fail if the port can't be bound.
- The MUD prompts on its own (ticks). Commands that matter wait for an expected reply, not just any prompt.
- Room names repeat. Navigation uses fingerprints plus dead reckoning.
- Bash and trip leave the victim resting in Xania. Check whether ROM does the same before porting the auto-stand.
- Player names can't prefix any mob keyword, or targeting breaks.
- One root cause can show up as several crash signatures. Link them to one finding.
- `pytest | tail` hides failures; check the exit status.
