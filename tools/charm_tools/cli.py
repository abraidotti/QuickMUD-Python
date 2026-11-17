"""python -m charm_tools <command> ...

    doctor                 check that the tools can run here
    sim smoke [ARGS...]    the smoke test (see: python -m charm_tools sim smoke --help)
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

    sim = sub.add_parser("sim", help="testing against a running game")
    sim_sub = sim.add_subparsers(dest="sim_command", required=True, metavar="sim-command")
    sim_sub.add_parser("smoke", help="the smoke test (handled above; listed here for --help)")

    args = ap.parse_args(argv)

    if args.command == "doctor":
        from . import doctor
        return doctor.main(args.image)
    ap.error(f"unknown command {args.command}")  # unreachable: argparse enforces the choices
    return 2
