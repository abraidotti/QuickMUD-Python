"""charm_tools port io: comm.c's input and output in the Python game against the C game's, from the saved capture.

The capture is tools/tests/data/io.txt: tools/oracle/iocases.txt run through tools/oracle/iocheck.c. Recapture it
with python -m charm_tools port io --docker charm:build --save after changing the cases or the C.
"""

import unittest

from charm_tools.port import io


class SavedCapture(unittest.TestCase):
    def test_python_is_the_c(self):
        c = io.load(io.fixture_path())
        py = io.python_io(io.cases_path().read_text(encoding="latin-1"))
        self.assertGreater(len(c.out), 300)
        self.assertEqual(io.compare(c, py), [])

    def test_the_capture_has_the_quirks(self):
        c = io.load(io.fixture_path())
        text = "\n".join(c.out)
        self.assertIn("Line too long.", text)
        self.assertIn("PUT A LID ON IT", text)
        self.assertIn("[Hit Return to continue]", text)
        self.assertIn("test input spamming!", c.log)
        self.assertIn("EOF encountered on read.", c.log)  # a line that fills the buffer exactly reads 0 bytes


class Helpers(unittest.TestCase):
    def test_escapes_round_trip(self):
        raw = "a\\b\n\r\x1b\x00\xff~ "
        self.assertEqual(io.unesc(io.esc(raw).replace(" ", "\\s")), raw)
        self.assertEqual(io.unesc("x\\x41\\sy\\e"), "xA y\x1b")

    def test_pipe(self):
        a, b = io.pipe_pair()
        a.send(b"hi")
        self.assertEqual(b.recv(1), b"h")
        self.assertEqual(b.recv(10), b"i")
        with self.assertRaises(BlockingIOError):
            b.recv(10)
        self.assertEqual(b.recv(0), b"")  # read(fd, buf, 0): what the C sees as EOF


if __name__ == "__main__":
    unittest.main()
