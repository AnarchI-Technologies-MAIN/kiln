from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv
import shutil


@dataclass(frozen=True)
class StagedArtifact:
    candidate_id: str
    source_path: str
    staged_path: str
    artifact_hash: str
    provenance_ref: str
    disposition: str


def artifact_hash(path: Path) -> str:
    return sha256(
        Path(path).read_bytes()
    ).hexdigest()


def candidate_identity(
    source_path: Path,
    provenance_ref: str,
) -> str:
    source = (
        str(Path(source_path).resolve())
        + "\0"
        + provenance_ref
        + "\0"
        + artifact_hash(source_path)
    )

    return (
        "KILN-REDESIGN-"
        + sha256(
            source.encode("utf-8")
        ).hexdigest()[:16].upper()
    )


def stage_artifact(
    source_path: Path,
    staging_root: Path,
    provenance_ref: str,
) -> StagedArtifact:
    source = Path(source_path).resolve()
    staging = Path(staging_root).resolve()

    if not source.exists():
        raise RuntimeError(
            "redesign artifact source is missing"
        )

    if not source.is_file():
        raise RuntimeError(
            "redesign artifact source is not a file"
        )

    candidate_id = candidate_identity(
        source,
        provenance_ref,
    )

    destination = (
        staging
        / candidate_id
        / source.name
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )

    source_hash = artifact_hash(
        source
    )

    staged_hash = artifact_hash(
        destination
    )

    if source_hash != staged_hash:
        raise RuntimeError(
            "staged artifact hash mismatch"
        )

    return StagedArtifact(
        candidate_id=candidate_id,
        source_path=str(source),
        staged_path=str(destination),
        artifact_hash=staged_hash,
        provenance_ref=provenance_ref,
        disposition="STAGED_FOR_ADJUDICATION",
    )


def write_registry(
    path: Path,
    artifacts: Tuple[StagedArtifact, ...],
):
    fields = [
        "candidate_id",
        "source_path",
        "staged_path",
        "artifact_hash",
        "provenance_ref",
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

        for item in artifacts:
            writer.writerow({
                "candidate_id": item.candidate_id,
                "source_path": item.source_path,
                "staged_path": item.staged_path,
                "artifact_hash": item.artifact_hash,
                "provenance_ref": item.provenance_ref,
                "disposition": item.disposition,
            })


@dataclass(frozen=True)
class RedesignAdjudication:
    candidate_id: str
    promotion_eligible: bool
    disposition: str
    failed_gates: Tuple[str, ...]


def adjudicate_redesign(
    artifact: StagedArtifact,
    baseline_preserved: bool,
    fracture_mitigated: bool,
) -> RedesignAdjudication:
    failures = []

    if artifact.disposition != "STAGED_FOR_ADJUDICATION":
        failures.append("ARTIFACT_NOT_STAGED")

    if not artifact.provenance_ref.strip():
        failures.append("MISSING_PROVENANCE")

    if not baseline_preserved:
        failures.append("BASELINE_REGRESSION")

    if not fracture_mitigated:
        failures.append("FRACTURE_NOT_MITIGATED")

    eligible = len(failures) == 0

    disposition = "PROMOTION_ELIGIBLE"

    if not eligible:
        disposition = "PROMOTION_BLOCKED"

    return RedesignAdjudication(
        candidate_id=artifact.candidate_id,
        promotion_eligible=eligible,
        disposition=disposition,
        failed_gates=tuple(sorted(set(failures))),
    )

@dataclass(frozen=True)
class ContaminationScan:
    candidate_id: str
    clean: bool
    disposition: str
    findings: Tuple[str, ...]


SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "secrets.json",
}

DISPOSABLE_PARTS = {
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "kiln-staging",
}

SECRET_PATTERNS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "AWS_SECRET_ACCESS_KEY=",
    "STRIPE_SECRET_KEY=",
    "RESEND_API_KEY=",
)


def scan_staged_artifact(
    artifact: StagedArtifact,
) -> ContaminationScan:
    path = Path(
        artifact.staged_path
    )

    findings = []

    if not path.exists():
        findings.append(
            "STAGED_ARTIFACT_MISSING"
        )

    if path.name.lower() in SECRET_FILENAMES:
        findings.append(
            "SECRET_BEARING_FILENAME"
        )

    if any(
        part in DISPOSABLE_PARTS
        for part in path.parts
    ):
        findings.append(
            "DISPOSABLE_ARTIFACT_PATH"
        )

    if path.exists() and path.is_file():
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            content = ""

        for pattern in SECRET_PATTERNS:
            if pattern in content:
                findings.append(
                    "SECRET_PATTERN_DETECTED"
                )
                break

    clean = len(findings) == 0

    disposition = "PROMOTION_CONTAMINATION_CLEAR"

    if not clean:
        disposition = "PROMOTION_CONTAMINATION_BLOCKED"

    return ContaminationScan(
        candidate_id=artifact.candidate_id,
        clean=clean,
        disposition=disposition,
        findings=tuple(
            sorted(set(findings))
        ),
    )

@dataclass(frozen=True)
class PromotionPreflight:
    candidate_id: str
    approved: bool
    target_head: str
    destination_path: str
    promotion_authorized: bool
    disposition: str
    failed_gates: Tuple[str, ...]


def git(repo: Path, *args: str):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def preflight_promotion(
    artifact: StagedArtifact,
    adjudication: RedesignAdjudication,
    contamination: ContaminationScan,
    target_repo: Path,
    destination_path: str,
    expected_head: str,
    approved: bool,
) -> PromotionPreflight:
    repo = Path(target_repo).resolve()
    failures = []

    if not approved:
        failures.append("APPROVAL_REQUIRED")

    if not adjudication.promotion_eligible:
        failures.append("REDESIGN_NOT_ELIGIBLE")

    if not contamination.clean:
        failures.append("CONTAMINATION_GATE_FAILED")

    staged = Path(artifact.staged_path)

    if not staged.exists():
        failures.append("STAGED_ARTIFACT_MISSING")

    if staged.exists():
        if artifact_hash(staged) != artifact.artifact_hash:
            failures.append("STAGED_ARTIFACT_DRIFT")

    if not destination_path.strip():
        failures.append("DESTINATION_REQUIRED")

    destination = Path(destination_path)

    if destination.is_absolute() or ".." in destination.parts:
        failures.append("DESTINATION_OUTSIDE_REPOSITORY")

    head = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    current_head = ""

    if head.returncode != 0:
        failures.append("TARGET_NOT_GIT_REPOSITORY")

    if head.returncode == 0:
        current_head = head.stdout.strip()

        if current_head != expected_head:
            failures.append("TARGET_HEAD_DRIFT")

    authorized = len(failures) == 0

    disposition = "PROMOTION_AUTHORIZED"

    if not authorized:
        disposition = "PROMOTION_BLOCKED"

    return PromotionPreflight(
        candidate_id=artifact.candidate_id,
        approved=approved,
        target_head=current_head,
        destination_path=destination_path,
        promotion_authorized=authorized,
        disposition=disposition,
        failed_gates=tuple(sorted(set(failures))),
    )

@dataclass(frozen=True)
class RedesignRoute:
    candidate_id: str
    route: str
    disposition: str
    reasons: Tuple[str, ...]


def decide_redesign_route(
    candidate_id: str,
    baseline_preserved: bool,
    fracture_mitigated: bool,
    regression_observed: bool,
    evidence_sufficient: bool,
    candidate_recoverable: bool,
) -> RedesignRoute:
    reasons = []

    if not candidate_recoverable:
        reasons.append("CANDIDATE_UNRECOVERABLE")

        return RedesignRoute(
            candidate_id=candidate_id,
            route="HARD_ROLLBACK",
            disposition="REDESIGN_ROUTED",
            reasons=tuple(reasons),
        )

    if not baseline_preserved:
        reasons.append("BASELINE_REGRESSION")

    if regression_observed:
        reasons.append("NEW_REGRESSION_OBSERVED")

    if reasons:
        return RedesignRoute(
            candidate_id=candidate_id,
            route="SOFT_ROLLBACK",
            disposition="REDESIGN_ROUTED",
            reasons=tuple(sorted(set(reasons))),
        )

    if not fracture_mitigated:
        return RedesignRoute(
            candidate_id=candidate_id,
            route="MUTATE_AGAIN",
            disposition="REDESIGN_ROUTED",
            reasons=("FRACTURE_NOT_MITIGATED",),
        )

    if not evidence_sufficient:
        return RedesignRoute(
            candidate_id=candidate_id,
            route="RETURN_TO_FIRE",
            disposition="REDESIGN_ROUTED",
            reasons=("MORE_BREAKAGE_EVIDENCE_REQUIRED",),
        )

    return RedesignRoute(
        candidate_id=candidate_id,
        route="STAGE_FOR_ADJUDICATION",
        disposition="REDESIGN_ROUTED",
        reasons=("IMPROVEMENT_EVIDENCE_SUFFICIENT",),
    )

@dataclass(frozen=True)
class RollbackResult:
    mode: str
    failed_artifact_hash: str
    restored_artifact_hash: str
    evidence_path: str
    rollback_proven: bool
    disposition: str


def rollback_artifact(
    active_path: Path,
    soft_restore_path: Path,
    hard_restore_path: Path,
    evidence_root: Path,
    mode: str,
) -> RollbackResult:
    active = Path(active_path).resolve()
    soft = Path(soft_restore_path).resolve()
    hard = Path(hard_restore_path).resolve()
    evidence = Path(evidence_root).resolve()

    if mode not in {
        "SOFT_ROLLBACK",
        "HARD_ROLLBACK",
    }:
        raise RuntimeError(
            "unsupported rollback mode"
        )

    if not active.exists():
        raise RuntimeError(
            "active redesign artifact is missing"
        )

    restore = soft

    if mode == "HARD_ROLLBACK":
        restore = hard

    if not restore.exists():
        raise RuntimeError(
            "rollback source is missing"
        )

    failed_hash = artifact_hash(
        active
    )

    evidence.mkdir(
        parents=True,
        exist_ok=True,
    )

    failed_copy = (
        evidence
        / f"{failed_hash}.failed"
    )

    shutil.copy2(
        active,
        failed_copy,
    )

    shutil.copy2(
        restore,
        active,
    )

    restored_hash = artifact_hash(
        active
    )

    expected_hash = artifact_hash(
        restore
    )

    proven = (
        failed_copy.exists()
        and artifact_hash(failed_copy) == failed_hash
        and restored_hash == expected_hash
    )

    disposition = "ROLLBACK_PROVEN"

    if not proven:
        disposition = "ROLLBACK_FAILED"

    return RollbackResult(
        mode=mode,
        failed_artifact_hash=failed_hash,
        restored_artifact_hash=restored_hash,
        evidence_path=str(failed_copy),
        rollback_proven=proven,
        disposition=disposition,
    )

@dataclass(frozen=True)
class PromotionResult:
    candidate_id: str
    commit_hash: str
    remote_commit: str
    pushed: bool
    remote_verified: bool
    disposition: str


def execute_promotion(
    artifact: StagedArtifact,
    preflight: PromotionPreflight,
    target_repo: Path,
    remote_name: str,
    branch_name: str,
    commit_message: str,
) -> PromotionResult:
    import shutil

    repo = Path(target_repo).resolve()

    if not preflight.promotion_authorized:
        raise RuntimeError(
            "promotion preflight is not authorized"
        )

    staged = Path(
        artifact.staged_path
    )

    destination = (
        repo
        / preflight.destination_path
    ).resolve()

    try:
        destination.relative_to(repo)
    except ValueError:
        raise RuntimeError(
            "promotion destination escaped repository"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        staged,
        destination,
    )

    add = git(
        repo,
        "add",
        "--",
        preflight.destination_path,
    )

    if add.returncode != 0:
        raise RuntimeError(
            "git staging failed"
        )

    staged_names = git(
        repo,
        "diff",
        "--cached",
        "--name-only",
    )

    if staged_names.returncode != 0:
        raise RuntimeError(
            "unable to inspect staged paths"
        )

    names = tuple(
        line.strip()
        for line in staged_names.stdout.splitlines()
        if line.strip()
    )

    normalized_destination = (
        Path(
            preflight.destination_path
        ).as_posix()
    )

    if names != (
        normalized_destination,
    ):
        git(
            repo,
            "reset",
            "HEAD",
            "--",
            preflight.destination_path,
        )

        raise RuntimeError(
            "staged path set differs from authorized artifact"
        )

    commit = git(
        repo,
        "commit",
        "-m",
        commit_message,
        "--",
        preflight.destination_path,
    )

    if commit.returncode != 0:
        raise RuntimeError(
            "promotion commit failed"
        )

    head = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    if head.returncode != 0:
        raise RuntimeError(
            "unable to resolve promotion commit"
        )

    commit_hash = head.stdout.strip()

    push = git(
        repo,
        "push",
        remote_name,
        f"HEAD:{branch_name}",
    )

    pushed = push.returncode == 0
    remote_commit = ""
    remote_verified = False

    if pushed:
        remote = git(
            repo,
            "ls-remote",
            remote_name,
            f"refs/heads/{branch_name}",
        )

        if remote.returncode == 0:
            fields = remote.stdout.strip().split()

            if fields:
                remote_commit = fields[0]
                remote_verified = (
                    remote_commit
                    == commit_hash
                )

    disposition = "PROMOTION_VERIFIED"

    if not pushed:
        disposition = "PROMOTION_PUSH_FAILED"

    if pushed and not remote_verified:
        disposition = "PROMOTION_REMOTE_VERIFICATION_FAILED"

    return PromotionResult(
        candidate_id=artifact.candidate_id,
        commit_hash=commit_hash,
        remote_commit=remote_commit,
        pushed=pushed,
        remote_verified=remote_verified,
        disposition=disposition,
    )

def close_promoted_candidate(
    registry_path: Path,
    artifacts: Tuple[StagedArtifact, ...],
    promotion: PromotionResult,
) -> Tuple[StagedArtifact, ...]:
    if (
        promotion.disposition != "PROMOTION_VERIFIED"
        or not promotion.pushed
        or not promotion.remote_verified
        or not promotion.commit_hash
        or promotion.commit_hash != promotion.remote_commit
    ):
        return artifacts

    remaining = tuple(
        artifact
        for artifact in artifacts
        if artifact.candidate_id != promotion.candidate_id
    )

    write_registry(
        Path(registry_path),
        remaining,
    )

    return remaining