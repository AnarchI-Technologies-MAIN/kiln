from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Mapping
import csv


EXECUTION_KEYS = ("execution_id", "kiln_execution_id")
OCCURRENCE_KEYS = ("occurrence_id", "test_occurrence_id", "library_occurrence_id")
PROFILE_KEYS = ("profile_id", "pressure_profile_id")
SURFACE_KEYS = ("attack_surface", "surface", "attack_surface_name")
CONFIDENCE_KEYS = ("confidence", "surface_confidence")


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


def build_maps(root: Path):
    execution_to_occurrence: Dict[str, str] = {}
    profile_to_execution: Dict[str, str] = {}
    profile_to_occurrence: Dict[str, str] = {}

    for path in sorted(root.rglob("*.csv")):
        try:
            rows = read_csv(path)
        except (UnicodeDecodeError, csv.Error):
            continue

        for row in rows:
            execution = first(row, EXECUTION_KEYS)
            occurrence = first(row, OCCURRENCE_KEYS)
            profile = first(row, PROFILE_KEYS)

            if execution and occurrence:
                prior = execution_to_occurrence.get(execution)
                if prior is not None and prior != occurrence:
                    raise RuntimeError(
                        f"conflicting execution mapping for {execution}"
                    )
                execution_to_occurrence[execution] = occurrence

            if profile and execution:
                prior = profile_to_execution.get(profile)
                if prior is not None and prior != execution:
                    raise RuntimeError(
                        f"conflicting profile mapping for {profile}"
                    )
                profile_to_execution[profile] = execution

            if profile and occurrence:
                prior = profile_to_occurrence.get(profile)
                if prior is not None and prior != occurrence:
                    raise RuntimeError(
                        f"conflicting profile occurrence for {profile}"
                    )
                profile_to_occurrence[profile] = occurrence

    return execution_to_occurrence, profile_to_execution, profile_to_occurrence


def admit_surfaces(annotation_input, annotation_output, ledger_output, kiln_root):
    source = unique_file(kiln_root, "kiln-attack-surface-index-001.csv")
    surface_rows = read_csv(source)

    if len(surface_rows) != 12:
        raise RuntimeError(
            f"expected 12 harvested attack-surface records, found {len(surface_rows)}"
        )

    execution_map, profile_execution, profile_occurrence = build_maps(kiln_root)

    annotations = read_csv(annotation_input)
    by_occurrence = {row["occurrence_id"]: row for row in annotations}

    admitted = []

    for index, source_row in enumerate(surface_rows, start=2):
        surface = first(source_row, SURFACE_KEYS)

        if not surface:
            raise RuntimeError(f"attack-surface row {index} has no surface")

        occurrence = first(source_row, OCCURRENCE_KEYS)
        execution = first(source_row, EXECUTION_KEYS)
        profile = first(source_row, PROFILE_KEYS)

        if not occurrence and execution:
            occurrence = execution_map.get(execution, "")

        if not occurrence and profile:
            occurrence = profile_occurrence.get(profile, "")

        if not occurrence and profile:
            mapped_execution = profile_execution.get(profile, "")
            occurrence = execution_map.get(mapped_execution, "")

        if not occurrence:
            raise RuntimeError(
                f"attack-surface row {index} cannot be mapped to a shared occurrence"
            )

        target = by_occurrence.get(occurrence)

        if target is None:
            raise RuntimeError(
                f"attack-surface row {index} references unknown occurrence {occurrence}"
            )

        evidence = f"{source.name}#row-{index}"
        confidence = first(source_row, CONFIDENCE_KEYS).upper() or "NONE"

        existing_names = [
            item for item in target.get("attack_surfaces", "").split(";") if item
        ]

        if surface not in existing_names:
            existing_names.append(surface)

        evidence_items = [
            item
            for item in target.get("attack_surface_evidence", "").split(";")
            if item
        ]

        evidence_item = f"{surface}:{evidence}"

        if evidence_item not in evidence_items:
            evidence_items.append(evidence_item)

        target["attack_surfaces"] = ";".join(sorted(existing_names))
        target["attack_surface_evidence"] = ";".join(sorted(evidence_items))

        admitted.append({
            "occurrence_id": occurrence,
            "profile_id": profile,
            "execution_id": execution,
            "attack_surface": surface,
            "confidence": confidence,
            "evidence_ref": evidence,
        })

    annotation_output.parent.mkdir(parents=True, exist_ok=True)

    with annotation_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(annotations[0].keys()))
        writer.writeheader()
        writer.writerows(annotations)

    fields = [
        "occurrence_id",
        "profile_id",
        "execution_id",
        "attack_surface",
        "confidence",
        "evidence_ref",
    ]

    with ledger_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(admitted)

    return len(annotations), len(admitted)
