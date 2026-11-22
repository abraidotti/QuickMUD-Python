# Charm: notes for Claude

Charm is a new MUD built on ROM 2.4b6 via QuickMUD, in Python (`game/`; areas in `area/`). It's a port of QuickMUD's
C game, at parity with it; the C is at the `c-final` tag (#112). Origin: `abraidotti/charm`, a fork of
`avinson/rom24-quickmud`. No upstream for our work: PRs go to `abraidotti/charm` only.

## Read first

- [README.md](README.md): lineage, credits and licence obligations.
- [plans/tools-port.md](plans/tools-port.md): porting Explorer, Sim and Builder into `tools/` (phases T0-T7).
- [plans/refactor.md](plans/refactor.md): refactor phases R0-R6.
- [plans/python-port.md](plans/python-port.md): porting the game to Python (phases P0-P6, done at `v1.0`).

A plan decision marked *Recommended* has **not been confirmed** by the user: ask before acting on one. Decisions
marked *Answered* have been.

## Source for the port

The Xania tools live in `../xania-sandro/` and are read by path. They're Xania's, so don't modify them:

- `../xania-sandro/xania-explorer` (main, 90cfc79): assessment
- `../xania-sandro/xania-sim` (main, 8d403f2): testing bots
- `../xania-sandro/xania-builder` (main, cb7c692): research, gate, ship
- `../xania-sandro/xania`: the Xania game (C++), for reference only

## Hard rules

- Never touch the Diku/Merc/ROM copyright headers: each `game/` module's licence header, and the C's own at
  `c-final`. Keep the credits the licences require (login screen, `credits`, `help diku`, `help merc`, `help rom`,
  OLC's version credits) and the README's licence checklist. Never call the game ROM.
- Refactors preserve behaviour until plan phase R6. Check with Explorer output and Sim trials before and after.
- Tools: stdlib-only Python for analysis; MIT licence in `tools/LICENSE`, kept separate from the game's licences.
- `game/` is under the game's licences, not MIT. Every module keeps the short licence header, and every ported
  function keeps its `# C: <file>.c <function>` marker above its `def` (checked against the C functions frozen at
  `c-final`); tests enforce both. `game/charm/data/` is edited by hand now (it was generated from the C).
- A deliberate change to behaviour (a bug fix) updates the saved C output it changes in the same PR: the goldens
  with `charm_tools port scenarios --save --only NAME` (first line `python`), and the other captures by hand, so the
  diff shows what changed.
- Commit or push only when the user asks. Commit messages are casual.

## How the user works

- **Issue first for decisions.** A change with judgement calls starts as an issue on `abraidotti/charm` with options
  and recommended answers. Open the PR only after every question is answered.
- **Bug issues** have these sections: Summary, How to reproduce, Faulty lines, Suggested fix, How this was found.
- **PRs** are thorough, verified and explainable (what changed, why, and the proof), and link to the dossier site
  once it exists.
- **Every change** is tested (gate or Sim trials) before it's called done.
- **Live trials fail fast**: preflight with `--quick` before a long run; heartbeat, caps and `--fail-fast`.
- **Assessments** give per-level stats (1-51) per class where relevant. Prose is generated from data and checked
  against the numbers. Missing source is reported as "unknown", never "fixed".
- **Recommendations** are regenerated from data, ranked by impact x effort, and written after the assessments.

## Environment

- Windows host; the game runs here or in WSL2 (distro `Ubuntu-26.04`, user `alessandro`, passwordless sudo), and
  copyover needs Linux.
- Gotchas from Xania are listed at the end of `plans/tools-port.md`. The main ones: use `127.0.0.1`, not
  `localhost`; feed scripts to `wsl.exe` on stdin as bytes; when you kill a run, clean up the whole process tree and
  not just the game.
