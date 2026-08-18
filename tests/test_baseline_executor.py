import unittest

from engine.baseline_executor import runner_command


class BaselineExecutorTests(unittest.TestCase):
    def test_unittest_file_target_uses_discovery(self):
        command = runner_command(
            "python-unittest",
            r"tests\test_report.py",
        )

        self.assertEqual(
            command[-6:],
            [
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_report.py",
            ],
        )

    def test_unittest_target_does_not_require_tests_package(self):
        command = runner_command(
            "python-unittest",
            "tests/test_report.py",
        )

        self.assertNotIn("tests.test_report", command)
        self.assertIn("test_report.py", command)

    def test_pytest_runner_preserves_path(self):
        command = runner_command(
            "pytest",
            "tests/test_report.py",
        )

        self.assertEqual(
            command[-2:],
            ["pytest", "tests/test_report.py"],
        )

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
            runner_command(
                "invented-runner",
                "tests/test_x.py",
            )


if __name__ == "__main__":
    unittest.main()
