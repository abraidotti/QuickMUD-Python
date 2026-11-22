"""python -m quickmud_tools <command> ...

    doctor                 check that the tools can run here
    explore areas          load every area as boot_db does: per-area counts, totals, bug() lines
    explore check          data checks on the loaded world
    explore parity         compare the loader with the C game's saved capture (tools/fixtures/boot)
    sim smoke [ARGS...]    the smoke test (see: python -m quickmud_tools sim smoke --help)
    sim bots [ARGS...]     bots playing while the game times its pulses (sim bots --help)
    sim lobby [ARGS...]    awkward replies at every login prompt (sim lobby --help)
    sim churn [ARGS...]    bots creating characters and quitting (sim churn --help)
    port status            the C functions the game ported (frozen at c-final) and where each went
    port coverage [FILE.c] the lines of the ported functions that no test or scenario runs
    port world             boot the game's world and compare it with the C game's saved capture
    port io                run comm.c's input and output cases and compare with the C game's saved results
    port crypt             the game's DES crypt against glibc's saved answers
    port players           the C game's saved player files, loaded and saved by the game, key by key
    port scenarios         the scenario files against their goldens, line by line (--save: write them again)

The checks that ran the C game live are at the c-final tag (#112).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    # Commands with their own argument parser get everything after their name, untouched. (argparse.REMAINDER
    # drops a leading "--help" or "--docker", so they're dispatched before the top-level parser sees them.)
    if argv[:2] == ["sim", "bots"]:
        from .sim import bots as bots_mod
        return bots_mod.main(argv[2:], prog="python -m quickmud_tools sim bots")
    if argv[:2] == ["sim", "lobby"]:
        from .sim import lobby as lobby_mod
        return lobby_mod.main(argv[2:], prog="python -m quickmud_tools sim lobby")
    if argv[:2] == ["sim", "churn"]:
        from .sim import churn as churn_mod
        return churn_mod.main(argv[2:], prog="python -m quickmud_tools sim churn")
    if argv[:2] == ["sim", "smoke"]:
        from .sim import smoke as smoke_mod
        return smoke_mod.main(argv[2:], prog="python -m quickmud_tools sim smoke")

    ap = argparse.ArgumentParser(prog="python -m quickmud_tools", description="Tools for working on QuickMUD-Python.")
    ap.add_argument("--version", action="version", version=f"quickmud_tools {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    doc = sub.add_parser("doctor", help="check that the tools can run here")
    doc.add_argument("--image", default="quickmud", help="the game image to look for (default: quickmud)")

    exp = sub.add_parser("explore", help="read and check the game's areas")
    exp_sub = exp.add_subparsers(dest="explore_command", required=True, metavar="explore-command")
    exp_sub.add_parser("areas", help="per-area counts, the totals 'memory' prints, and the boot's bug() lines")
    exp_sub.add_parser("check", help="data checks on the loaded world")
    exp_sub.add_parser("parity", help="compare the loader with the C game's saved capture")

    sim = sub.add_parser("sim", help="testing against a running game")
    sim_sub = sim.add_subparsers(dest="sim_command", required=True, metavar="sim-command")
    sim_sub.add_parser("smoke", help="the smoke test (handled above; listed here for --help)")
    sim_sub.add_parser("bots", help="bots playing while the game times its pulses (handled above)")
    sim_sub.add_parser("lobby", help="awkward replies at every login prompt (handled above)")
    sim_sub.add_parser("churn", help="bots creating characters and quitting (handled above)")

    port = sub.add_parser("port", help="the Python port of the game")
    port_sub = port.add_subparsers(dest="port_command", required=True, metavar="port-command")
    port_sub.add_parser("status", help="per C file: functions ported, and where they went")
    port_sub.add_parser("world", help="boot the world and compare it with the C game's saved capture")
    port_sub.add_parser("io", help="run comm.c's input and output cases and compare with the C game's results")
    port_sub.add_parser("crypt", help="check the game's password hashing against glibc's saved answers")
    port_sub.add_parser("players", help="load and save the C game's saved player files, and compare")
    pscen = port_sub.add_parser("scenarios", help="play the scenario files and compare with their goldens")
    pscen.add_argument("--save", action="store_true",
                       help="after a deliberate change: write the goldens again from the game (check the diff)")
    pscen.add_argument("--only", metavar="TEXT", help="only the scenarios whose name contains TEXT")
    pcov = port_sub.add_parser("coverage", help="the lines of the ported functions that no test or scenario runs")
    pcov.add_argument("c_files", nargs="*", metavar="FILE.c", help="only the functions ported from these C files")
    pcov.add_argument("--scenarios", action="store_true", help="run only the scenarios, not the unit tests")

    args = ap.parse_args(argv)

    if args.command == "doctor":
        from . import doctor
        return doctor.main(args.image)
    if args.command == "explore":
        from .explore import commands
        if args.explore_command == "areas":
            return commands.areas()
        if args.explore_command == "check":
            return commands.check()
        if args.explore_command == "parity":
            return commands.run_parity()
    if args.command == "port":
        if args.port_command == "status":
            from .port import status
            return status.run()
        if args.port_command == "io":
            from .port import io
            return io.run()
        if args.port_command == "crypt":
            from .port import cryptcheck
            return cryptcheck.run()
        if args.port_command == "scenarios":
            from .port import scenarios
            return scenarios.run(args.save, args.only)
        if args.port_command == "coverage":
            from .port import coverage
            return coverage.run(args.c_files, args.scenarios)
        if args.port_command == "players":
            from .port import players
            return players.run()
        if args.port_command == "world":
            from .port import world
            return world.run()
    ap.error(f"unknown command {args.command}")  # unreachable: argparse enforces the choices
    return 2
