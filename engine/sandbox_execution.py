from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Tuple
import json
import shutil
import subprocess

from engine.mutation_adapters import (
    discover_mutations,
    run_adapter_tests,
)
from engine.mutation_executor import (
    MutationCandidate,
    apply_mutation,
)
from engine.proof_metadata import (
    PROOF_METADATA_VERSION,
    build_proof_metadata,
    proof_metadata_payload,
)


PROOF_EVIDENCE_VERSION = "KILN-PROOF-EVIDENCE-3"
SANDBOX_CONTRACT_VERSION = "KILN-SANDBOX-2"
_WORKTREE_LOCK = Lock()


@dataclass(frozen=True)
class SandboxLease:
    sandbox_id: str
    cycle_id: str
    pass_number: int
    mutation_id: str
    root: Path
    repository: Path
    evidence_root: Path


@dataclass(frozen=True)
class BaselineSandboxResult:
    sandbox_id: str
    passed: bool
    exit_code: int
    sandbox_removed: bool
    evidence_path: str
    execution_error: str


@dataclass(frozen=True)
class MutationTrial:
    pass_number: int
    mutation_id: str
    identity_version: str
    proof_metadata_version: str
    sandbox_contract_version: str
    relative_path: str
    line: int
    column: int
    mutation_kind: str
    original_token: str
    replacement_token: str
    canonical_source_hash: str
    sandbox_id: str
    test_exit_code: int
    survived: bool
    fracture_observed: bool
    restored: bool
    sandbox_removed: bool
    disposition: str
    test_evidence_path: str
    proof_metadata_path: str
    detected_test_ids: Tuple[str, ...]
    invariant_refs: Tuple[str, ...]
    assertion_refs: Tuple[str, ...]
    behavioral_fragment_refs: Tuple[str, ...]
    execution_error: str


def git(
    repo: Path,
    *args: str,
):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def sandbox_identity(
    cycle_id: str,
    pass_number: int,
    mutation_id: str,
) -> str:
    material = "\0".join((
        SANDBOX_CONTRACT_VERSION,
        cycle_id,
        str(pass_number),
        mutation_id,
    ))

    return (
        "KILN-SANDBOX-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def normalize_error(
    error: BaseException,
    repository: Path | None = None,
) -> str:
    value = (
        f"{type(error).__name__}: {error}"
    )

    if repository is not None:
        value = value.replace(
            str(repository),
            "<sandbox>",
        )

    return " ".join(
        value.split()
    )


def test_process_outcome(
    returncode: int,
) -> str:
    """Classify only known test failure as fracture; everything else fails closed."""
    if returncode == 0:
        return "SURVIVED"

    if returncode == 1:
        return "FRACTURE"

    return "EXECUTION_FAILED"


class SandboxExecutor:

    def __init__(
        self,
        source_root: Path,
        source_commit: str,
        cycle_root: Path,
    ) -> None:
        self.source_root = Path(
            source_root
        ).resolve()
        self.source_commit = source_commit
        self.cycle_root = Path(
            cycle_root
        ).resolve()
        self.sandboxes_root = (
            self.cycle_root
            / "sandboxes"
        )
        self.workers_root = (
            self.cycle_root
            / "workers"
        )

        self.sandboxes_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.workers_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.recovery_root = (
            self.cycle_root
            / "recovery"
        )
        self.recover_abandoned_sandboxes()

    def registered_worktree_paths(
        self,
    ) -> Tuple[Path, ...]:
        result = git(
            self.source_root,
            "worktree",
            "list",
            "--porcelain",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "unable to enumerate registered worktrees"
            )

        paths = []

        for line in result.stdout.splitlines():
            if not line.startswith(
                "worktree "
            ):
                continue

            paths.append(
                Path(
                    line.removeprefix(
                        "worktree "
                    )
                ).resolve()
            )

        return tuple(paths)

    def worktree_registered(
        self,
        repository: Path,
    ) -> bool:
        expected = Path(
            repository
        ).resolve()

        return expected in self.registered_worktree_paths()

    def write_worker_state(
        self,
        sandbox_id: str,
        cycle_id: str,
        pass_number: int,
        mutation_id: str,
        state: str,
    ) -> str:
        evidence_root = (
            self.workers_root
            / sandbox_id
        )
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        path = evidence_root / "worker-state.json"
        path.write_text(
            json.dumps(
                {
                    "cycle_id": cycle_id,
                    "mutation_id": mutation_id,
                    "pass_number": pass_number,
                    "sandbox_id": sandbox_id,
                    "state": state,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return self.evidence_relative_path(
            path
        )

    def write_cycle_state(
        self,
        cycle_id: str,
        state: str,
        execution_error: str = "",
    ) -> None:
        path = self.cycle_root / "cycle-state.json"
        path.write_text(
            json.dumps(
                {
                    "cycle_id": cycle_id,
                    "execution_error": execution_error,
                    "state": state,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def recover_abandoned_sandboxes(
        self,
    ) -> None:
        cycle_state_path = (
            self.cycle_root
            / "cycle-state.json"
        )
        interrupted_cycle = None

        if cycle_state_path.is_file():
            try:
                interrupted_cycle = json.loads(
                    cycle_state_path.read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, ValueError):
                interrupted_cycle = {
                    "state": "MALFORMED"
                }

        abandoned = tuple(
            sorted(
                path
                for path in self.sandboxes_root.iterdir()
                if path.is_dir()
            )
        )

        if (
            interrupted_cycle
            and interrupted_cycle.get("state")
            != "COMPLETE"
        ):
            self.recovery_root.mkdir(
                parents=True,
                exist_ok=True,
            )
            (
                self.recovery_root
                / "cycle-state.json"
            ).write_text(
                json.dumps(
                    {
                        "disposition": "FULL_REPLAY_REQUIRED",
                        "prior_cycle_state": interrupted_cycle,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        if not abandoned:
            return

        self.recovery_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        for root in abandoned:
            sandbox_id = root.name
            lease = SandboxLease(
                sandbox_id=sandbox_id,
                cycle_id="",
                pass_number=-1,
                mutation_id="",
                root=root,
                repository=root / "repository",
                evidence_root=(
                    self.workers_root
                    / sandbox_id
                ),
            )
            removed = self.release(
                lease
            )
            recovery_path = (
                self.recovery_root
                / f"{sandbox_id}.json"
            )
            recovery_path.write_text(
                json.dumps(
                    {
                        "disposition": (
                            "ABANDONED_SANDBOX_RECOVERED"
                            if removed
                            else "ABANDONED_SANDBOX_RECOVERY_FAILED"
                        ),
                        "sandbox_id": sandbox_id,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            if not removed:
                raise RuntimeError(
                    "unable to recover abandoned sandbox: "
                    + sandbox_id
                )

    def _validated_sandbox_root(
        self,
        sandbox_id: str,
    ) -> Path:
        root = (
            self.sandboxes_root
            / sandbox_id
        ).resolve()

        try:
            root.relative_to(
                self.sandboxes_root
            )
        except ValueError:
            raise RuntimeError(
                "sandbox path escaped cycle boundary"
            )

        return root

    def materialize(
        self,
        cycle_id: str,
        pass_number: int,
        mutation_id: str,
    ) -> SandboxLease:
        sandbox_id = sandbox_identity(
            cycle_id,
            pass_number,
            mutation_id,
        )
        root = self._validated_sandbox_root(
            sandbox_id
        )

        if root.exists():
            raise RuntimeError(
                f"stale sandbox blocks execution: {sandbox_id}"
            )

        root.mkdir(
            parents=True,
            exist_ok=False,
        )
        repository = root / "repository"
        evidence_root = (
            self.workers_root
            / sandbox_id
        )
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        with _WORKTREE_LOCK:
            added = git(
                self.source_root,
                "worktree",
                "add",
                "--detach",
                str(repository),
                self.source_commit,
            )

        if added.returncode != 0:
            shutil.rmtree(
                root,
                ignore_errors=True,
            )
            raise RuntimeError(
                "unable to materialize destructive sandbox: "
                + added.stderr.strip()
            )

        return SandboxLease(
            sandbox_id=sandbox_id,
            cycle_id=cycle_id,
            pass_number=pass_number,
            mutation_id=mutation_id,
            root=root,
            repository=repository,
            evidence_root=evidence_root,
        )

    def release(
        self,
        lease: SandboxLease,
    ) -> bool:
        root = self._validated_sandbox_root(
            lease.sandbox_id
        )

        try:
            with _WORKTREE_LOCK:
                if self.worktree_registered(
                    lease.repository
                ):
                    for _ in range(2):
                        removed = git(
                            self.source_root,
                            "worktree",
                            "remove",
                            "--force",
                            str(lease.repository),
                        )

                        if removed.returncode == 0:
                            break
        except Exception:
            return False

        shutil.rmtree(
            root,
            ignore_errors=True,
        )

        try:
            with _WORKTREE_LOCK:
                pruned = git(
                    self.source_root,
                    "worktree",
                    "prune",
                )

                if pruned.returncode != 0:
                    return False

                registered = self.worktree_registered(
                    lease.repository
                )
        except Exception:
            return False

        return not root.exists() and not registered

    def evidence_relative_path(
        self,
        path: Path,
    ) -> str:
        return Path(path).resolve().relative_to(
            self.cycle_root
        ).as_posix()

    def write_process_evidence(
        self,
        lease: SandboxLease,
        result: subprocess.CompletedProcess,
    ) -> str:
        stdout_path = (
            lease.evidence_root
            / "test.stdout.txt"
        )
        stderr_path = (
            lease.evidence_root
            / "test.stderr.txt"
        )
        process_path = (
            lease.evidence_root
            / "process.json"
        )

        stdout_path.write_text(
            result.stdout or "",
            encoding="utf-8",
        )
        stderr_path.write_text(
            result.stderr or "",
            encoding="utf-8",
        )
        process_path.write_text(
            json.dumps(
                {
                    "args": str(result.args),
                    "returncode": result.returncode,
                    "stderr_path": "test.stderr.txt",
                    "stdout_path": "test.stdout.txt",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return self.evidence_relative_path(
            process_path
        )

    def write_execution_error(
        self,
        lease: SandboxLease,
        message: str,
    ) -> str:
        path = (
            lease.evidence_root
            / "execution-error.txt"
        )
        path.write_text(
            message + "\n",
            encoding="utf-8",
        )

        return self.evidence_relative_path(
            path
        )

    def write_unleased_error(
        self,
        sandbox_id: str,
        message: str,
    ) -> str:
        evidence_root = (
            self.workers_root
            / sandbox_id
        )
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        path = (
            evidence_root
            / "execution-error.txt"
        )
        path.write_text(
            message + "\n",
            encoding="utf-8",
        )

        return self.evidence_relative_path(
            path
        )

    def write_proof_metadata_evidence(
        self,
        sandbox_id: str,
        metadata,
    ) -> str:
        evidence_root = (
            self.workers_root
            / sandbox_id
        )
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        path = evidence_root / "proof-metadata.json"
        path.write_text(
            json.dumps(
                proof_metadata_payload(metadata),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return self.evidence_relative_path(path)

    def write_trial_evidence(
        self,
        lease: SandboxLease,
        trial: MutationTrial,
    ) -> None:
        path = (
            lease.evidence_root
            / "trial.json"
        )
        path.write_text(
            json.dumps(
                asdict(trial),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_unleased_trial_evidence(
        self,
        sandbox_id: str,
        trial: MutationTrial,
    ) -> None:
        evidence_root = (
            self.workers_root
            / sandbox_id
        )
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        path = evidence_root / "trial.json"
        path.write_text(
            json.dumps(
                asdict(trial),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def execute_baseline(
        self,
        cycle_id: str,
        adapter: str,
        entry: str,
    ) -> BaselineSandboxResult:
        sandbox_id = sandbox_identity(
            cycle_id,
            0,
            "BASELINE",
        )

        try:
            lease = self.materialize(
                cycle_id,
                0,
                "BASELINE",
            )
        except Exception as error:
            execution_error = normalize_error(
                error
            )
            evidence_path = self.write_unleased_error(
                sandbox_id,
                execution_error,
            )
            self.write_worker_state(
                sandbox_id,
                cycle_id,
                0,
                "BASELINE",
                "COMPLETED",
            )

            return BaselineSandboxResult(
                sandbox_id=sandbox_id,
                passed=False,
                exit_code=-1,
                sandbox_removed=not self._validated_sandbox_root(
                    sandbox_id
                ).exists(),
                evidence_path=evidence_path,
                execution_error=execution_error,
            )
        passed = False
        exit_code = -1
        evidence_path = ""
        execution_error = ""

        try:
            self.write_worker_state(
                lease.sandbox_id,
                cycle_id,
                0,
                "BASELINE",
                "TEST_RUNNING",
            )
            result = run_adapter_tests(
                adapter,
                lease.repository,
                entry,
            )
            exit_code = result.returncode
            evidence_path = self.write_process_evidence(
                lease,
                result,
            )
            outcome = test_process_outcome(
                result.returncode
            )
            passed = outcome == "SURVIVED"

            if outcome == "EXECUTION_FAILED":
                execution_error = (
                    "unexpected baseline test process exit code: "
                    + str(result.returncode)
                )
        except BaseException as error:
            execution_error = normalize_error(
                error,
                lease.repository,
            )
            evidence_path = self.write_execution_error(
                lease,
                execution_error,
            )
        finally:
            sandbox_removed = self.release(
                lease
            )

        if not sandbox_removed:
            passed = False
            execution_error = (
                execution_error + "; "
                if execution_error
                else ""
            ) + "sandbox cleanup failed"

        self.write_worker_state(
            lease.sandbox_id,
            cycle_id,
            0,
            "BASELINE",
            (
                "COMPLETED"
                if sandbox_removed
                else "CLEANUP_FAILED"
            ),
        )

        return BaselineSandboxResult(
            sandbox_id=lease.sandbox_id,
            passed=passed,
            exit_code=exit_code,
            sandbox_removed=sandbox_removed,
            evidence_path=evidence_path,
            execution_error=execution_error,
        )

    def execute_mutation(
        self,
        cycle_id: str,
        adapter: str,
        entry: str,
        pass_number: int,
        advertised: MutationCandidate,
    ) -> MutationTrial:
        sandbox_id = sandbox_identity(
            cycle_id,
            pass_number,
            advertised.mutation_id,
        )

        try:
            lease = self.materialize(
                cycle_id,
                pass_number,
                advertised.mutation_id,
            )
        except Exception as error:
            execution_error = normalize_error(
                error
            )
            evidence_path = self.write_unleased_error(
                sandbox_id,
                execution_error,
            )
            metadata = build_proof_metadata(
                self.source_root,
                adapter,
                "",
                "",
                advertised.mutation_id,
                entry,
            )
            proof_metadata_path = self.write_proof_metadata_evidence(
                sandbox_id,
                metadata,
            )
            trial = MutationTrial(
                pass_number=pass_number,
                mutation_id=advertised.mutation_id,
                identity_version=advertised.identity_version,
                proof_metadata_version=PROOF_METADATA_VERSION,
                sandbox_contract_version=SANDBOX_CONTRACT_VERSION,
                relative_path=advertised.relative_path,
                line=advertised.line,
                column=advertised.column,
                mutation_kind=advertised.kind,
                original_token=advertised.original_token,
                replacement_token=advertised.replacement_token,
                canonical_source_hash=advertised.canonical_source_hash,
                sandbox_id=sandbox_id,
                test_exit_code=-1,
                survived=False,
                fracture_observed=False,
                restored=False,
                sandbox_removed=not self._validated_sandbox_root(
                    sandbox_id
                ).exists(),
                disposition="SANDBOX_MATERIALIZATION_FAILED",
                test_evidence_path=evidence_path,
                proof_metadata_path=proof_metadata_path,
                detected_test_ids=(),
                invariant_refs=(),
                assertion_refs=(),
                behavioral_fragment_refs=(),
                execution_error=execution_error,
            )
            self.write_unleased_trial_evidence(
                sandbox_id,
                trial,
            )
            self.write_worker_state(
                sandbox_id,
                cycle_id,
                pass_number,
                advertised.mutation_id,
                "COMPLETED",
            )

            return trial
        specimen_candidate = None
        test_exit_code = -1
        survived = False
        fracture = False
        restored = False
        disposition = "SANDBOX_EXECUTION_FAILED"
        evidence_path = ""
        execution_error = ""
        metadata = build_proof_metadata(
            lease.repository,
            adapter,
            "",
            "",
            advertised.mutation_id,
            entry,
        )

        try:
            self.write_worker_state(
                lease.sandbox_id,
                cycle_id,
                pass_number,
                advertised.mutation_id,
                "MATERIALIZED",
            )
            matches = tuple(
                item
                for item in discover_mutations(
                    adapter,
                    lease.repository,
                )
                if item.mutation_id
                == advertised.mutation_id
            )

            if len(matches) != 1:
                raise RuntimeError(
                    "advertised mutation candidate did not uniquely resolve "
                    "inside sandbox"
                )

            specimen_candidate = matches[0]
            application = apply_mutation(
                lease.repository,
                specimen_candidate,
            )

            if not application.applied:
                raise RuntimeError(
                    "selected mutation did not alter sandbox"
                )

            self.write_worker_state(
                lease.sandbox_id,
                cycle_id,
                pass_number,
                advertised.mutation_id,
                "MUTATION_APPLIED",
            )
            self.write_worker_state(
                lease.sandbox_id,
                cycle_id,
                pass_number,
                advertised.mutation_id,
                "TEST_RUNNING",
            )
            result = run_adapter_tests(
                adapter,
                lease.repository,
                entry,
            )
            evidence_path = self.write_process_evidence(
                lease,
                result,
            )
            metadata = build_proof_metadata(
                lease.repository,
                adapter,
                result.stdout or "",
                result.stderr or "",
                advertised.mutation_id,
                entry,
            )
            test_exit_code = result.returncode
            outcome = test_process_outcome(
                result.returncode
            )
            survived = outcome == "SURVIVED"
            fracture = outcome == "FRACTURE"
            restored = restore_candidate(
                lease.repository,
                specimen_candidate,
            )

            if survived:
                disposition = "MUTATION_SURVIVED"
            elif fracture:
                disposition = "FRACTURE_OBSERVED"
            else:
                disposition = "TEST_PROCESS_FAILED"
                execution_error = (
                    "unexpected test process exit code: "
                    + str(result.returncode)
                )

            if not restored:
                survived = False
                fracture = False
                disposition = "SANDBOX_RESTORE_FAILED"
                execution_error = (
                    execution_error + "; "
                    if execution_error
                    else ""
                ) + "mutation source restoration failed"
        except BaseException as error:
            execution_error = normalize_error(
                error,
                lease.repository,
            )
            disposition = (
                "SANDBOX_INTERRUPTED"
                if not isinstance(
                    error,
                    Exception,
                )
                else "TEST_TIMEOUT"
                if isinstance(
                    error,
                    subprocess.TimeoutExpired,
                )
                else "SANDBOX_EXECUTION_FAILED"
            )
            evidence_path = self.write_execution_error(
                lease,
                execution_error,
            )

            if specimen_candidate is not None:
                restored = restore_candidate(
                    lease.repository,
                    specimen_candidate,
                )
        finally:
            sandbox_removed = self.release(
                lease
            )

        if not sandbox_removed:
            survived = False
            fracture = False
            disposition = "SANDBOX_CLEANUP_FAILED"
            execution_error = (
                execution_error + "; "
                if execution_error
                else ""
            ) + "sandbox cleanup failed"

        proof_metadata_path = self.write_proof_metadata_evidence(
            lease.sandbox_id,
            metadata,
        )

        trial = MutationTrial(
            pass_number=pass_number,
            mutation_id=advertised.mutation_id,
            identity_version=advertised.identity_version,
            proof_metadata_version=PROOF_METADATA_VERSION,
            sandbox_contract_version=SANDBOX_CONTRACT_VERSION,
            relative_path=advertised.relative_path,
            line=advertised.line,
            column=advertised.column,
            mutation_kind=advertised.kind,
            original_token=advertised.original_token,
            replacement_token=advertised.replacement_token,
            canonical_source_hash=advertised.canonical_source_hash,
            sandbox_id=lease.sandbox_id,
            test_exit_code=test_exit_code,
            survived=survived,
            fracture_observed=fracture,
            restored=restored,
            sandbox_removed=sandbox_removed,
            disposition=disposition,
            test_evidence_path=evidence_path,
            proof_metadata_path=proof_metadata_path,
            detected_test_ids=metadata.detected_test_ids,
            invariant_refs=metadata.invariant_refs,
            assertion_refs=metadata.assertion_refs,
            behavioral_fragment_refs=metadata.behavioral_fragment_refs,
            execution_error=execution_error,
        )
        self.write_trial_evidence(
            lease,
            trial,
        )
        self.write_worker_state(
            lease.sandbox_id,
            cycle_id,
            pass_number,
            advertised.mutation_id,
            (
                "COMPLETED"
                if sandbox_removed
                else "CLEANUP_FAILED"
            ),
        )

        return trial

    def record_worker_failure(
        self,
        cycle_id: str,
        pass_number: int,
        advertised: MutationCandidate,
        error: BaseException,
    ) -> MutationTrial:
        sandbox_id = sandbox_identity(
            cycle_id,
            pass_number,
            advertised.mutation_id,
        )
        root = self._validated_sandbox_root(
            sandbox_id
        )
        lease = SandboxLease(
            sandbox_id=sandbox_id,
            cycle_id=cycle_id,
            pass_number=pass_number,
            mutation_id=advertised.mutation_id,
            root=root,
            repository=root / "repository",
            evidence_root=(
                self.workers_root
                / sandbox_id
            ),
        )
        sandbox_removed = self.release(
            lease
        )
        execution_error = (
            "worker future failed: "
            + normalize_error(
                error,
                lease.repository,
            )
        )
        evidence_path = self.write_unleased_error(
            sandbox_id,
            execution_error,
        )
        metadata = build_proof_metadata(
            self.source_root,
            "",
            "",
            "",
            advertised.mutation_id,
            "",
        )
        proof_metadata_path = self.write_proof_metadata_evidence(
            sandbox_id,
            metadata,
        )
        trial = MutationTrial(
            pass_number=pass_number,
            mutation_id=advertised.mutation_id,
            identity_version=advertised.identity_version,
            proof_metadata_version=PROOF_METADATA_VERSION,
            sandbox_contract_version=SANDBOX_CONTRACT_VERSION,
            relative_path=advertised.relative_path,
            line=advertised.line,
            column=advertised.column,
            mutation_kind=advertised.kind,
            original_token=advertised.original_token,
            replacement_token=advertised.replacement_token,
            canonical_source_hash=advertised.canonical_source_hash,
            sandbox_id=sandbox_id,
            test_exit_code=-1,
            survived=False,
            fracture_observed=False,
            restored=False,
            sandbox_removed=sandbox_removed,
            disposition="WORKER_FUTURE_FAILED",
            test_evidence_path=evidence_path,
            proof_metadata_path=proof_metadata_path,
            detected_test_ids=(),
            invariant_refs=(),
            assertion_refs=(),
            behavioral_fragment_refs=(),
            execution_error=execution_error,
        )
        self.write_unleased_trial_evidence(
            sandbox_id,
            trial,
        )
        self.write_worker_state(
            sandbox_id,
            cycle_id,
            pass_number,
            advertised.mutation_id,
            (
                "COMPLETED"
                if sandbox_removed
                else "CLEANUP_FAILED"
            ),
        )

        return trial


def restore_candidate(
    specimen: Path,
    candidate: MutationCandidate,
) -> bool:
    result = git(
        specimen,
        "checkout",
        "--",
        candidate.relative_path,
    )

    if result.returncode != 0:
        return False

    status = git(
        specimen,
        "status",
        "--porcelain",
        "--",
        candidate.relative_path,
    )

    return (
        status.returncode == 0
        and not status.stdout.strip()
    )
