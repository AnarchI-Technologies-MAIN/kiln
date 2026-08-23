import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from engine.cycle_orchestrator import (
    run_cycle,
    validate_trial_evidence,
)
from engine.mutation_adapters import discover_mutations
from engine.sandbox_execution import (
    SandboxExecutor,
    test_process_outcome,
)


class SandboxExecutionTests(unittest.TestCase):

    def fixture(self, root: Path):
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(repo)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "config",
                "user.email",
                "kiln@example.invalid",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "config",
                "user.name",
                "Kiln Test",
            ],
            check=True,
        )
        (repo / "app.py").write_text(
            "FLAG = True\n",
            encoding="utf-8",
        )
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_app.py").write_text(
            "import unittest\n"
            "import app\n"
            "\n"
            "class AppTests(unittest.TestCase):\n"
            "    def test_flag(self):\n"
            "        self.assertTrue(app.FLAG)\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "commit",
                "-q",
                "-m",
                "baseline",
            ],
            check=True,
        )
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        cycle_root = root / "sessions" / "CYCLE"
        executor = SandboxExecutor(
            repo,
            commit,
            cycle_root,
        )
        candidate = discover_mutations(
            "python",
            repo,
        )[0]
        return repo, cycle_root, executor, candidate

    def completed(self, returncode: int):
        return subprocess.CompletedProcess(
            args=["tests"],
            returncode=returncode,
            stdout="stdout",
            stderr="stderr",
        )

    def test_process_outcomes_are_fail_closed(self):
        self.assertEqual(test_process_outcome(0), "SURVIVED")
        self.assertEqual(test_process_outcome(1), "FRACTURE")

        for code in (2, -9, -1073741819):
            self.assertEqual(
                test_process_outcome(code),
                "EXECUTION_FAILED",
            )

    def test_abnormal_exit_is_not_fracture_or_survival(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)

            with patch(
                "engine.sandbox_execution.run_adapter_tests",
                return_value=self.completed(-1073741819),
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            self.assertFalse(trial.survived)
            self.assertFalse(trial.fracture_observed)
            self.assertTrue(trial.restored)
            self.assertTrue(trial.sandbox_removed)
            self.assertEqual(
                trial.disposition,
                "TEST_PROCESS_FAILED",
            )
            self.assertTrue(trial.execution_error)

    def test_timeout_restores_and_removes_sandbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)

            with patch(
                "engine.sandbox_execution.run_adapter_tests",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["tests"],
                    timeout=0.01,
                ),
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            self.assertEqual(trial.disposition, "TEST_TIMEOUT")
            self.assertFalse(trial.survived)
            self.assertFalse(trial.fracture_observed)
            self.assertTrue(trial.restored)
            self.assertTrue(trial.sandbox_removed)
            self.assertTrue(
                Path(executor.cycle_root / trial.test_evidence_path).is_file()
            )

    def test_process_evidence_write_failure_is_explicit_and_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)

            with patch(
                "engine.sandbox_execution.run_adapter_tests",
                return_value=self.completed(0),
            ), patch.object(
                executor,
                "write_process_evidence",
                side_effect=OSError("evidence device failed"),
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            self.assertEqual(
                trial.disposition,
                "SANDBOX_EXECUTION_FAILED",
            )
            self.assertFalse(trial.survived)
            self.assertFalse(trial.fracture_observed)
            self.assertTrue(trial.restored)
            self.assertTrue(trial.sandbox_removed)
            self.assertIn(
                "evidence device failed",
                trial.execution_error,
            )

    def test_keyboard_interrupt_after_apply_is_recorded_and_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)
            from engine.sandbox_execution import apply_mutation

            def interrupt_after_apply(specimen, selected):
                apply_mutation(specimen, selected)
                raise KeyboardInterrupt("hostile interrupt")

            with patch(
                "engine.sandbox_execution.apply_mutation",
                side_effect=interrupt_after_apply,
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            self.assertEqual(
                trial.disposition,
                "SANDBOX_INTERRUPTED",
            )
            self.assertFalse(trial.survived)
            self.assertFalse(trial.fracture_observed)
            self.assertTrue(trial.restored)
            self.assertTrue(trial.sandbox_removed)
            worker_root = (
                executor.workers_root
                / trial.sandbox_id
            )
            self.assertTrue((worker_root / "trial.json").is_file())
            state = json.loads(
                (worker_root / "worker-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["state"], "COMPLETED")

    def test_cleanup_failure_cannot_report_survival(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)

            with patch(
                "engine.sandbox_execution.run_adapter_tests",
                return_value=self.completed(0),
            ), patch.object(
                executor,
                "release",
                return_value=False,
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            self.assertEqual(
                trial.disposition,
                "SANDBOX_CLEANUP_FAILED",
            )
            self.assertFalse(trial.survived)
            self.assertFalse(trial.fracture_observed)
            self.assertFalse(trial.sandbox_removed)
            lease_root = (
                executor.sandboxes_root
                / trial.sandbox_id
            )
            lease = next(
                item
                for item in lease_root.iterdir()
                if item.name == "repository"
            )
            from engine.sandbox_execution import SandboxLease
            self.assertTrue(
                executor.release(
                    SandboxLease(
                        sandbox_id=trial.sandbox_id,
                        cycle_id="CYCLE",
                        pass_number=1,
                        mutation_id=candidate.mutation_id,
                        root=lease_root,
                        repository=lease,
                        evidence_root=(
                            executor.workers_root
                            / trial.sandbox_id
                        ),
                    )
                )
            )

    def test_release_is_idempotent_and_restart_recovers_abandoned_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, cycle_root, executor, candidate = self.fixture(root)
            lease = executor.materialize(
                "CYCLE",
                1,
                candidate.mutation_id,
            )
            executor.write_cycle_state(
                "CYCLE",
                "TRIALS_RUNNING",
            )

            restarted = SandboxExecutor(
                repo,
                executor.source_commit,
                cycle_root,
            )

            self.assertFalse(lease.root.exists())
            self.assertTrue(
                (
                    restarted.recovery_root
                    / f"{lease.sandbox_id}.json"
                ).is_file()
            )
            replay = json.loads(
                (
                    restarted.recovery_root
                    / "cycle-state.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                replay["disposition"],
                "FULL_REPLAY_REQUIRED",
            )
            self.assertTrue(restarted.release(lease))
            self.assertTrue(restarted.release(lease))

    def test_release_recovers_when_worktree_remove_command_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, executor, candidate = self.fixture(root)
            lease = executor.materialize(
                "CYCLE",
                1,
                candidate.mutation_id,
            )
            from engine.sandbox_execution import git as real_git
            removal_attempts = []

            def fail_remove(repo, *args):
                if args[:2] == ("worktree", "remove"):
                    removal_attempts.append(args)
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=1,
                        stdout="",
                        stderr="injected remove failure",
                    )

                return real_git(repo, *args)

            with patch(
                "engine.sandbox_execution.git",
                side_effect=fail_remove,
            ):
                removed = executor.release(lease)

            self.assertTrue(removed)
            self.assertEqual(len(removal_attempts), 2)
            self.assertFalse(lease.root.exists())
            self.assertNotIn(
                lease.repository.resolve(),
                executor.registered_worktree_paths(),
            )

    def test_evidence_validation_rejects_missing_and_malformed_documents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, cycle_root, executor, candidate = self.fixture(root)

            with patch(
                "engine.sandbox_execution.run_adapter_tests",
                return_value=self.completed(0),
            ):
                trial = executor.execute_mutation(
                    "CYCLE",
                    "python",
                    "tests",
                    1,
                    candidate,
                )

            validate_trial_evidence(
                cycle_root,
                "CYCLE",
                (candidate,),
                (trial,),
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "mutation identity does not match",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (
                        replace(
                            trial,
                            mutation_id="UNKNOWN-MUTATION",
                        ),
                    ),
                )

            primary = cycle_root / trial.test_evidence_path
            original = primary.read_text(encoding="utf-8")
            primary.unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "evidence reference is missing",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (trial,),
                )

            primary.write_text("not-json\n", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError,
                "process evidence is malformed",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (trial,),
                )

            primary.write_text(original, encoding="utf-8")
            metadata_path = cycle_root / trial.proof_metadata_path
            metadata_original = metadata_path.read_text(
                encoding="utf-8"
            )
            metadata_path.unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "evidence reference is missing",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (trial,),
                )

            metadata_path.write_text(
                "not-json\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "proof metadata evidence is malformed",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (trial,),
                )

            metadata_path.write_text(
                metadata_original,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "must be relative",
            ):
                validate_trial_evidence(
                    cycle_root,
                    "CYCLE",
                    (candidate,),
                    (
                        replace(
                            trial,
                            proof_metadata_path=str(metadata_path),
                        ),
                    ),
                )

    def test_cycle_rejects_missing_worker_evidence_as_aggregate_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, _, _, _ = self.fixture(root)
            original_write = SandboxExecutor.write_process_evidence

            def omit_mutation_process_evidence(executor, lease, result):
                relative_path = original_write(
                    executor,
                    lease,
                    result,
                )

                if lease.pass_number > 0:
                    (
                        executor.cycle_root
                        / relative_path
                    ).unlink()

                return relative_path

            with patch.object(
                SandboxExecutor,
                "write_process_evidence",
                new=omit_mutation_process_evidence,
            ):
                result = run_cycle(
                    str(repo),
                    "python",
                    "tests",
                    1,
                    "stable",
                    root / "aggregate-sessions",
                )

            self.assertEqual(
                result.disposition,
                "AGGREGATE_VALIDATION_FAILED",
            )
            self.assertEqual(result.execution_failures, 1)
            self.assertEqual(result.passes_executed, 0)
            self.assertFalse(result.specimen_removed)
            cycle_root = (
                root
                / "aggregate-sessions"
                / result.cycle_id
            )
            self.assertTrue(
                (cycle_root / "aggregate-error.json").is_file()
            )
            state = json.loads(
                (cycle_root / "cycle-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                state["state"],
                "AGGREGATE_VALIDATION_FAILED",
            )


if __name__ == "__main__":
    unittest.main()
