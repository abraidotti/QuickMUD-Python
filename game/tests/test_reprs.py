"""The two guards against a test run that hangs: short reprs, and the watchdog.

A dataclass's default repr prints every field, so a character printed its room, the room its people, and so on:
a failing assertIn on the character list once hung a test for ten minutes (P5 PR 8). The game's linked classes
have short reprs now, and these check they stay short. The watchdog (quickmud.testing.watchdog) stops any test that
still hangs, with every thread's traceback; the last test runs one that does, in a subprocess.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import subprocess
import sys
import time
import unittest
from pathlib import Path

from quickmud.entities.create import create_object
from quickmud.net.descriptor import new_descriptor
from tests import test_commands  # (the module: importing its class would run its tests here too)

GAME = Path(__file__).resolve().parents[1]


class ShortReprs(unittest.TestCase):
    def setUp(self):
        self.case = test_commands.Commands()
        self.case.setUp()  # a small world, with a player in it
        self.game, self.ch = self.case.game, self.case.ch

    def tearDown(self):
        self.case.tearDown()

    def test_every_linked_class_is_short(self):
        game, ch = self.game, self.ch
        room = ch.in_room
        index = game.index
        obj = create_object(game, next(iter(index.objs.values())), 0)
        mob_index = next(iter(index.mobs.values()))
        things = {"Game": game, "Index": index, "Char": ch, "PCData": ch.pcdata, "Descriptor": ch.desc,
                  "Obj": obj, "Room": room, "Area": room.area, "MobIndex": mob_index,
                  "ObjIndex": obj.index, "a blank Descriptor": new_descriptor()}
        if any(e is not None for e in room.exit):
            things["Exit"] = next(e for e in room.exit if e is not None)
        if index.had_list:
            things["HelpArea"] = index.had_list[0]
        for name, thing in things.items():
            with self.subTest(name):
                text = repr(thing)
                self.assertLess(len(text), 200, text[:300])
                self.assertNotIn("\n", text)

    def test_a_failing_assertin_on_the_char_list_is_quick(self):
        stranger = test_commands.Commands()
        stranger.setUp()
        try:
            start = time.monotonic()
            with self.assertRaises(AssertionError):
                self.assertIn(stranger.ch, self.game.char_list)
            self.assertLess(time.monotonic() - start, 5)
        finally:
            stranger.tearDown()


class Watchdog(unittest.TestCase):
    def test_a_hanging_test_is_stopped_with_its_traceback(self):
        script = (
            "import time, unittest\n"
            "from quickmud.testing import watchdog\n"
            "watchdog.install()\n"
            "class Hangs(unittest.TestCase):\n"
            "    def test_sleeps(self):\n"
            "        time.sleep(60)\n"
            "unittest.main(argv=['hangs'])\n"
        )
        env = {**__import__("os").environ, "QUICKMUD_TEST_TIMEOUT": "2", "PYTHONPATH": str(GAME)}
        start = time.monotonic()
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=50)
        self.assertLess(time.monotonic() - start, 30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Timeout", r.stderr)
        self.assertIn("test_sleeps", r.stderr)

    def test_allow_gives_a_test_longer(self):
        from quickmud.testing.watchdog import allow

        @allow(600)
        def slow():
            pass

        self.assertEqual(slow.watchdog_seconds, 600)


if __name__ == "__main__":
    unittest.main()
