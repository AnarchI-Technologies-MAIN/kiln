import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.cycle_orchestrator import (
    finalize_cycle_result,
    run_cycle,
)


class CycleOrchestratorTests(unittest.TestCase):

    def test_cycle_mutates_disposable_worktree_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            sessions=root/"sessions"

            repo.mkdir()

            subprocess.run(
                ["git","init","-q",str(repo)],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"config","user.email","kiln@example.invalid"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"config","user.name","Kiln Test"],
                check=True,
            )

            (repo/"app.py").write_text(
                "FLAG = True\n"
                "\n"
                "def enabled():\n"
                "    return FLAG\n",
                encoding="utf-8",
            )

            tests=repo/"tests"
            tests.mkdir()

            (tests/"test_app.py").write_text(
                "import unittest\n"
                "import app\n"
                "\n"
                "class AppTests(unittest.TestCase):\n"
                "    def test_enabled(self):\n"
                "        self.assertTrue(app.enabled())\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["git","-C",str(repo),"add","."],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"commit","-q","-m","baseline"],
                check=True,
            )

            before=subprocess.check_output(
                ["git","-C",str(repo),"rev-parse","HEAD"],
                text=True,
            ).strip()

            raw=run_cycle(
                str(repo),
                "python",
                "tests",
                1,
                "fracture",
                sessions,
            )

            result=finalize_cycle_result(
                raw,
                str(repo),
            )

            after=subprocess.check_output(
                ["git","-C",str(repo),"rev-parse","HEAD"],
                text=True,
            ).strip()

            self.assertTrue(
                result.baseline_passed
            )

            self.assertEqual(
                result.passes_executed,
                1,
            )

            self.assertEqual(
                result.fractures_observed,
                1,
            )

            self.assertTrue(
                result.specimen_removed
            )

            self.assertTrue(
                result.original_head_preserved
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                subprocess.check_output(
                    ["git","-C",str(repo),"status","--porcelain"],
                    text=True,
                ).strip(),
                "",
            )


if __name__ == "__main__":
    unittest.main()
