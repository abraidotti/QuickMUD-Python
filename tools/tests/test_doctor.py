import contextlib
import io
import subprocess
import unittest
from unittest import mock

from quickmud_tools import doctor


def completed(stdout="", code=0):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr="")


class DoctorTest(unittest.TestCase):
    def test_checkout_is_found_with_its_areas(self):
        checks = {c.name: c for c in doctor.check_checkout()}
        self.assertTrue(checks["checkout"].ok)
        self.assertTrue(checks["areas"].ok)
        self.assertTrue(checks["game"].ok)
        self.assertRegex(checks["areas"].detail, r"^\d+ area files")

    def test_no_docker_on_path(self):
        with mock.patch("shutil.which", return_value=None):
            [check] = doctor.check_docker()
        self.assertFalse(check.ok)
        self.assertIn("PATH", check.detail)

    def test_daemon_not_answering(self):
        with mock.patch("shutil.which", return_value="docker"), \
             mock.patch.object(doctor, "_run", return_value=completed(code=1)):
            [check] = doctor.check_docker()
        self.assertFalse(check.ok)
        self.assertIn("daemon", check.detail)

    def test_missing_image(self):
        results = [completed("29.9.3\n"), completed(code=1)]
        with mock.patch("shutil.which", return_value="docker"), \
             mock.patch.object(doctor, "_run", side_effect=results):
            docker, image = doctor.check_docker("quickmud")
        self.assertTrue(docker.ok)
        self.assertFalse(image.ok)
        self.assertIn("docker build -t quickmud .", image.detail)

    def test_exit_code_is_1_when_anything_fails(self):
        checks = [doctor.Check("a", True, ""), doctor.Check("b", False, "why")]
        with mock.patch.object(doctor, "run", return_value=checks), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(doctor.main(), 1)
        self.assertIn("FAIL  b  why", out.getvalue())

    def test_exit_code_is_0_when_all_ok(self):
        with mock.patch.object(doctor, "run", return_value=[doctor.Check("a", True, "")]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(), 0)


if __name__ == "__main__":
    unittest.main()
