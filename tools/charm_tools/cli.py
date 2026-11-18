"""python -m charm_tools <command> ...

    doctor                 check that the tools can run here
    explore areas          load every area as boot_db does: per-area counts, totals, bug() lines
    explore check          data checks on the loaded world
    explore parity         compare the loader with the real game (--docker IMAGE, or the saved capture)
    sim smoke [ARGS...]    the smoke test (see: python -m charm_tools sim smoke --help)
    sim bots [ARGS...]     bots playing while the Python game times its pulses (sim bots --help)
    port status            how much of the C game the Python game (game/) has ported, function by function
    port rng --docker IMG  check the C game's random numbers against game/tests/data/rng.json
    port data [--check]    generate game/charm/data/ from the C tables (--check: fail if it would change)
    port world             boot both games' worlds and compare them (--docker IMAGE, or the saved capture)
    port io                run comm.c's input and output cases through both games (--docker IMAGE, or saved)
    port greeting --docker IMG  connect to both games and compare what they send first
    port crypt             the Python game's DES crypt against glibc's (--docker IMAGE, or the saved cases)
    port login --docker IMG     the same login sessions against both games, byte for byte
    port players --docker IMG   player files saved by each game load in the other, key by key
    port commands --docker IMG  the same sessions in the game against both games, byte for byte
    port scenarios         scenario files through both games, line by line (--docker IMAGE, or the goldens)
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
        return bots_mod.main(argv[2:], prog="python -m charm_tools sim bots")
    if argv[:2] == ["sim", "smoke"]:
        from .sim import smoke as smoke_mod
        return smoke_mod.main(argv[2:], prog="python -m charm_tools sim smoke")

    ap = argparse.ArgumentParser(prog="python -m charm_tools", description="Tools for working on Charm.")
    ap.add_argument("--version", action="version", version=f"charm_tools {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    doc = sub.add_parser("doctor", help="check that the tools can run here")
    doc.add_argument("--image", default="charm", help="the game image to look for (default: charm)")

    exp = sub.add_parser("explore", help="read and check the game's areas")
    exp_sub = exp.add_subparsers(dest="explore_command", required=True, metavar="explore-command")
    exp_sub.add_parser("areas", help="per-area counts, the totals 'memory' prints, and the boot's bug() lines")
    exp_sub.add_parser("check", help="data checks on the loaded world")
    par = exp_sub.add_parser("parity", help="compare the loader with the real game")
    par.add_argument("--docker", metavar="IMAGE", help="capture from a throwaway container (default: the saved "
                                                       "capture in tools/fixtures/boot)")
    par.add_argument("--save", action="store_true", help="with --docker: save the capture as the new fixture")

    sim = sub.add_parser("sim", help="testing against a running game")
    sim_sub = sim.add_subparsers(dest="sim_command", required=True, metavar="sim-command")
    sim_sub.add_parser("smoke", help="the smoke test (handled above; listed here for --help)")
    sim_sub.add_parser("bots", help="bots playing while the game times its pulses (handled above)")

    port = sub.add_parser("port", help="the Python port of the game")
    port_sub = port.add_subparsers(dest="port_command", required=True, metavar="port-command")
    port_sub.add_parser("status", help="per C file: functions ported, and where they went")
    prng = port_sub.add_parser("rng", help="capture the C game's random numbers and compare with the fixture")
    prng.add_argument("--docker", metavar="IMAGE", required=True,
                      help="a build-stage image: docker build --target build -t charm:build .")
    prng.add_argument("--save", action="store_true", help="save the capture as the new fixture")
    pdata = port_sub.add_parser("data", help="generate game/charm/data/ from the C tables")
    pdata.add_argument("--check", action="store_true", help="write nothing; exit 1 if regenerating would change it")
    pworld = port_sub.add_parser("world", help="boot the C and Python worlds with one seed and compare them")
    pworld.add_argument("--docker", metavar="IMAGE",
                        help="a build-stage image to boot the C world in (default: the saved capture)")
    pworld.add_argument("--seed", action="append", metavar="N",
                        help="CHARM_SEED for both sides; repeat for more (default: the saved capture's)")
    pworld.add_argument("--time", metavar="T", help="current_time at boot (default: the saved capture's)")
    pworld.add_argument("--updates", type=int, help="area_update passes after boot (default: the saved capture's)")
    pworld.add_argument("--save", action="store_true", help="with --docker: save the C capture as the fixture")
    pio = port_sub.add_parser("io", help="run comm.c's input and output cases through both games and compare")
    pio.add_argument("--docker", metavar="IMAGE", help="a build-stage image (default: the saved capture)")
    pio.add_argument("--save", action="store_true", help="with --docker: save the C results as the fixture")
    pcrypt = port_sub.add_parser("crypt", help="check the Python game's password hashing against glibc's crypt")
    pcrypt.add_argument("--docker", metavar="IMAGE", help="a build-stage image (default: the saved cases)")
    pcrypt.add_argument("--save", action="store_true", help="with --docker: save the cases and answers")
    plogin = port_sub.add_parser("login", help="run the same login sessions against both games and compare")
    plogin.add_argument("--docker", metavar="IMAGE", required=True, help="a runtime image: docker build -t charm .")
    plogin.add_argument("--only", metavar="TEXT", help="only the scenarios whose name contains TEXT")
    pcommands = port_sub.add_parser("commands", help="run the same sessions in the game against both games")
    pcommands.add_argument("--docker", metavar="IMAGE", required=True, help="a runtime image: docker build -t charm .")
    pcommands.add_argument("--only", metavar="TEXT", help="only the scenarios whose name contains TEXT")
    pscen = port_sub.add_parser("scenarios", help="play the scenario files through both games and compare")
    pscen.add_argument("--docker", metavar="IMAGE", help="the build-stage image: docker build --target build")
    pscen.add_argument("--save", action="store_true", help="with --docker: write the goldens the tests replay")
    pscen.add_argument("--only", metavar="TEXT", help="only the scenarios whose name contains TEXT")
    pcov = port_sub.add_parser("coverage", help="the lines of the ported functions that no test or scenario runs")
    pcov.add_argument("c_files", nargs="*", metavar="FILE.c", help="only the functions ported from these C files")
    pcov.add_argument("--scenarios", action="store_true", help="run only the scenarios, not the unit tests")
    pplayers = port_sub.add_parser("players", help="round-trip player files between the two games")
    pplayers.add_argument("--docker", metavar="IMAGE", required=True, help="a runtime image: docker build -t charm .")
    pplayers.add_argument("--save", action="store_true", help="keep the C game's files for the tests")
    pgreet = port_sub.add_parser("greeting", help="connect to both games and compare the first bytes they send")
    pgreet.add_argument("--docker", metavar="IMAGE", required=True, help="a runtime image: docker build -t charm .")

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
            if args.save and not args.docker:
                ap.error("--save needs --docker")
            return commands.run_parity(args.docker, args.save)
    if args.command == "port":
        if args.port_command == "status":
            from .port import status
            return status.run()
        if args.port_command == "rng":
            from .port import rng
            return rng.run(args.docker, args.save)
        if args.port_command == "data":
            from .port import data
            return data.run(args.check)
        if args.port_command == "io":
            from .port import io
            if args.save and not args.docker:
                ap.error("--save needs --docker")
            return io.run(args.docker, args.save)
        if args.port_command == "crypt":
            from .port import cryptcheck
            if args.save and not args.docker:
                ap.error("--save needs --docker")
            return cryptcheck.run(args.docker, args.save)
        if args.port_command == "login":
            from .port import login
            return login.run(args.docker, args.only)
        if args.port_command == "commands":
            from .port import commands
            return commands.run(args.docker, args.only)
        if args.port_command == "scenarios":
            from .port import scenarios
            return scenarios.run(args.docker, args.save, args.only)
        if args.port_command == "coverage":
            from .port import coverage
            return coverage.run(args.c_files, args.scenarios)
        if args.port_command == "players":
            from .port import players
            return players.run(args.docker, args.save)
        if args.port_command == "greeting":
            from .port import greeting
            return greeting.run(args.docker)
        if args.port_command == "world":
            from .port import world
            custom = args.seed or args.time or args.updates is not None
            if not args.docker and custom:
                ap.error("--seed, --time and --updates need --docker (the saved capture has its own)")
            if args.save and (not args.docker or custom):
                ap.error("--save needs --docker, with the default seed, time and updates")
            return world.run(args.docker, args.seed or [world.SEED], args.time or world.TIME,
                             world.UPDATES if args.updates is None else args.updates, args.save)
    ap.error(f"unknown command {args.command}")  # unreachable: argparse enforces the choices
    return 2
