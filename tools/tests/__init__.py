"""charm_tools' tests. Every test runs under the game's watchdog (charm.testing.watchdog): one that
hangs stops the run with every thread's traceback."""

from charm_tools.paths import use_game

use_game()

from charm.testing import watchdog  # noqa: E402

watchdog.install()
