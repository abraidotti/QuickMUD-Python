"""The fread_* ports (areafile/reader.py), quirk by quirk, against what Charm's db.c does.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for Charm; no single C source. Licence terms: README.md#licence-terms and doc/.
"""

import tempfile
import unittest
from pathlib import Path

from charm.world.areafile.reader import AreaParseError, Reader, int32, sh_int


def r(text):
    return Reader(text, "t.are")


class NumberTest(unittest.TestCase):
    def test_plain_signed_and_piped(self):
        rd = r("12 -3 +4 1|2|4")
        self.assertEqual([rd.read_number() for _ in range(4)], [12, -3, 4, 7])

    def test_consumes_one_trailing_space_only(self):
        rd = r("5  x")
        rd.read_number()
        self.assertEqual(rd.text[rd.pos:], " x")

    def test_other_terminators_are_pushed_back(self):
        rd = r("10d4")
        self.assertEqual(rd.read_number(), 10)
        self.assertEqual(rd.read_letter(), "d")

    def test_bad_format_is_fatal(self):
        with self.assertRaises(AreaParseError) as e:
            r("abc\n").read_number()
        self.assertEqual(e.exception.message, "Fread_number: bad format.")

    def test_wraps_like_a_c_int(self):
        self.assertEqual(r("2147483648").read_number(), -2147483648)


class FlagTest(unittest.TestCase):
    def test_letters_digits_and_pipes(self):
        rd = r("ABC 12 A|4")
        self.assertEqual([rd.read_flag() for _ in range(3)], [7, 12, 5])

    def test_repeated_letters_add_again(self):
        # ROM's fread_flag adds every letter (db.c:2743); Xania's counted a run once.
        self.assertEqual(r("AA").read_flag(), 2)

    def test_lower_case_letters_start_at_bit_26(self):
        self.assertEqual(r("a").read_flag(), 1 << 26)
        self.assertEqual(r("e").read_flag(), 1 << 30)

    def test_f_wraps_negative_and_g_up_adds_nothing(self):
        # flag_convert returns a long, but fread_flag sums into an int.
        self.assertEqual(r("f").read_flag(), -(1 << 31))
        self.assertEqual(r("g").read_flag(), 0)
        self.assertEqual(r("Ag").read_flag(), 1)

    def test_leading_minus_negates(self):
        self.assertEqual(r("-AB").read_flag(), -3)


class WordTest(unittest.TestCase):
    def test_plain_and_quoted(self):
        rd = r("stand 'two words' \"x y\"")
        self.assertEqual([rd.read_word() for _ in range(3)], ["stand", "two words", "x y"])

    def test_a_quote_counts_only_as_the_first_character(self):
        self.assertEqual(r("it's here").read_word(), "it's")

    def test_too_long_is_fatal(self):
        self.assertEqual(r("x" * 255 + " ").read_word(), "x" * 255)
        with self.assertRaises(AreaParseError) as e:
            r("x" * 256 + " \n").read_word()
        self.assertEqual(e.exception.message, "Fread_word: word too long.")

    def test_eof_is_fatal(self):
        with self.assertRaises(AreaParseError):
            r("   ").read_word()


class StringTest(unittest.TestCase):
    def test_up_to_tilde_with_cr_dropped(self):
        rd = r("  a\r\nb~ next\n")
        self.assertEqual(rd.read_string(), "a\nb")
        self.assertEqual(rd.read_word(), "next")

    def test_empty(self):
        self.assertEqual(r("~").read_string(), "")

    def test_files_are_read_as_raw_bytes(self):
        # plains.are and newthalos.are have "\n\r" inside strings. The C drops the \r; reading the file as text
        # would have turned it into a second newline.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "t.are")
            path.write_bytes(b"one\n\rtwo~")
            self.assertEqual(Reader.from_path(path).read_string(), "one\ntwo")

    def test_eof_logs_a_bug_and_returns_null(self):
        rd = r("no tilde\n")
        self.assertIsNone(rd.read_string())
        self.assertEqual([d.message for d in rd.diagnostics], ["Fread_string: EOF"])

    def test_string_eol(self):
        rd = r("  first line\nsecond")
        self.assertEqual(rd.read_string_eol(), "first line")
        with self.assertRaises(AreaParseError):
            rd.read_string_eol()  # no newline before EOF: fatal


class ToEolTest(unittest.TestCase):
    def test_skips_the_line_and_blank_lines(self):
        rd = r("rest of line\n\n\nnext\n")
        self.assertEqual(rd.read_to_eol(), "rest of line")
        self.assertEqual(rd.read_word(), "next")

    def test_a_word_at_eof_without_whitespace_is_fatal(self):
        # fread_word only ends an unquoted word at whitespace; at EOF it reads EOF until "word too long".
        with self.assertRaises(AreaParseError):
            r("last").read_word()

    def test_eof_would_hang_the_game(self):
        with self.assertRaises(AreaParseError):
            r("no newline").read_to_eol()


class BugLineTest(unittest.TestCase):
    """bug() prints how many lines start before the position (db.c bug())."""

    def test_counts_lines_started_before_the_position(self):
        rd = r("a\nb\nc")
        self.assertEqual(rd.bug_line(), 0)
        rd.pos = 1  # after "a"
        self.assertEqual(rd.bug_line(), 1)
        rd.pos = 2  # just after the first newline: line 2 hasn't started before it
        self.assertEqual(rd.bug_line(), 1)
        rd.pos = 3
        self.assertEqual(rd.bug_line(), 2)

    def test_diagnostic_log_lines(self):
        rd = r("x\n")
        rd.pos = 1
        rd.bug("CHECK_POS : size == -1 < 0")
        self.assertEqual(rd.diagnostics[0].log_lines(),
                         ["[*****] FILE: t.are LINE: 1", "[*****] BUG: CHECK_POS : size == -1 < 0"])

    def test_a_bug_past_the_last_newline_hangs(self):
        # bug() counts lines with while (getc (fpArea) != '\n'), which never ends on a last line with no newline
        # (tools/fixtures/boot/cases/eof_no_newline.are: the C game spins there)
        rd = r("first\nno newline")
        rd.pos = 6  # the start of the last line: the loop stops after one line (ftell is 6)
        self.assertEqual(rd.bug_line(), 1)
        rd.pos = 7  # one past it: the loop has to read the last line, and finds no newline
        with self.assertRaises(AreaParseError):
            rd.bug_line()
        rd.pos = len(rd.text)
        with self.assertRaises(AreaParseError) as e:
            rd.bug("Fread_string: EOF")
        self.assertIn("hangs", e.exception.message)
        self.assertEqual(e.exception.log, [])  # it prints nothing: not even its own FILE line
        self.assertEqual(rd.diagnostics, [])


class WrapTest(unittest.TestCase):
    def test_int32_and_sh_int(self):
        self.assertEqual(int32(1 << 31), -(1 << 31))
        self.assertEqual(sh_int(32768), -32768)
        self.assertEqual(sh_int(65536), 0)  # a vnum of 65536 ends a section, as in the game


if __name__ == "__main__":
    unittest.main()
