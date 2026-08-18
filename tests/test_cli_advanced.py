import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.cli_advanced import (
    contract_summary,
    evidence_summary,
    fragment_summary,
    graph_edges_from_evidence,
    materialize_graph,
    targeted_inject,
)
from engine.cli_workflows import inspect_candidates


class AdvancedCliTests(unittest.TestCase):

    def build_repo(self, root: Path):
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

    def test_targeted_inject_persists_cycle_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=self.build_repo(root)
            sessions=root/"sessions"

            inventory=inspect_candidates(
                str(repo),
                "python",
            )

            result=targeted_inject(
                str(repo),
                "python",
                "tests",
                inventory.candidate_ids[0],
                sessions,
            )

            self.assertTrue(
                result.original_head_preserved
            )

            self.assertEqual(
                result.passes_executed,
                1,
            )

            summary=evidence_summary(
                str(repo),
                sessions,
            )

            self.assertEqual(
                summary.cycle_count,
                1,
            )

            self.assertEqual(
                summary.trial_count,
                1,
            )

    def test_graph_materializes_from_cycle_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=self.build_repo(root)
            sessions=root/"sessions"

            inventory=inspect_candidates(
                str(repo),
                "python",
            )

            targeted_inject(
                str(repo),
                "python",
                "tests",
                inventory.candidate_ids[0],
                sessions,
            )

            edges=graph_edges_from_evidence(
                str(repo),
                sessions,
            )

            self.assertEqual(
                len(edges),
                1,
            )

            summary=materialize_graph(
                str(repo),
                sessions,
            )

            self.assertEqual(
                summary.edge_count,
                1,
            )

            self.assertTrue(
                Path(
                    summary.graph_path
                ).exists()
            )

    def test_fragment_command_uses_real_behavioral_fragment_core(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=self.build_repo(root)

            summary=fragment_summary(
                str(repo),
                "tests/test_app.py",
            )

            self.assertGreater(
                summary.fragment_count,
                0,
            )

    def test_contract_uses_observed_cycle_graph(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=self.build_repo(root)
            sessions=root/"sessions"

            inventory=inspect_candidates(
                str(repo),
                "python",
            )

            targeted_inject(
                str(repo),
                "python",
                "tests",
                inventory.candidate_ids[0],
                sessions,
            )

            summary=contract_summary(
                str(repo),
                sessions,
                "detect mutation fracture",
                "mutation",
                "",
                "",
            )

            self.assertEqual(
                summary.disposition,
                "SYNTHETIC_CONTRACT_READY",
            )

            self.assertFalse(
                summary.contract.execution_authorized
            )


if __name__ == "__main__":
    unittest.main()
