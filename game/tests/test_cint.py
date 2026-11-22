"""C integer behaviour (quickmud/core/cint.py).

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Written for QuickMUD-Python; no single C source.
Licence terms: README.md#licence-terms and doc/.
"""

import unittest

from quickmud.core.cint import c_div, c_mod, int32, sh_int, uint32


class CIntTest(unittest.TestCase):
    def test_wrapping(self):
        self.assertEqual(int32(2**31), -(2**31))
        self.assertEqual(int32(-1), -1)
        self.assertEqual(uint32(-1), 2**32 - 1)
        self.assertEqual(sh_int(32768), -32768)
        self.assertEqual(sh_int(65536), 0)

    def test_division_truncates_toward_zero(self):
        for a, b, q, r in [(7, 2, 3, 1), (-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1), (-1, 127773, 0, -1)]:
            with self.subTest(a=a, b=b):
                self.assertEqual((c_div(a, b), c_mod(a, b)), (q, r))
                self.assertEqual(c_div(a, b) * b + c_mod(a, b), a)


if __name__ == "__main__":
    unittest.main()
