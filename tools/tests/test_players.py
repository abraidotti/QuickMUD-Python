"""charm_tools port players without Docker: the C game's saved files, loaded and saved again by the Python game.

tools/tests/data/players holds what the C game wrote in a port players --save run: Newbie, a character it made,
and Shemp and Smokegod after logging in with the fixtures. Recapture with
python -m charm_tools port players --docker charm:c --save after changing the C or the fixtures.
"""

import unittest

from charm_tools.port import players
from charm_tools.port.live import fixtures


def saved(name: str) -> str:
    return (players.saved_dir() / name).read_text(encoding="latin-1")


def logoff(text: str) -> int:
    return int(next(line.split()[1] for line in text.splitlines() if line.startswith("LogO")))


class RoundTrip(unittest.TestCase):
    def test_c_file_loads_and_saves_the_same_in_python(self):
        c = saved(players.NAME)
        self.assertEqual(players.compare(c, players.python_resave(c, players.NAME), "C", "Python"), [])

    def test_fixtures_log_in_the_same(self):
        for who, password in players.FIXTURE_PASSWORDS:
            with self.subTest(who=who):
                c = saved(f"{who}.after-login")
                fixture = (fixtures() / "player" / who).read_text(encoding="latin-1")
                py = players.python_resave(fixture, who, logoff(c), password)
                self.assertEqual(players.compare(c, py, "C", "Python"), [])


class Compare(unittest.TestCase):
    A = "#PLAYER\nName X~\nLogO 1\nPlyd 2\nLevl 3\nEnd\n\n#O\nVnum 9\nEnd\n\n#END\n"

    def test_clock_keys_are_left_out(self):
        b = self.A.replace("LogO 1", "LogO 5").replace("Plyd 2", "Plyd 7")
        self.assertEqual(players.compare(self.A, b, "a", "b"), [])

    def test_names_the_key(self):
        b = self.A.replace("Levl 3", "Levl 4")
        self.assertEqual(players.compare(self.A, b, "a", "b"), ["section 0 (#PLAYER): a Levl '3', b Levl '4'"])

    def test_spacing_counts(self):
        a = self.A.replace("Levl 3", "Titl  the Recruit~")
        b = self.A.replace("Levl 3", "Titl the Recruit~")
        self.assertEqual(len(players.compare(a, b, "a", "b")), 1)

    def test_sections_must_match(self):
        b = self.A.replace("#O\nVnum 9\nEnd\n\n", "")
        self.assertTrue(players.compare(self.A, b, "a", "b")[0].startswith("sections:"))


if __name__ == "__main__":
    unittest.main()
