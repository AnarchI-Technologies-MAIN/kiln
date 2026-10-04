import tempfile
import unittest
from pathlib import Path

from engine.load_pressure_executor import LOAD_LEVELS, runner_command


class LoadPressureExecutorTests(unittest.TestCase):
    def test_load_ladder_is_exact(self):
        self.assertEqual(
            LOAD_LEVELS,
            {"1x": 1, "2x": 2, "4x": 4, "8x": 8, "16x": 16},
        )

    def test_unittest_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            command = runner_command("python-unittest", "tests/test_report.py", worktree)
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

    def test_pytest_compatible_resolves_to_pytest(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            command = runner_command(
                "pytest-compatible",
                "tests/test_manifest.py",
                worktree,
            )

            self.assertEqual(
                command[-2:],
                ["pytest", "tests/test_manifest.py"],
            )
    
    def test_unknown_runner_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            with self.assertRaises(RuntimeError):
                runner_command("unknown", "tests/test_report.py", worktree)
    
    def test_absolute_path_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            with self.assertRaises(RuntimeError) as ctx:
                runner_command("pytest", "/etc/passwd", worktree)
            self.assertIn("absolute", str(ctx.exception).lower())
    
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            with self.assertRaises(RuntimeError) as ctx:
                runner_command("pytest", "../../outside/malicious.py", worktree)
            self.assertIn("escapes", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
