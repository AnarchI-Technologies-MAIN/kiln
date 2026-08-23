from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Tuple
import shutil
import subprocess

from engine.mutation_adapters import (
    adapter_available,
    discover_mutations,
    run_adapter_tests,
)
from engine.coal_contracts import resolve_coal_contract
from engine.target_intake import inspect_target


@dataclass(frozen=True)
class TargetPreflight:
    target_id: str
    source_commit: str
    adapter: str
    entry: str
    git_repository: bool
    repository_clean: bool
    adapter_supported: bool
    entry_ready: bool
    mutation_candidate_count: int
    disposition: str
    blockers: Tuple[str, ...]


@dataclass(frozen=True)
class TargetBaseline:
    target_id: str
    source_commit: str
    adapter: str
    entry: str
    baseline_passed: bool
    exit_code: int
    specimen_removed: bool
    original_head_preserved: bool
    disposition: str


@dataclass(frozen=True)
class CandidateInventory:
    target_id: str
    source_commit: str
    adapter: str
    candidate_count: int
    candidate_ids: Tuple[str, ...]
    disposition: str


@dataclass(frozen=True)
class SurfaceInventory:
    target_id: str
    source_commit: str
    adapter: str
    mutation_kinds: Tuple[str, ...]
    candidate_count: int
    disposition: str


@dataclass(frozen=True)
class TargetProof:
    target_id: str
    source_commit: str
    adapter: str
    entry: str
    preflight_passed: bool
    baseline_passed: bool
    mutation_candidate_count: int
    original_head_preserved: bool
    destructive_execution_performed: bool
    disposition: str


def git(
    repo: Path,
    *args: str,
):
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def javascript_entry_ready(
    root: Path,
    entry: str,
) -> bool:
    package = root / "package.json"

    if not package.exists():
        return False

    try:
        import json

        payload = json.loads(
            package.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return False

    scripts = payload.get(
        "scripts",
        {},
    )

    return entry in scripts


def target_entry_ready(
    root: Path,
    adapter: str,
    entry: str,
) -> bool:
    contract = resolve_coal_contract(
        adapter,
        root,
    )

    if contract is None:
        return False

    entry_kind = contract.execution.entry_kind

    if entry_kind == "script":
        return javascript_entry_ready(
            root,
            entry,
        )

    if entry_kind == "none":
        return True

    if entry_kind == "opaque":
        return bool(entry.strip())

    target = (
        root
        / entry
    ).resolve()

    try:
        target.relative_to(
            root
        )
    except ValueError:
        return False

    return target.exists()


def inspect_candidates(
    target: str,
    adapter: str,
) -> CandidateInventory:
    identity = inspect_target(
        target
    )

    root = Path(
        identity.repository_root
    ).resolve()

    if not adapter_available(adapter, root):
        raise RuntimeError(
            f"coal contract not found for adapter: {adapter}"
        )

    candidates = discover_mutations(
        adapter,
        root,
    )

    return CandidateInventory(
        target_id=identity.target_id,
        source_commit=identity.source_commit,
        adapter=adapter,
        candidate_count=len(
            candidates
        ),
        candidate_ids=tuple(
            item.mutation_id
            for item in candidates
        ),
        disposition="CANDIDATE_INVENTORY_READY",
    )


def inspect_surfaces(
    target: str,
    adapter: str,
) -> SurfaceInventory:
    identity = inspect_target(
        target
    )

    root = Path(
        identity.repository_root
    ).resolve()

    candidates = discover_mutations(
        adapter,
        root,
    )

    kinds = tuple(
        sorted(
            set(
                item.kind
                for item in candidates
            )
        )
    )

    return SurfaceInventory(
        target_id=identity.target_id,
        source_commit=identity.source_commit,
        adapter=adapter,
        mutation_kinds=kinds,
        candidate_count=len(
            candidates
        ),
        disposition="MUTATION_SURFACE_INVENTORIED",
    )


def preflight_target(
    target: str,
    adapter: str,
    entry: str,
) -> TargetPreflight:
    identity = inspect_target(
        target
    )

    root = Path(
        identity.repository_root
    ).resolve()

    blockers = []

    if not identity.git_repository:
        blockers.append(
            "GIT_PROVENANCE_REQUIRED"
        )

    if not identity.repository_clean:
        blockers.append(
            "CLEAN_SOURCE_REQUIRED"
        )

    adapter_supported = adapter_available(
        adapter,
        root,
    )

    if not adapter_supported:
        blockers.append(
            "COAL_CONTRACT_MISSING"
        )

    entry_ready = False

    if adapter_supported:
        entry_ready = target_entry_ready(
            root,
            adapter,
            entry,
        )

    if not entry_ready:
        blockers.append(
            "ENTRY_NOT_READY"
        )

    candidate_count = 0

    if adapter_supported:
        candidate_count = len(
            discover_mutations(
                adapter,
                root,
            )
        )

    disposition = "READY_FOR_KILN_PROOF"

    if blockers:
        disposition = "PREFLIGHT_BLOCKED"

    return TargetPreflight(
        target_id=identity.target_id,
        source_commit=identity.source_commit,
        adapter=adapter,
        entry=entry,
        git_repository=identity.git_repository,
        repository_clean=identity.repository_clean,
        adapter_supported=adapter_supported,
        entry_ready=entry_ready,
        mutation_candidate_count=candidate_count,
        disposition=disposition,
        blockers=tuple(
            sorted(
                blockers
            )
        ),
    )


def run_target_baseline(
    target: str,
    adapter: str,
    entry: str,
) -> TargetBaseline:
    preflight = preflight_target(
        target,
        adapter,
        entry,
    )

    if preflight.disposition != "READY_FOR_KILN_PROOF":
        return TargetBaseline(
            target_id=preflight.target_id,
            source_commit=preflight.source_commit,
            adapter=adapter,
            entry=entry,
            baseline_passed=False,
            exit_code=-1,
            specimen_removed=True,
            original_head_preserved=False,
            disposition="BASELINE_BLOCKED",
        )

    identity = inspect_target(
        target
    )

    source = Path(
        identity.repository_root
    ).resolve()

    holder = Path(
        mkdtemp(
            prefix="kiln-cli-baseline-"
        )
    )

    specimen = (
        holder
        / "repository"
    )

    added = git(
        source,
        "worktree",
        "add",
        "--detach",
        str(specimen),
        identity.source_commit,
    )

    if added.returncode != 0:
        shutil.rmtree(
            holder,
            ignore_errors=True,
        )

        raise RuntimeError(
            "unable to materialize baseline specimen"
        )

    exit_code = -1
    baseline_passed = False

    try:
        result = run_adapter_tests(
            adapter,
            specimen,
            entry,
        )

        exit_code = result.returncode
        baseline_passed = (
            exit_code == 0
        )

    finally:
        git(
            source,
            "worktree",
            "remove",
            "--force",
            str(specimen),
        )

        shutil.rmtree(
            holder,
            ignore_errors=True,
        )

    post = inspect_target(
        target
    )

    preserved = (
        post.git_repository
        and post.repository_clean
        and post.source_commit
        == identity.source_commit
    )

    removed = not holder.exists()

    disposition = "BASELINE_PROVEN"

    if not baseline_passed:
        disposition = "BASELINE_FAILED"

    if not removed:
        disposition = "BASELINE_TEARDOWN_FAILED"

    if not preserved:
        disposition = "SOURCE_PRESERVATION_FAILED"

    return TargetBaseline(
        target_id=identity.target_id,
        source_commit=identity.source_commit,
        adapter=adapter,
        entry=entry,
        baseline_passed=baseline_passed,
        exit_code=exit_code,
        specimen_removed=removed,
        original_head_preserved=preserved,
        disposition=disposition,
    )


def prove_target(
    target: str,
    adapter: str,
    entry: str,
) -> TargetProof:
    preflight = preflight_target(
        target,
        adapter,
        entry,
    )

    if preflight.disposition != "READY_FOR_KILN_PROOF":
        return TargetProof(
            target_id=preflight.target_id,
            source_commit=preflight.source_commit,
            adapter=adapter,
            entry=entry,
            preflight_passed=False,
            baseline_passed=False,
            mutation_candidate_count=preflight.mutation_candidate_count,
            original_head_preserved=False,
            destructive_execution_performed=False,
            disposition="PROOF_BLOCKED",
        )

    baseline = run_target_baseline(
        target,
        adapter,
        entry,
    )

    disposition = "TARGET_PROVEN_FOR_BOUNDED_CYCLE"

    if not baseline.baseline_passed:
        disposition = "TARGET_PROOF_FAILED"

    if not baseline.original_head_preserved:
        disposition = "TARGET_PROOF_FAILED"

    return TargetProof(
        target_id=baseline.target_id,
        source_commit=baseline.source_commit,
        adapter=adapter,
        entry=entry,
        preflight_passed=True,
        baseline_passed=baseline.baseline_passed,
        mutation_candidate_count=preflight.mutation_candidate_count,
        original_head_preserved=baseline.original_head_preserved,
        destructive_execution_performed=False,
        disposition=disposition,
    )
