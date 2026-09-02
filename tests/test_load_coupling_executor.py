import tempfile
import unittest
from pathlib import Path

from engine.load_coupling_executor import runner_command


class LoadCouplingExecutorTests(unittest.TestCase):
    def test_unittest_path_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            command = runner_command(
                "python-unittest",
                "tests/test_report.py",
                worktree,
            )

            self.assertIn("-m", command)
            self.assertIn("unittest", command)
            self.assertIn("discover", command)
            self.assertIn("test_report.py", command)
            self.assertNotIn("tests.test_report", command)

    def test_pytest_path_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            command = runner_command(
                "pytest",
                "tests/test_report.py",
                worktree,
            )
            self.assertEqual(command[-1], "tests/test_report.py")

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
                runner_command("invented", "tests/test_x.py", worktree)
    
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
