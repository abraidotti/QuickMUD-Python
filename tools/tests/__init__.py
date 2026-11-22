"""quickmud_tools' tests. Every test runs under the game's watchdog (quickmud.testing.watchdog): one that
hangs stops the run with every thread's traceback."""

from quickmud_tools.paths import use_game

use_game()

from quickmud.testing import watchdog  # noqa: E402

watchdog.install()
