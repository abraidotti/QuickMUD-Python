"""python -m charm_tools <command> ...

    doctor                 check that the tools can run here
    explore areas          load every area as boot_db does: per-area counts, totals, bug() lines
    explore check          data checks on the loaded world
    explore parity         compare the loader with the real game (--docker IMAGE, or the saved capture)
    sim smoke [ARGS...]    the smoke test (see: python -m charm_tools sim smoke --help)
    port status            how much of the C game the Python game (game/) has ported, function by function
    port rng --docker IMG  check the C game's random numbers against game/tests/data/rng.json
    port data [--check]    generate game/charm/data/ from the C tables (--check: fail if it would change)
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    # Commands with their own argument parser get everything after their name, untouched. (argparse.REMAINDER
    # drops a leading "--help" or "--docker", so they're dispatched before the top-level parser sees them.)
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

    port = sub.add_parser("port", help="the Python port of the game")
    port_sub = port.add_subparsers(dest="port_command", required=True, metavar="port-command")
    port_sub.add_parser("status", help="per C file: functions ported, and where they went")
    prng = port_sub.add_parser("rng", help="capture the C game's random numbers and compare with the fixture")
    prng.add_argument("--docker", metavar="IMAGE", required=True,
                      help="a build-stage image: docker build --target build -t charm:build .")
    prng.add_argument("--save", action="store_true", help="save the capture as the new fixture")
    pdata = port_sub.add_parser("data", help="generate game/charm/data/ from the C tables")
    pdata.add_argument("--check", action="store_true", help="write nothing; exit 1 if regenerating would change it")

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
    ap.error(f"unknown command {args.command}")  # unreachable: argparse enforces the choices
    return 2
