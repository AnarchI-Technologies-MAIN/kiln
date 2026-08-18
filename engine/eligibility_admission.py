from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple
import csv


DISPOSITION_MAP = {
    "READY_FOR_BASELINE_EXECUTION_PLANNING": "ELIGIBLE",
    "READY_BUT_DIRTY_REPOSITORY": "REQUIRES_ISOLATION",
    "ISOLATION_TOPOLOGY_REQUIRED": "REQUIRES_ISOLATION",
    "SANDBOX_TOPOLOGY_REQUIRED": "REQUIRES_SANDBOX",
    "RUNNER_RECONCILIATION_REQUIRED": "RUNNER_BLOCKED",
    "SUPPORT_ARTIFACT_ONLY": "SUPPORT_ONLY",
    "BLOCKED": "BLOCKED",
}

# Larger value = more restrictive when several execution contexts map
# to the same shared occurrence.
RESTRICTIVENESS = {
    "ELIGIBLE": 0,
    "REQUIRES_ISOLATION": 1,
    "REQUIRES_SANDBOX": 2,
    "SUPPORT_ONLY": 3,
    "RUNNER_BLOCKED": 4,
    "BLOCKED": 5,
}

EXECUTION_KEYS = ("execution_id", "kiln_execution_id")
OCCURRENCE_KEYS = ("occurrence_id", "test_occurrence_id", "library_occurrence_id")
DISPOSITION_KEYS = ("baseline_disposition", "disposition", "preflight_disposition")


def first(row: Mapping[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def unique_file(root: Path, filename: str) -> Path:
    matches = sorted(root.rglob(filename))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one {filename}, found {len(matches)}"
        )
    return matches[0]


def execution_occurrence_map(root: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    for path in sorted(root.rglob("*.csv")):
        try:
            rows = read_csv(path)
        except (UnicodeDecodeError, csv.Error):
            continue

        for row in rows:
            execution_id = first(row, EXECUTION_KEYS)
            occurrence_id = first(row, OCCURRENCE_KEYS)

            if not execution_id or not occurrence_id:
                continue

            prior = mapping.get(execution_id)

            if prior is not None and prior != occurrence_id:
                raise RuntimeError(
                    "conflicting execution-to-occurrence mapping: "
                    f"{execution_id}: {prior} != {occurrence_id}"
                )

            mapping[execution_id] = occurrence_id

    return mapping


@dataclass(frozen=True)
class Admission:
    occurrence_id: str
    eligibility: str
    source_dispositions: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]


def derive_admissions(kiln_root: Path) -> Tuple[Admission, ...]:
    preflight_path = unique_file(
        kiln_root,
        "kiln-baseline-preflight-001.csv",
    )

    rows = read_csv(preflight_path)
    execution_map = execution_occurrence_map(kiln_root)

    candidates: Dict[str, List[Tuple[str, str]]] = {}

    for index, row in enumerate(rows, start=2):
        disposition = first(row, DISPOSITION_KEYS)

        if disposition not in DISPOSITION_MAP:
            continue

        occurrence_id = first(row, OCCURRENCE_KEYS)

        if not occurrence_id:
            execution_id = first(row, EXECUTION_KEYS)
            occurrence_id = execution_map.get(execution_id, "")

        if not occurrence_id:
            raise RuntimeError(
                f"preflight row {index} cannot be mapped to a shared occurrence"
            )

        evidence = f"{preflight_path.name}#row-{index}"
        candidates.setdefault(occurrence_id, []).append(
            (disposition, evidence)
        )

    admissions: List[Admission] = []

    for occurrence_id in sorted(candidates):
        evidence_rows = candidates[occurrence_id]

        resolved = max(
            (DISPOSITION_MAP[item[0]] for item in evidence_rows),
            key=lambda value: RESTRICTIVENESS[value],
        )

        admissions.append(
            Admission(
                occurrence_id=occurrence_id,
                eligibility=resolved,
                source_dispositions=tuple(
                    sorted({item[0] for item in evidence_rows})
                ),
                evidence_refs=tuple(
                    sorted({item[1] for item in evidence_rows})
                ),
            )
        )

    return tuple(admissions)


def apply_admissions(
    annotation_input: Path,
    annotation_output: Path,
    admission_output: Path,
    kiln_root: Path,
) -> Tuple[int, int]:
    rows = read_csv(annotation_input)
    admissions = derive_admissions(kiln_root)
    by_occurrence = {item.occurrence_id: item for item in admissions}

    known = {row["occurrence_id"] for row in rows}
    missing = sorted(set(by_occurrence) - known)

    if missing:
        raise RuntimeError(
            f"{len(missing)} admitted occurrences are absent from the Kiln index"
        )

    updated = 0

    for row in rows:
        admission = by_occurrence.get(row["occurrence_id"])

        if admission is None:
            continue

        # Attack surfaces are intentionally untouched in Core 003.
        if row.get("attack_surfaces", "").strip():
            raise RuntimeError(
                "Core 003 input unexpectedly already contains attack surfaces"
            )

        row["eligibility"] = admission.eligibility
        row["confidence"] = "HIGH"
        row["evidence_refs"] = ";".join(admission.evidence_refs)
        row["last_state"] = "UNADJUDICATED"
        updated += 1

    annotation_output.parent.mkdir(parents=True, exist_ok=True)

    with annotation_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    admission_output.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "occurrence_id",
        "eligibility",
        "source_dispositions",
        "evidence_refs",
    ]

    with admission_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in admissions:
            writer.writerow({
                "occurrence_id": item.occurrence_id,
                "eligibility": item.eligibility,
                "source_dispositions": ";".join(item.source_dispositions),
                "evidence_refs": ";".join(item.evidence_refs),
            })

    return len(rows), updated
