import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.cli_workflows import (
    inspect_candidates,
    inspect_surfaces,
    preflight_target,
    prove_target,
    run_target_baseline,
)


class CliWorkflowTests(unittest.TestCase):

    def build_repo(self, root: Path) -> Path:
        repo=root/"repo"
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

        return repo

    def test_preflight_proves_clean_git_target(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=self.build_repo(
                Path(temp)
            )

            result=preflight_target(
                str(repo),
                "python",
                "tests",
            )

            self.assertEqual(
                result.disposition,
                "READY_FOR_KILN_PROOF",
            )

            self.assertGreater(
                result.mutation_candidate_count,
                0,
            )

    def test_baseline_isolated_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=self.build_repo(
                Path(temp)
            )

            result=run_target_baseline(
                str(repo),
                "python",
                "tests",
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.specimen_removed
            )

            self.assertTrue(
                result.original_head_preserved
            )

    def test_candidate_and_surface_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=self.build_repo(
                Path(temp)
            )

            candidates=inspect_candidates(
                str(repo),
                "python",
            )

            surfaces=inspect_surfaces(
                str(repo),
                "python",
            )

            self.assertGreater(
                candidates.candidate_count,
                0,
            )

            self.assertEqual(
                candidates.candidate_count,
                surfaces.candidate_count,
            )

    def test_prove_never_executes_destructive_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=self.build_repo(
                Path(temp)
            )

            result=prove_target(
                str(repo),
                "python",
                "tests",
            )

            self.assertEqual(
                result.disposition,
                "TARGET_PROVEN_FOR_BOUNDED_CYCLE",
            )

            self.assertFalse(
                result.destructive_execution_performed
            )

            self.assertTrue(
                result.original_head_preserved
            )


if __name__ == "__main__":
    unittest.main()
