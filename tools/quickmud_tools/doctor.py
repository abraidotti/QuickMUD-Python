"""doctor: check that the tools can run here.

Each check is ok, or fails with the reason. Exit 0 if everything is ok, 1 otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import paths

MIN_PYTHON = (3, 12)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_python() -> Check:
    v = sys.version_info
    return Check("python", v >= MIN_PYTHON,
                 f"{v.major}.{v.minor}.{v.micro}" + ("" if v >= MIN_PYTHON else f"; need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"))


def check_checkout() -> list[Check]:
    try:
        root = paths.find_root()
    except paths.RootNotFound as e:
        return [Check("checkout", False, str(e))]
    areas = [line.strip() for line in (paths.area_dir(root) / "area.lst").read_text(encoding="latin-1").splitlines()
             if line.strip().endswith(".are")]
    return [Check("checkout", True, str(root)),
            Check("game", (paths.game_dir(root) / "quickmud" / "__main__.py").is_file(), str(paths.game_dir(root))),
            Check("areas", bool(areas), f"{len(areas)} area files in area.lst")]


def _run(*argv: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_docker(image: str = "quickmud") -> list[Check]:
    if shutil.which("docker") is None:
        return [Check("docker", False, "docker isn't on PATH")]
    v = _run("docker", "version", "--format", "{{.Server.Version}}")
    if v is None or v.returncode != 0:
        return [Check("docker", False, "the docker daemon isn't answering (is Docker Desktop running?)")]
    checks = [Check("docker", True, f"server {v.stdout.strip()}")]
    img = _run("docker", "image", "inspect", "--format", "{{.Created}}", image)
    checks.append(Check(f"image {image}", img is not None and img.returncode == 0,
                        f"built {img.stdout.strip()[:19]}" if img is not None and img.returncode == 0
                        else f"no image; build it with: docker build -t {image} ."))
    return checks


def run(image: str = "quickmud") -> list[Check]:
    return [check_python(), *check_checkout(), *check_docker(image)]


def main(image: str = "quickmud") -> int:
    checks = run(image)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {'ok  ' if c.ok else 'FAIL'}  {c.name:<{width}}  {c.detail}")
    bad = [c for c in checks if not c.ok]
    print("all good" if not bad else f"{len(bad)} problem(s)")
    return 0 if not bad else 1
