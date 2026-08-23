import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from engine.cycle_orchestrator import (
    execute_parallel_trials,
    finalize_cycle_result,
    run_cycle,
    validate_parallel_result_set,
)
from engine.sandbox_execution import MutationTrial


class CycleOrchestratorTests(unittest.TestCase):

    def trial(self, pass_number: int) -> MutationTrial:
        return MutationTrial(
            pass_number=pass_number,
            mutation_id=f"MUTATION-{pass_number}",
            identity_version="IDENTITY-1",
            proof_metadata_version="METADATA-1",
            sandbox_contract_version="SANDBOX-1",
            relative_path="app.py",
            line=pass_number,
            column=0,
            mutation_kind="TOKEN_REPLACEMENT",
            original_token="True",
            replacement_token="False",
            canonical_source_hash="source",
            sandbox_id=f"SANDBOX-{pass_number}",
            test_exit_code=0,
            survived=True,
            fracture_observed=False,
            restored=True,
            sandbox_removed=True,
            disposition="MUTATION_SURVIVED",
            test_evidence_path=f"workers/{pass_number}/process.json",
            proof_metadata_path=f"workers/{pass_number}/proof-metadata.json",
            detected_test_ids=(),
            invariant_refs=(),
            assertion_refs=(),
            behavioral_fragment_refs=(),
            execution_error="",
        )

    def test_parallel_executor_runs_concurrently_and_orders_results(self):
        barrier=threading.Barrier(2)
        owner=self

        class FakeExecutor:
            def execute_mutation(
                self,
                cycle_id,
                adapter,
                entry,
                pass_number,
                candidate,
            ):
                barrier.wait(timeout=2)
                return owner.trial(pass_number)

        result=execute_parallel_trials(
            FakeExecutor(),
            "CYCLE",
            "python",
            "tests",
            (object(),object()),
            2,
        )

        self.assertEqual(
            tuple(item.pass_number for item in result),
            (1,2),
        )

    def test_parallel_result_set_rejects_duplicate_and_unknown_passes(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "missing, duplicate, or unknown",
        ):
            validate_parallel_result_set(
                (object(), object()),
                (self.trial(1), self.trial(1)),
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "missing, duplicate, or unknown",
        ):
            validate_parallel_result_set(
                (object(), object()),
                (self.trial(1), self.trial(99)),
            )

    def test_parallel_future_exception_becomes_explicit_failed_trial(self):
        owner = self

        class FakeExecutor:
            def execute_mutation(
                self,
                cycle_id,
                adapter,
                entry,
                pass_number,
                candidate,
            ):
                if pass_number == 2:
                    raise RuntimeError("worker exploded")

                return owner.trial(pass_number)

            def record_worker_failure(
                self,
                cycle_id,
                pass_number,
                candidate,
                error,
            ):
                prior = owner.trial(pass_number)
                return MutationTrial(
                    **{
                        **prior.__dict__,
                        "survived": False,
                        "restored": False,
                        "disposition": "WORKER_FUTURE_FAILED",
                        "execution_error": str(error),
                    }
                )

        result = execute_parallel_trials(
            FakeExecutor(),
            "CYCLE",
            "python",
            "tests",
            (object(), object()),
            2,
        )

        self.assertEqual(
            tuple(item.pass_number for item in result),
            (1, 2),
        )
        self.assertFalse(result[1].survived)
        self.assertEqual(
            result[1].disposition,
            "WORKER_FUTURE_FAILED",
        )

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
            proof_bundle = json.loads(
                Path(result.proof_metadata_path).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                proof_bundle["schema"],
                "kiln.proof-metadata-aggregate.v1",
            )
            self.assertEqual(len(proof_bundle["trials"]), 1)
            trial_metadata = proof_bundle["trials"][0]["metadata"]
            self.assertTrue(trial_metadata["assertion_refs"])
            self.assertTrue(trial_metadata["fragment_contracts"])
            self.assertTrue(trial_metadata["fragment_proof_links"])
            self.assertNotIn(str(repo), json.dumps(proof_bundle))
            self.assertTrue(
                (
                    Path(result.evidence_path).parent
                    / result.trials[0].proof_metadata_path
                ).is_file()
            )

    def test_parallel_cycle_is_reproducible_and_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            first_sessions=root/"sessions-a"
            second_sessions=root/"sessions-b"
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
                "FLAGS = [True, True, True, True]\n",
                encoding="utf-8",
            )
            tests=repo/"tests"
            tests.mkdir()
            (tests/"test_app.py").write_text(
                "import unittest\n"
                "import app\n"
                "\n"
                "class AppTests(unittest.TestCase):\n"
                "    def test_flags(self):\n"
                "        self.assertTrue(all(app.FLAGS))\n",
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

            first=finalize_cycle_result(
                run_cycle(
                    str(repo),
                    "python",
                    "tests",
                    4,
                    "stable",
                    first_sessions,
                    workers=2,
                ),
                str(repo),
            )
            second=finalize_cycle_result(
                run_cycle(
                    str(repo),
                    "python",
                    "tests",
                    4,
                    "stable",
                    second_sessions,
                    workers=2,
                ),
                str(repo),
            )

            self.assertEqual(
                first.workers_used,
                2,
            )
            self.assertEqual(
                first.passes_executed,
                4,
            )
            self.assertEqual(
                tuple(item.pass_number for item in first.trials),
                (1,2,3,4),
            )
            self.assertEqual(
                len({item.sandbox_id for item in first.trials}),
                4,
            )
            self.assertTrue(
                all(item.sandbox_removed for item in first.trials)
            )
            self.assertEqual(
                Path(first.evidence_path).read_bytes(),
                Path(second.evidence_path).read_bytes(),
            )
            self.assertEqual(
                Path(first.proof_metadata_path).read_bytes(),
                Path(second.proof_metadata_path).read_bytes(),
            )
            self.assertTrue(
                first.original_head_preserved
            )
            self.assertTrue(
                second.original_head_preserved
            )

    def test_parallel_cycle_rejects_nondeterministic_early_stop(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "require --until stable",
        ):
            run_cycle(
                ".",
                "python",
                "tests",
                2,
                "fracture",
                Path("sessions"),
                workers=2,
            )


if __name__ == "__main__":
    unittest.main()
