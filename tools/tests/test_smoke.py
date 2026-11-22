"""Unit tests for the smoke test's telnet handling. The live run is: python -m quickmud_tools sim smoke --docker quickmud"""

import unittest

from quickmud_tools.sim import smoke

IAC, WILL, WONT, ECHO, GA = 255, 251, 252, 1, 249


class CleanTest(unittest.TestCase):
    def clean(self, data: bytes) -> str:
        s = smoke.Session.__new__(smoke.Session)  # no socket needed for _clean
        return s._clean(data)

    def test_strips_telnet_option_negotiation(self):
        # The game turns echo off for passwords (IAC WILL ECHO) and back on (IAC WONT ECHO).
        self.assertEqual(self.clean(bytes([IAC, WILL, ECHO]) + b"Password: " + bytes([IAC, WONT, ECHO])),
                         "Password: ")

    def test_strips_two_byte_commands(self):
        self.assertEqual(self.clean(b"<20hp>" + bytes([IAC, GA])), "<20hp>")

    def test_strips_ansi_colour(self):
        self.assertEqual(self.clean(b"\x1b[1;31mAnsi enabled!\x1b[0m"), "Ansi enabled!")

    def test_keeps_latin1_text(self):
        self.assertEqual(self.clean("Stærfeldt".encode("latin-1")), "Stærfeldt")


class FixturesTest(unittest.TestCase):
    def test_fixtures_are_where_docker_mode_copies_them_from(self):
        self.assertTrue((smoke.FIXTURES / "player" / smoke.IMMORTAL[0]).is_file())
        self.assertTrue((smoke.FIXTURES / "qmconfig.rc").is_file())

    def test_immortal_fixture_is_level_60(self):
        text = (smoke.FIXTURES / "player" / smoke.IMMORTAL[0]).read_text(encoding="latin-1")
        self.assertIn("\nLevl 60\n", text)


if __name__ == "__main__":
    unittest.main()
