from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Tuple
import csv
import hashlib

from .library_index import KilnLibraryIndex


ALLOWED_ELIGIBILITY = {
    "ELIGIBLE",
    "REQUIRES_ISOLATION",
    "REQUIRES_SANDBOX",
}


RECOVERY_MODE = {
    "ELIGIBLE": "DETACHED_WORKTREE",
    "REQUIRES_ISOLATION": "DETACHED_WORKTREE",
    "REQUIRES_SANDBOX": "SANDBOX",
}


@dataclass(frozen=True)
class KilnCandidate:
    candidate_id: str
    occurrence_id: str
    content_id: str
    repository_root: str
    repository_path: str
    runner: str
    eligibility: str
    recovery_mode: str
    attack_surfaces: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> Tuple[str, ...]:
    return tuple(
        sorted({item.strip() for item in str(value).split(";") if item.strip()})
    )


def candidate_identity(
    occurrence_id: str,
    content_id: str,
    surfaces: Tuple[str, ...],
) -> str:
    material = "|".join(
        (occurrence_id, content_id, ",".join(surfaces))
    ).encode("utf-8")

    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"KILN-CANDIDATE-{digest}"


def build_candidates(
    annotation_path: Path,
    library_index: KilnLibraryIndex,
) -> Tuple[KilnCandidate, ...]:
    rows = read_csv(annotation_path)
    candidates = []

    for row in rows:
        eligibility = row.get("eligibility", "").strip()

        if eligibility not in ALLOWED_ELIGIBILITY:
            continue

        surfaces = split_values(row.get("attack_surfaces", ""))

        if not surfaces:
            continue

        occurrence_id = row["occurrence_id"].strip()
        content_id = row["content_id"].strip()

        shared = library_index.get(occurrence_id)

        if shared is None:
            raise RuntimeError(
                f"candidate references unknown occurrence {occurrence_id}"
            )

        if shared.content_id != content_id:
            raise RuntimeError(
                f"content identity mismatch for {occurrence_id}"
            )

        evidence = split_values(row.get("evidence_refs", ""))
        surface_evidence = split_values(
            row.get("attack_surface_evidence", "")
        )

        combined_evidence = tuple(
            sorted(set(evidence).union(surface_evidence))
        )

        if not combined_evidence:
            raise RuntimeError(
                f"candidate {occurrence_id} has no preserved evidence"
            )

        candidates.append(
            KilnCandidate(
                candidate_id=candidate_identity(
                    occurrence_id,
                    content_id,
                    surfaces,
                ),
                occurrence_id=occurrence_id,
                content_id=content_id,
                repository_root=shared.repository_root,
                repository_path=shared.repository_path,
                runner=shared.runner,
                eligibility=eligibility,
                recovery_mode=RECOVERY_MODE[eligibility],
                attack_surfaces=surfaces,
                evidence_refs=combined_evidence,
            )
        )

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.occurrence_id,
                item.candidate_id,
            ),
        )
    )


def write_candidates(path: Path, candidates: Tuple[KilnCandidate, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "candidate_id",
        "occurrence_id",
        "content_id",
        "repository_root",
        "repository_path",
        "runner",
        "eligibility",
        "recovery_mode",
        "attack_surfaces",
        "evidence_refs",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in candidates:
            writer.writerow({
                "candidate_id": item.candidate_id,
                "occurrence_id": item.occurrence_id,
                "content_id": item.content_id,
                "repository_root": item.repository_root,
                "repository_path": item.repository_path,
                "runner": item.runner,
                "eligibility": item.eligibility,
                "recovery_mode": item.recovery_mode,
                "attack_surfaces": ";".join(item.attack_surfaces),
                "evidence_refs": ";".join(item.evidence_refs),
            })
