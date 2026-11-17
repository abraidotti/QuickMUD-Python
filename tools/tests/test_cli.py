import contextlib
import io
import unittest
from unittest import mock

from charm_tools import cli


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as e:  # argparse exits for --help, --version and usage errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_version(self):
        code, out, _ = run(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("charm_tools 0.1.0", out)

    def test_no_command_is_a_usage_error(self):
        code, _, err = run([])
        self.assertEqual(code, 2)
        self.assertIn("command", err)

    def test_doctor_passes_its_exit_code_through(self):
        with mock.patch("charm_tools.doctor.main", return_value=1) as doctor_main:
            code, _, _ = run(["doctor", "--image", "charm:test"])
        self.assertEqual(code, 1)
        doctor_main.assert_called_once_with("charm:test")

    def test_sim_smoke_passes_its_arguments_through(self):
        with mock.patch("charm_tools.sim.smoke.main", return_value=0) as smoke_main:
            code, _, _ = run(["sim", "smoke", "--docker", "charm", "-v"])
        self.assertEqual(code, 0)
        self.assertEqual(smoke_main.call_args.args[0], ["--docker", "charm", "-v"])

    def test_sim_smoke_help(self):
        code, out, _ = run(["sim", "smoke", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("--docker", out)


if __name__ == "__main__":
    unittest.main()
