from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv
import json
import subprocess

from engine.proof_metadata import (
    PROOF_METADATA_VERSION,
    validate_proof_metadata_payload,
)
from engine.mutation_adapters import (
    adapter_available,
    discover_mutations,
)
from engine.sandbox_execution import (
    PROOF_EVIDENCE_VERSION,
    SANDBOX_CONTRACT_VERSION,
    MutationTrial,
    SandboxExecutor,
    normalize_error,
    sandbox_identity,
    classify_test_process_outcome,
)
from engine.target_intake import inspect_target


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    proof_evidence_version: str
    target_id: str
    source_commit: str
    adapter: str
    entry: str
    baseline_passed: bool
    baseline_sandbox_id: str
    baseline_evidence_path: str
    mutation_candidate_count: int
    passes_requested: int
    until: str
    passes_executed: int
    workers_requested: int
    workers_used: int
    fractures_observed: int
    survivors_observed: int
    execution_failures: int
    specimen_removed: bool
    original_head_preserved: bool
    disposition: str
    evidence_path: str
    proof_metadata_path: str
    trials: Tuple[MutationTrial, ...]


def git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def cycle_identity(
    target_id: str,
    source_commit: str,
    adapter: str,
    entry: str,
    max_passes: int = 1,
    until: str = "adjudication",
    candidate_id: str = "",
) -> str:
    material = "\0".join((
        PROOF_EVIDENCE_VERSION,
        target_id,
        source_commit,
        adapter,
        entry,
        str(max_passes),
        until,
        candidate_id,
    ))

    return (
        "KILN-CYCLE-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def write_trials(path: Path, trials: Tuple[MutationTrial, ...]):
    fields = [
        "pass_number",
        "mutation_id",
        "identity_version",
        "proof_metadata_version",
        "sandbox_contract_version",
        "relative_path",
        "line",
        "column",
        "mutation_kind",
        "original_token",
        "replacement_token",
        "canonical_source_hash",
        "sandbox_id",
        "test_exit_code",
        "survived",
        "fracture_observed",
        "restored",
        "sandbox_removed",
        "disposition",
        "test_evidence_path",
        "proof_metadata_path",
        "detected_test_ids",
        "invariant_refs",
        "assertion_refs",
        "behavioral_fragment_refs",
        "execution_error",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for trial in sorted(trials, key=lambda item: item.pass_number):
            row = asdict(trial)

            for field in (
                "survived",
                "fracture_observed",
                "restored",
                "sandbox_removed",
            ):
                row[field] = str(row[field]).lower()

            for field in (
                "detected_test_ids",
                "invariant_refs",
                "assertion_refs",
                "behavioral_fragment_refs",
            ):
                row[field] = json.dumps(
                    row[field],
                    separators=(",", ":"),
                )

            writer.writerow(row)


def empty_proof_metadata_aggregate() -> dict:
    return {
        "schema": "kiln.proof-metadata-aggregate.v1",
        "proof_evidence_version": PROOF_EVIDENCE_VERSION,
        "proof_metadata_version": PROOF_METADATA_VERSION,
        "trials": [],
    }


def write_proof_metadata_aggregate(
    path: Path,
    cycle_root: Path,
    trials: Tuple[MutationTrial, ...],
) -> str:
    payload = empty_proof_metadata_aggregate()

    for trial in sorted(
        trials,
        key=lambda item: item.pass_number,
    ):
        evidence_path = resolved_evidence_path(
            cycle_root,
            trial.sandbox_id,
            trial.proof_metadata_path,
        )

        try:
            metadata = json.loads(
                evidence_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "worker proof metadata evidence is malformed"
            ) from error

        validate_proof_metadata_payload(
            metadata,
            trial.mutation_id,
        )
        payload["trials"].append({
            "pass_number": trial.pass_number,
            "mutation_id": trial.mutation_id,
            "metadata": metadata,
        })

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return str(path)


def write_empty_proof_metadata_aggregate(
    path: Path,
) -> str:
    path.write_text(
        json.dumps(
            empty_proof_metadata_aggregate(),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return str(path)


def validate_parallel_result_set(
    selected,
    trials,
) -> Tuple[MutationTrial, ...]:
    ordered = tuple(
        sorted(
            trials,
            key=lambda item: item.pass_number,
        )
    )
    expected = tuple(
        range(
            1,
            len(selected) + 1,
        )
    )
    actual = tuple(
        item.pass_number
        for item in ordered
    )

    if actual != expected:
        raise RuntimeError(
            "parallel worker result set is missing, duplicate, or unknown: "
            + repr(actual)
        )

    return ordered


def resolved_evidence_path(
    cycle_root: Path,
    sandbox_id: str,
    relative_path: str,
) -> Path:
    candidate = Path(
        relative_path
    )

    if candidate.is_absolute():
        raise RuntimeError(
            "worker evidence path must be relative"
        )

    root = Path(
        cycle_root
    ).resolve()
    path = (
        root
        / candidate
    ).resolve()
    worker_root = (
        root
        / "workers"
        / sandbox_id
    ).resolve()

    try:
        path.relative_to(
            worker_root
        )
    except ValueError:
        raise RuntimeError(
            "worker evidence path escaped sandbox evidence root"
        )

    if not path.is_file():
        raise RuntimeError(
            "worker evidence reference is missing: "
            + relative_path
        )

    return path


def validate_primary_evidence(
    path: Path,
    expected_returncode: int,
    execution_error: str,
) -> None:
    if path.name == "process.json":
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "worker process evidence is malformed"
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise RuntimeError(
                "worker process evidence must be an object"
            )

        if payload.get(
            "returncode"
        ) != expected_returncode:
            raise RuntimeError(
                "worker process evidence return code mismatch"
            )

        for field in (
            "stdout_path",
            "stderr_path",
        ):
            value = payload.get(
                field
            )

            if not isinstance(
                value,
                str,
            ):
                raise RuntimeError(
                    "worker process evidence path is invalid"
                )

            output_path = (
                path.parent
                / value
            ).resolve()

            if output_path.parent != path.parent.resolve():
                raise RuntimeError(
                    "worker process output path escaped evidence root"
                )

            if not output_path.is_file():
                raise RuntimeError(
                    "worker process output evidence is missing"
                )

        return

    if path.name == "execution-error.txt":
        if not execution_error:
            raise RuntimeError(
                "execution-error evidence lacks trial error"
            )

        if not path.read_text(
            encoding="utf-8"
        ).strip():
            raise RuntimeError(
                "execution-error evidence is empty"
            )

        return

    raise RuntimeError(
        "worker evidence has unsupported primary document"
    )


def validate_trial_evidence(
    cycle_root: Path,
    cycle_id: str,
    selected,
    trials: Tuple[MutationTrial, ...],
) -> None:
    for trial in trials:
        candidate = selected[
            trial.pass_number - 1
        ]
        expected_sandbox_id = sandbox_identity(
            cycle_id,
            trial.pass_number,
            candidate.mutation_id,
        )

        if trial.mutation_id != candidate.mutation_id:
            raise RuntimeError(
                "worker mutation identity does not match authority order"
            )

        candidate_fields = {
            "identity_version": candidate.identity_version,
            "relative_path": candidate.relative_path,
            "line": candidate.line,
            "column": candidate.column,
            "mutation_kind": candidate.kind,
            "original_token": candidate.original_token,
            "replacement_token": candidate.replacement_token,
            "canonical_source_hash": candidate.canonical_source_hash,
        }

        for field, expected_value in candidate_fields.items():
            if getattr(trial, field) != expected_value:
                raise RuntimeError(
                    "worker mutation evidence conflicts with candidate: "
                    + field
                )

        if (
            trial.sandbox_contract_version
            != SANDBOX_CONTRACT_VERSION
        ):
            raise RuntimeError(
                "worker result uses an unsupported sandbox contract"
            )

        if trial.sandbox_id != expected_sandbox_id:
            raise RuntimeError(
                "worker sandbox identity does not match authority order"
            )

        if trial.survived and trial.fracture_observed:
            raise RuntimeError(
                "worker result cannot be both survivor and fracture"
            )

        if (
            trial.survived
            or trial.fracture_observed
        ) and (
            trial.execution_error
            or not trial.restored
            or not trial.sandbox_removed
        ):
            raise RuntimeError(
                "classified worker result lacks clean restoration"
            )

        outcome = classify_test_process_outcome(
            trial.test_exit_code
        )

        if trial.survived and outcome != "SURVIVED":
            raise RuntimeError(
                "survivor result has invalid process exit code"
            )

        if trial.fracture_observed and outcome != "FRACTURE":
            raise RuntimeError(
                "fracture result has invalid process exit code"
            )

        if (
            trial.survived
            and trial.disposition
            != "MUTATION_SURVIVED"
        ) or (
            trial.fracture_observed
            and trial.disposition
            != "FRACTURE_OBSERVED"
        ):
            raise RuntimeError(
                "worker classification conflicts with disposition"
            )

        if (
            not trial.survived
            and not trial.fracture_observed
            and not trial.execution_error
        ):
            raise RuntimeError(
                "unknown worker result lacks execution error"
            )

        primary = resolved_evidence_path(
            cycle_root,
            trial.sandbox_id,
            trial.test_evidence_path,
        )
        validate_primary_evidence(
            primary,
            trial.test_exit_code,
            trial.execution_error,
        )
        metadata_path = resolved_evidence_path(
            cycle_root,
            trial.sandbox_id,
            trial.proof_metadata_path,
        )

        if metadata_path.name != "proof-metadata.json":
            raise RuntimeError(
                "worker proof metadata has an unsupported document name"
            )

        try:
            metadata_payload = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "worker proof metadata evidence is malformed"
            ) from error

        validate_proof_metadata_payload(
            metadata_payload,
            trial.mutation_id,
        )

        if (
            trial.proof_metadata_version
            != PROOF_METADATA_VERSION
            or tuple(metadata_payload["detected_test_ids"])
            != trial.detected_test_ids
            or tuple(metadata_payload["invariant_refs"])
            != trial.invariant_refs
            or tuple(metadata_payload["assertion_refs"])
            != trial.assertion_refs
            or tuple(metadata_payload["behavioral_fragment_refs"])
            != trial.behavioral_fragment_refs
        ):
            raise RuntimeError(
                "worker proof metadata conflicts with trial summary"
            )

        worker_root = primary.parent
        trial_path = worker_root / "trial.json"
        state_path = worker_root / "worker-state.json"

        if not trial_path.is_file():
            raise RuntimeError(
                "worker trial evidence is missing"
            )

        try:
            trial_payload = json.loads(
                trial_path.read_text(
                    encoding="utf-8"
                )
            )
            state_payload = json.loads(
                state_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "worker trial or lifecycle evidence is malformed"
            ) from error

        expected_trial = json.loads(
            json.dumps(
                asdict(trial),
                sort_keys=True,
            )
        )

        if trial_payload != expected_trial:
            raise RuntimeError(
                "worker trial evidence does not match worker result"
            )

        if state_payload.get(
            "sandbox_id"
        ) != trial.sandbox_id:
            raise RuntimeError(
                "worker lifecycle evidence has wrong sandbox"
            )

        if (
            state_payload.get("cycle_id")
            != cycle_id
            or state_payload.get("pass_number")
            != trial.pass_number
            or state_payload.get("mutation_id")
            != trial.mutation_id
        ):
            raise RuntimeError(
                "worker lifecycle evidence conflicts with authority"
            )

        if state_payload.get(
            "state"
        ) not in {
            "COMPLETED",
            "CLEANUP_FAILED",
        }:
            raise RuntimeError(
                "worker lifecycle did not reach terminal evidence state"
            )

        expected_state = (
            "COMPLETED"
            if trial.sandbox_removed
            else "CLEANUP_FAILED"
        )

        if state_payload.get("state") != expected_state:
            raise RuntimeError(
                "worker cleanup result conflicts with lifecycle evidence"
            )


def validate_baseline_evidence(
    cycle_root: Path,
    cycle_id: str,
    baseline,
) -> None:
    expected_sandbox_id = sandbox_identity(
        cycle_id,
        0,
        "BASELINE",
    )

    if baseline.sandbox_id != expected_sandbox_id:
        raise RuntimeError(
            "baseline sandbox identity does not match cycle"
        )

    primary = resolved_evidence_path(
        cycle_root,
        baseline.sandbox_id,
        baseline.evidence_path,
    )
    validate_primary_evidence(
        primary,
        baseline.exit_code,
        baseline.execution_error,
    )
    state_path = (
        primary.parent
        / "worker-state.json"
    )

    try:
        state_payload = json.loads(
            state_path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "baseline lifecycle evidence is missing or malformed"
        ) from error

    if (
        state_payload.get("sandbox_id")
        != baseline.sandbox_id
        or state_payload.get("state")
        not in {
            "COMPLETED",
            "CLEANUP_FAILED",
        }
    ):
        raise RuntimeError(
            "baseline lifecycle evidence is not terminal"
        )

    outcome = classify_test_process_outcome(
        baseline.exit_code
    )

    if baseline.passed != (
        outcome == "SURVIVED"
        and not baseline.execution_error
        and baseline.sandbox_removed
    ):
        raise RuntimeError(
            "baseline result conflicts with process or cleanup evidence"
        )


def write_aggregate_error(
    cycle_root: Path,
    error: BaseException,
) -> None:
    path = Path(
        cycle_root
    ) / "aggregate-error.json"
    path.write_text(
        json.dumps(
            {
                "disposition": "AGGREGATE_VALIDATION_FAILED",
                "error": f"{type(error).__name__}: {error}",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def execute_parallel_trials(
    executor: SandboxExecutor,
    cycle_id: str,
    adapter: str,
    entry: str,
    selected,
    workers: int,
) -> Tuple[MutationTrial, ...]:
    futures = {}
    completed = []

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="kiln-proof",
    ) as pool:
        for pass_number, candidate in enumerate(selected, start=1):
            future = pool.submit(
                executor.execute_mutation,
                cycle_id,
                adapter,
                entry,
                pass_number,
                candidate,
            )
            futures[future] = (
                pass_number,
                candidate,
            )

        for future in as_completed(futures):
            pass_number, candidate = futures[
                future
            ]

            try:
                trial = future.result()
            except BaseException as error:
                recorder = getattr(
                    executor,
                    "record_worker_failure",
                    None,
                )

                if recorder is None:
                    raise RuntimeError(
                        "worker future failed at pass "
                        + str(pass_number)
                    ) from error

                trial = recorder(
                    cycle_id,
                    pass_number,
                    candidate,
                    error,
                )

            completed.append(
                trial
            )

    return validate_parallel_result_set(
        selected,
        completed,
    )


def execute_sequential_trials(
    executor: SandboxExecutor,
    cycle_id: str,
    adapter: str,
    entry: str,
    selected,
    until: str,
) -> Tuple[MutationTrial, ...]:
    completed = []

    for pass_number, candidate in enumerate(selected, start=1):
        trial = executor.execute_mutation(
            cycle_id,
            adapter,
            entry,
            pass_number,
            candidate,
        )
        completed.append(trial)

        if trial.execution_error or not trial.restored:
            break

        if (
            until in {"fracture", "adjudication"}
            and trial.fracture_observed
        ):
            break

    return tuple(completed)


def run_cycle(
    target: str,
    adapter: str,
    entry: str,
    max_passes: int,
    until: str,
    session_root: Path,
    candidate_id: str = "",
    workers: int = 1,
) -> CycleResult:
    if not adapter_available(adapter, Path(target)):
        raise RuntimeError(
            f"coal contract not found for adapter: {adapter}"
        )

    if max_passes < 1:
        raise RuntimeError("cycle max passes must be positive")

    if workers < 1:
        raise RuntimeError("cycle workers must be positive")

    if workers > 64:
        raise RuntimeError("cycle workers exceed safety bound")

    if workers > 1 and until != "stable":
        raise RuntimeError(
            "parallel destructive cycles require --until stable"
        )

    identity = inspect_target(target)

    if not identity.git_repository:
        raise RuntimeError(
            "destructive cycle requires Git target provenance"
        )

    if not identity.repository_clean:
        raise RuntimeError(
            "destructive cycle requires clean source repository"
        )

    source_root = Path(identity.repository_root).resolve()
    original_head = git(
        source_root,
        "rev-parse",
        "HEAD",
    ).stdout.strip()

    if original_head != identity.source_commit:
        raise RuntimeError("target identity drift detected before cycle")

    candidates = discover_mutations(adapter, source_root)
    selected = candidates[:max_passes]

    if candidate_id:
        selected = tuple(
            item
            for item in candidates
            if item.mutation_id == candidate_id
        )

        if len(selected) != 1:
            raise RuntimeError(
                "requested mutation candidate was not uniquely resolved"
            )

    cycle_id = cycle_identity(
        identity.target_id,
        identity.source_commit,
        adapter,
        entry,
        max_passes,
        until,
        candidate_id,
    )
    cycle_root = Path(session_root).resolve() / cycle_id

    try:
        cycle_root.relative_to(
            source_root
        )
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "cycle session root overlaps source repository"
        )

    cycle_root.mkdir(parents=True, exist_ok=True)
    executor = SandboxExecutor(
        source_root,
        identity.source_commit,
        cycle_root,
    )
    executor.write_cycle_state(
        cycle_id,
        "BASELINE_RUNNING",
    )

    try:
        baseline = executor.execute_baseline(
            cycle_id,
            adapter,
            entry,
        )
    except BaseException as error:
        executor.write_cycle_state(
            cycle_id,
            "INTERRUPTED",
            normalize_error(error),
        )
        raise

    evidence_path = cycle_root / "mutation-trials.csv"
    proof_metadata_path = cycle_root / "proof-metadata.json"

    try:
        validate_baseline_evidence(
            cycle_root,
            cycle_id,
            baseline,
        )
    except Exception as error:
        write_aggregate_error(
            cycle_root,
            error,
        )
        write_trials(evidence_path, ())
        write_empty_proof_metadata_aggregate(
            proof_metadata_path
        )
        executor.write_cycle_state(
            cycle_id,
            "AGGREGATE_VALIDATION_FAILED",
            normalize_error(error),
        )

        return CycleResult(
            cycle_id=cycle_id,
            proof_evidence_version=PROOF_EVIDENCE_VERSION,
            target_id=identity.target_id,
            source_commit=identity.source_commit,
            adapter=adapter,
            entry=entry,
            baseline_passed=False,
            baseline_sandbox_id=baseline.sandbox_id,
            baseline_evidence_path=baseline.evidence_path,
            mutation_candidate_count=len(candidates),
            passes_requested=max_passes,
            until=until,
            passes_executed=0,
            workers_requested=workers,
            workers_used=0,
            fractures_observed=0,
            survivors_observed=0,
            execution_failures=1,
            specimen_removed=False,
            original_head_preserved=False,
            disposition="AGGREGATE_VALIDATION_FAILED",
            evidence_path=str(evidence_path),
            proof_metadata_path=str(proof_metadata_path),
            trials=(),
        )

    if not baseline.passed:
        write_trials(evidence_path, ())
        write_empty_proof_metadata_aggregate(
            proof_metadata_path
        )
        executor.write_cycle_state(
            cycle_id,
            "COMPLETE",
            baseline.execution_error,
        )

        return CycleResult(
            cycle_id=cycle_id,
            proof_evidence_version=PROOF_EVIDENCE_VERSION,
            target_id=identity.target_id,
            source_commit=identity.source_commit,
            adapter=adapter,
            entry=entry,
            baseline_passed=False,
            baseline_sandbox_id=baseline.sandbox_id,
            baseline_evidence_path=baseline.evidence_path,
            mutation_candidate_count=len(candidates),
            passes_requested=max_passes,
            until=until,
            passes_executed=0,
            workers_requested=workers,
            workers_used=0,
            fractures_observed=0,
            survivors_observed=0,
            execution_failures=int(bool(baseline.execution_error)),
            specimen_removed=baseline.sandbox_removed,
            original_head_preserved=False,
            disposition=(
                "BASELINE_EXECUTION_FAILED"
                if baseline.execution_error
                else "BASELINE_FAILED"
            ),
            evidence_path=str(evidence_path),
            proof_metadata_path=str(proof_metadata_path),
            trials=(),
        )

    workers_used = min(workers, len(selected)) if selected else 0
    executor.write_cycle_state(
        cycle_id,
        "TRIALS_RUNNING",
    )

    try:
        if workers_used > 1:
            trials = execute_parallel_trials(
                executor,
                cycle_id,
                adapter,
                entry,
                selected,
                workers_used,
            )
        else:
            trials = execute_sequential_trials(
                executor,
                cycle_id,
                adapter,
                entry,
                selected,
                until,
            )

            validate_parallel_result_set(
                selected[:len(trials)],
                trials,
            )
    except BaseException as error:
        executor.write_cycle_state(
            cycle_id,
            "INTERRUPTED",
            normalize_error(error),
        )
        raise

    try:
        validate_trial_evidence(
            cycle_root,
            cycle_id,
            selected,
            trials,
        )
        write_proof_metadata_aggregate(
            proof_metadata_path,
            cycle_root,
            trials,
        )
    except Exception as error:
        write_aggregate_error(
            cycle_root,
            error,
        )
        write_trials(evidence_path, ())
        write_empty_proof_metadata_aggregate(
            proof_metadata_path
        )
        executor.write_cycle_state(
            cycle_id,
            "AGGREGATE_VALIDATION_FAILED",
            normalize_error(error),
        )

        return CycleResult(
            cycle_id=cycle_id,
            proof_evidence_version=PROOF_EVIDENCE_VERSION,
            target_id=identity.target_id,
            source_commit=identity.source_commit,
            adapter=adapter,
            entry=entry,
            baseline_passed=True,
            baseline_sandbox_id=baseline.sandbox_id,
            baseline_evidence_path=baseline.evidence_path,
            mutation_candidate_count=len(candidates),
            passes_requested=max_passes,
            until=until,
            passes_executed=0,
            workers_requested=workers,
            workers_used=workers_used,
            fractures_observed=0,
            survivors_observed=0,
            execution_failures=1,
            specimen_removed=False,
            original_head_preserved=False,
            disposition="AGGREGATE_VALIDATION_FAILED",
            evidence_path=str(evidence_path),
            proof_metadata_path=str(proof_metadata_path),
            trials=(),
        )

    write_trials(evidence_path, trials)
    fractures = sum(item.fracture_observed for item in trials)
    survivors = sum(item.survived for item in trials)
    execution_failures = sum(
        bool(item.execution_error)
        or not item.restored
        or not item.sandbox_removed
        for item in trials
    )
    specimens_removed = (
        baseline.sandbox_removed
        and all(item.sandbox_removed for item in trials)
    )
    disposition = "CYCLE_COMPLETE"

    if execution_failures:
        disposition = "SANDBOX_EXECUTION_FAILED"
    elif fractures:
        disposition = "FRACTURE_EVIDENCE_PRODUCED"
    elif until == "stable" and trials and len(trials) == len(selected):
        disposition = "BOUNDED_STABILITY_OBSERVED"

    result = CycleResult(
        cycle_id=cycle_id,
        proof_evidence_version=PROOF_EVIDENCE_VERSION,
        target_id=identity.target_id,
        source_commit=identity.source_commit,
        adapter=adapter,
        entry=entry,
        baseline_passed=True,
        baseline_sandbox_id=baseline.sandbox_id,
        baseline_evidence_path=baseline.evidence_path,
        mutation_candidate_count=len(candidates),
        passes_requested=max_passes,
        until=until,
        passes_executed=len(trials),
        workers_requested=workers,
        workers_used=workers_used,
        fractures_observed=fractures,
        survivors_observed=survivors,
        execution_failures=execution_failures,
        specimen_removed=specimens_removed,
        original_head_preserved=False,
        disposition=disposition,
        evidence_path=str(evidence_path),
        proof_metadata_path=str(proof_metadata_path),
        trials=trials,
    )
    executor.write_cycle_state(
        cycle_id,
        "COMPLETE",
    )

    return result


def finalize_cycle_result(result: CycleResult, target: str) -> CycleResult:
    identity = inspect_target(target)
    source_root = Path(identity.repository_root)
    head = git(source_root, "rev-parse", "HEAD")
    preserved = (
        head.returncode == 0
        and head.stdout.strip() == result.source_commit
        and identity.repository_clean
    )
    finalized = CycleResult(
        cycle_id=result.cycle_id,
        proof_evidence_version=result.proof_evidence_version,
        target_id=result.target_id,
        source_commit=result.source_commit,
        adapter=result.adapter,
        entry=result.entry,
        baseline_passed=result.baseline_passed,
        baseline_sandbox_id=result.baseline_sandbox_id,
        baseline_evidence_path=result.baseline_evidence_path,
        mutation_candidate_count=result.mutation_candidate_count,
        passes_requested=result.passes_requested,
        until=result.until,
        passes_executed=result.passes_executed,
        workers_requested=result.workers_requested,
        workers_used=result.workers_used,
        fractures_observed=result.fractures_observed,
        survivors_observed=result.survivors_observed,
        execution_failures=result.execution_failures,
        specimen_removed=result.specimen_removed,
        original_head_preserved=preserved,
        disposition=result.disposition,
        evidence_path=result.evidence_path,
        proof_metadata_path=result.proof_metadata_path,
        trials=result.trials,
    )
    result_path = Path(result.evidence_path).parent / "cycle-result.json"
    result_path.write_text(
        json.dumps(asdict(finalized), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return finalized
