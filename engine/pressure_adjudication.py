from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv


LOAD_ORDER = {
    "1x": 1,
    "2x": 2,
    "4x": 4,
    "8x": 8,
    "16x": 16,
}


@dataclass(frozen=True)
class PressureAdjudication:
    plan_id: str
    contract_id: str
    disposition: str
    highest_survived_level: str
    fracture_level: str
    fracture_observed: bool
    repair_authorized: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adjudicate_plan(rows: List[dict]) -> PressureAdjudication:
    if not rows:
        raise RuntimeError("pressure adjudication received no observations")

    ordered = sorted(
        rows,
        key=lambda row: LOAD_ORDER[row["pressure_level"]],
    )

    plan_id = ordered[0]["plan_id"]
    contract_id = ordered[0]["contract_id"]

    for row in ordered:
        if row.get("worktree_removed") != "true":
            raise RuntimeError(
                f"pressure recovery failed for plan {plan_id}"
            )

        if row.get("original_head_preserved") != "true":
            raise RuntimeError(
                f"original HEAD not preserved for plan {plan_id}"
            )

    survived = [
        row for row in ordered
        if row.get("survived") == "true"
    ]

    fractured = [
        row for row in ordered
        if row.get("survived") != "true"
    ]

    highest = ""

    if survived:
        highest = survived[-1]["pressure_level"]

    if fractured:
        fracture = fractured[0]["pressure_level"]

        return PressureAdjudication(
            plan_id=plan_id,
            contract_id=contract_id,
            disposition="PRESSURE_FRACTURE",
            highest_survived_level=highest,
            fracture_level=fracture,
            fracture_observed=True,
            repair_authorized=False,
        )

    expected_levels = ("1x", "2x", "4x", "8x", "16x")
    observed_levels = tuple(row["pressure_level"] for row in ordered)

    if observed_levels != expected_levels:
        raise RuntimeError(
            f"incomplete pressure envelope for {plan_id}: {observed_levels}"
        )

    return PressureAdjudication(
        plan_id=plan_id,
        contract_id=contract_id,
        disposition="PRESSURE_ENVELOPE_SURVIVED",
        highest_survived_level="16x",
        fracture_level="",
        fracture_observed=False,
        repair_authorized=False,
    )


def adjudicate_all(path: Path) -> Tuple[PressureAdjudication, ...]:
    rows = read_csv(path)
    grouped: Dict[str, List[dict]] = {}

    for row in rows:
        grouped.setdefault(row["plan_id"], []).append(row)

    return tuple(
        adjudicate_plan(grouped[plan_id])
        for plan_id in sorted(grouped)
    )


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "contract_id",
        "disposition",
        "highest_survived_level",
        "fracture_level",
        "fracture_observed",
        "repair_authorized",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "contract_id": item.contract_id,
                "disposition": item.disposition,
                "highest_survived_level": item.highest_survived_level,
                "fracture_level": item.fracture_level,
                "fracture_observed": str(item.fracture_observed).lower(),
                "repair_authorized": str(item.repair_authorized).lower(),
            })
