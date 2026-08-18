from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from time import monotonic
from typing import Tuple
import csv
import os
import shutil
import subprocess
import sys

from engine.mutation_executor import (
    MutationCandidate,
    apply_mutation,
)
from engine.mutation_adapters import (
    discover_mutations,
    run_adapter_tests,
    supported_cycle_adapters,
)
from engine.target_intake import inspect_target


@dataclass(frozen=True)
class MutationTrial:
    pass_number: int
    mutation_id: str
    relative_path: str
    line: int
    original_token: str
    replacement_token: str
    test_exit_code: int
    survived: bool
    fracture_observed: bool
    restored: bool
    disposition: str


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    target_id: str
    source_commit: str
    adapter: str
    entry: str
    baseline_passed: bool
    mutation_candidate_count: int
    passes_requested: int
    passes_executed: int
    fractures_observed: int
    survivors_observed: int
    specimen_removed: bool
    original_head_preserved: bool
    disposition: str
    evidence_path: str
    trials: Tuple[MutationTrial, ...]


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


def cycle_identity(
    target_id: str,
    source_commit: str,
    adapter: str,
    entry: str,
) -> str:
    material = "\0".join((
        target_id,
        source_commit,
        adapter,
        entry,
    ))

    return (
        "KILN-CYCLE-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def python_test_command(
    entry: str,
):
    normalized = entry.replace(
        "\\",
        "/",
    )

    target = Path(
        normalized
    )

    if target.suffix == ".py":
        module = target.with_suffix(
            ""
        ).as_posix().replace(
            "/",
            ".",
        )

        return [
            sys.executable,
            "-W",
            "error::ResourceWarning",
            "-m",
            "unittest",
            module,
        ]

    return [
        sys.executable,
        "-W",
        "error::ResourceWarning",
        "-m",
        "unittest",
        "discover",
        "-s",
        normalized,
    ]


def run_python_tests(
    specimen: Path,
    entry: str,
):
    environment = dict(
        os.environ
    )

    environment["PYTHONPATH"] = str(
        specimen
    )

    return subprocess.run(
        python_test_command(entry),
        cwd=str(specimen),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


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


def write_trials(
    path: Path,
    trials: Tuple[MutationTrial, ...],
):
    fields = [
        "pass_number",
        "mutation_id",
        "relative_path",
        "line",
        "original_token",
        "replacement_token",
        "test_exit_code",
        "survived",
        "fracture_observed",
        "restored",
        "disposition",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for trial in trials:
            row = asdict(
                trial
            )

            row["survived"] = str(
                trial.survived
            ).lower()

            row["fracture_observed"] = str(
                trial.fracture_observed
            ).lower()

            row["restored"] = str(
                trial.restored
            ).lower()

            writer.writerow(
                row
            )


def run_cycle(
    target: str,
    adapter: str,
    entry: str,
    max_passes: int,
    until: str,
    session_root: Path,
    candidate_id: str = "",
) -> CycleResult:
    if adapter not in supported_cycle_adapters():
        raise RuntimeError(
            f"unsupported cycle adapter: {adapter}"
        )

    if max_passes < 1:
        raise RuntimeError(
            "cycle max passes must be positive"
        )

    identity = inspect_target(
        target
    )

    if not identity.git_repository:
        raise RuntimeError(
            "destructive cycle requires Git target provenance"
        )

    if not identity.repository_clean:
        raise RuntimeError(
            "destructive cycle requires clean source repository"
        )

    source_root = Path(
        identity.repository_root
    ).resolve()

    original_head = (
        git(
            source_root,
            "rev-parse",
            "HEAD",
        ).stdout.strip()
    )

    if original_head != identity.source_commit:
        raise RuntimeError(
            "target identity drift detected before cycle"
        )

    cycle_id = cycle_identity(
        identity.target_id,
        identity.source_commit,
        adapter,
        entry,
    )

    cycle_root = (
        Path(session_root).resolve()
        / cycle_id
    )

    cycle_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    specimen = Path(
        mkdtemp(
            prefix="specimen-",
            dir=str(cycle_root),
        )
    )

    worktree = specimen / "repository"

    add = git(
        source_root,
        "worktree",
        "add",
        "--detach",
        str(worktree),
        identity.source_commit,
    )

    if add.returncode != 0:
        shutil.rmtree(
            specimen,
            ignore_errors=True,
        )

        raise RuntimeError(
            "unable to materialize cycle specimen"
        )

    baseline_passed = False
    specimen_removed = False
    trials = []

    try:
        baseline = run_adapter_tests(
            adapter,
            worktree,
            entry,
        )

        baseline_passed = (
            baseline.returncode == 0
        )

        if not baseline_passed:
            disposition = (
                "BASELINE_FAILED"
            )

            evidence_path = (
                cycle_root
                / "mutation-trials.csv"
            )

            write_trials(
                evidence_path,
                (),
            )

            return CycleResult(
                cycle_id=cycle_id,
                target_id=identity.target_id,
                source_commit=identity.source_commit,
                adapter=adapter,
                entry=entry,
                baseline_passed=False,
                mutation_candidate_count=0,
                passes_requested=max_passes,
                passes_executed=0,
                fractures_observed=0,
                survivors_observed=0,
                specimen_removed=False,
                original_head_preserved=False,
                disposition=disposition,
                evidence_path=str(
                    evidence_path
                ),
                trials=(),
            )

        candidates = (
            discover_mutations(
                adapter,
                worktree,
            )
        )

        selected = candidates[
            :max_passes
        ]

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

        for index, candidate in enumerate(
            selected,
            start=1,
        ):
            application = apply_mutation(
                worktree,
                candidate,
            )

            if not application.applied:
                raise RuntimeError(
                    "selected mutation did not alter specimen"
                )

            result = run_adapter_tests(
                adapter,
                worktree,
                entry,
            )

            survived = (
                result.returncode == 0
            )

            fracture = not survived

            restored = restore_candidate(
                worktree,
                candidate,
            )

            disposition = (
                "MUTATION_SURVIVED"
            )

            if fracture:
                disposition = (
                    "FRACTURE_OBSERVED"
                )

            if not restored:
                disposition = (
                    "SPECIMEN_RESTORE_FAILED"
                )

            trial = MutationTrial(
                pass_number=index,
                mutation_id=candidate.mutation_id,
                relative_path=candidate.relative_path,
                line=candidate.line,
                original_token=candidate.original_token,
                replacement_token=candidate.replacement_token,
                test_exit_code=result.returncode,
                survived=survived,
                fracture_observed=fracture,
                restored=restored,
                disposition=disposition,
            )

            trials.append(
                trial
            )

            if not restored:
                break

            if (
                until == "fracture"
                and fracture
            ):
                break

            if (
                until == "adjudication"
                and fracture
            ):
                break

        evidence_path = (
            cycle_root
            / "mutation-trials.csv"
        )

        write_trials(
            evidence_path,
            tuple(trials),
        )

        fractures = sum(
            item.fracture_observed
            for item in trials
        )

        survivors = sum(
            item.survived
            for item in trials
        )

        disposition = (
            "CYCLE_COMPLETE"
        )

        if fractures:
            disposition = (
                "FRACTURE_EVIDENCE_PRODUCED"
            )

        if (
            until == "stable"
            and trials
            and fractures == 0
            and len(trials) == len(selected)
        ):
            disposition = (
                "BOUNDED_STABILITY_OBSERVED"
            )

        return CycleResult(
            cycle_id=cycle_id,
            target_id=identity.target_id,
            source_commit=identity.source_commit,
            adapter=adapter,
            entry=entry,
            baseline_passed=True,
            mutation_candidate_count=len(
                candidates
            ),
            passes_requested=max_passes,
            passes_executed=len(
                trials
            ),
            fractures_observed=fractures,
            survivors_observed=survivors,
            specimen_removed=False,
            original_head_preserved=False,
            disposition=disposition,
            evidence_path=str(
                evidence_path
            ),
            trials=tuple(
                trials
            ),
        )

    finally:
        git(
            source_root,
            "worktree",
            "remove",
            "--force",
            str(worktree),
        )

        shutil.rmtree(
            specimen,
            ignore_errors=True,
        )

        specimen_removed = (
            not specimen.exists()
        )


def finalize_cycle_result(
    result: CycleResult,
    target: str,
) -> CycleResult:
    identity = inspect_target(
        target
    )

    source_root = Path(
        identity.repository_root
    )

    head = git(
        source_root,
        "rev-parse",
        "HEAD",
    )

    preserved = (
        head.returncode == 0
        and head.stdout.strip()
        == result.source_commit
        and identity.repository_clean
    )

    finalized = CycleResult(
        cycle_id=result.cycle_id,
        target_id=result.target_id,
        source_commit=result.source_commit,
        adapter=result.adapter,
        entry=result.entry,
        baseline_passed=result.baseline_passed,
        mutation_candidate_count=result.mutation_candidate_count,
        passes_requested=result.passes_requested,
        passes_executed=result.passes_executed,
        fractures_observed=result.fractures_observed,
        survivors_observed=result.survivors_observed,
        specimen_removed=True,
        original_head_preserved=preserved,
        disposition=result.disposition,
        evidence_path=result.evidence_path,
        trials=result.trials,
    )

    import json

    result_path = (
        Path(result.evidence_path).parent
        / "cycle-result.json"
    )

    result_path.write_text(
        json.dumps(
            asdict(finalized),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return finalized
