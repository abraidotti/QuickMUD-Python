"""Run the smoke test from the repo root: python tools/smoke.py --docker quickmud

A thin wrapper; the test lives in quickmud_tools/sim/smoke.py (python -m quickmud_tools sim smoke).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quickmud_tools.sim.smoke import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(prog="python tools/smoke.py"))
