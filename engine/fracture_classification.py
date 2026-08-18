from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


CLASSIFICATIONS = {
    "EXPECTED_INVARIANT_VIOLATION",
    "TEST_COVERAGE_GAP",
    "IMPLEMENTATION_DEFECT",
    "HARNESS_DEFECT",
    "ENVIRONMENTAL_DEFECT",
    "UNRESOLVED",
}


@dataclass(frozen=True)
class FractureClassification:
    fracture_id: str
    plan_id: str
    classification: str
    confidence: str
    rationale: str
    repair_authorized: bool


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classify(row):
    if row.get("baseline_proven") != "true":
        return FractureClassification(
            fracture_id=row["fracture_id"],
            plan_id=row["plan_id"],
            classification="ENVIRONMENTAL_DEFECT",
            confidence="HIGH",
            rationale="fracture lineage lacks a proven untouched baseline",
            repair_authorized=False,
        )

    if row.get("coupling_proven") != "true":
        return FractureClassification(
            fracture_id=row["fracture_id"],
            plan_id=row["plan_id"],
            classification="HARNESS_DEFECT",
            confidence="HIGH",
            rationale="pressure result lacks proven target coupling",
            repair_authorized=False,
        )

    if row.get("recovery_proven") != "true":
        return FractureClassification(
            fracture_id=row["fracture_id"],
            plan_id=row["plan_id"],
            classification="HARNESS_DEFECT",
            confidence="HIGH",
            rationale="recovery invariant failed during pressure observation",
            repair_authorized=False,
        )

    return FractureClassification(
        fracture_id=row["fracture_id"],
        plan_id=row["plan_id"],
        classification="UNRESOLVED",
        confidence="NONE",
        rationale="valid pressure fracture requires targeted root-cause evidence",
        repair_authorized=False,
    )


def classify_all(path):
    rows = read_csv(path)
    return tuple(classify(row) for row in rows)


def write_results(path, results):
    fields = [
        "fracture_id",
        "plan_id",
        "classification",
        "confidence",
        "rationale",
        "repair_authorized",
    ]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "fracture_id": item.fracture_id,
                "plan_id": item.plan_id,
                "classification": item.classification,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "repair_authorized": str(item.repair_authorized).lower(),
            })
