import unittest

from engine.load_coupling_executor import runner_command


class LoadCouplingExecutorTests(unittest.TestCase):
    def test_unittest_path_resolution(self):
        command = runner_command(
            "python-unittest",
            "tests/test_report.py",
        )

        self.assertIn("-m", command)
        self.assertIn("unittest", command)
        self.assertIn("discover", command)
        self.assertIn("test_report.py", command)
        self.assertNotIn("tests.test_report", command)

    def test_pytest_path_resolution(self):
        command = runner_command(
            "pytest",
            "tests/test_report.py",
        )
        self.assertEqual(command[-1], "tests/test_report.py")

    def test_pytest_compatible_resolves_to_pytest(self):
        command = runner_command(
            "pytest-compatible",
            "tests/test_manifest.py",
        )

        self.assertEqual(
            command[-2:],
            ["pytest", "tests/test_manifest.py"],
        )
    def test_unknown_runner_fails_closed(self):
        with self.assertRaises(RuntimeError):
            runner_command("invented", "tests/test_x.py")


if __name__ == "__main__":
    unittest.main()
