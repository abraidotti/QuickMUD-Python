import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quickmud_tools import paths


class PathsTest(unittest.TestCase):
    def test_finds_this_checkout(self):
        root = paths.find_root()
        self.assertTrue((root / "game" / "quickmud" / "__init__.py").is_file())
        self.assertTrue((root / "area" / "area.lst").is_file())
        self.assertEqual(paths.game_dir(root), root / "game")

    def test_quickmud_root_must_be_a_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"QUICKMUD_ROOT": tmp}):
            with self.assertRaises(paths.RootNotFound):
                paths.find_root()

    def test_quickmud_root_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            for m in paths.MARKERS:
                (Path(tmp) / m).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / m).write_text("")
            with mock.patch.dict(os.environ, {"QUICKMUD_ROOT": tmp}):
                self.assertEqual(paths.find_root(), Path(tmp).resolve())

    def test_nothing_above_a_stray_directory(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QUICKMUD_ROOT", None)
            with self.assertRaises(paths.RootNotFound):
                paths.find_root(Path(tmp))


if __name__ == "__main__":
    unittest.main()
