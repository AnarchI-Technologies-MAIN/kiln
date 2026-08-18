from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import csv


@dataclass(frozen=True)
class CouplingAdjudication:
    plan_id: str
    coupling_id: str
    disposition: str
    pressure_eligible: bool
    repair_authorized: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adjudicate(row: dict) -> CouplingAdjudication:
    recovery_ok = (
        row.get("worktree_removed") == "true"
        and row.get("original_head_preserved") == "true"
    )

    if not recovery_ok:
        return CouplingAdjudication(
            plan_id=row["plan_id"],
            coupling_id=row["coupling_id"],
            disposition="COUPLING_TRIAL_FRACTURE",
            pressure_eligible=False,
            repair_authorized=False,
        )

    if row.get("coupling_proven") == "true":
        return CouplingAdjudication(
            plan_id=row["plan_id"],
            coupling_id=row["coupling_id"],
            disposition="PROVEN_COUPLING",
            pressure_eligible=True,
            repair_authorized=False,
        )

    return CouplingAdjudication(
        plan_id=row["plan_id"],
        coupling_id=row["coupling_id"],
        disposition="UNPROVEN_COUPLING",
        pressure_eligible=False,
        repair_authorized=False,
    )


def adjudicate_all(path: Path) -> Tuple[CouplingAdjudication, ...]:
    return tuple(
        sorted(
            (adjudicate(row) for row in read_csv(path)),
            key=lambda item: item.plan_id,
        )
    )


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "coupling_id",
        "disposition",
        "pressure_eligible",
        "repair_authorized",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "coupling_id": item.coupling_id,
                "disposition": item.disposition,
                "pressure_eligible": str(item.pressure_eligible).lower(),
                "repair_authorized": str(item.repair_authorized).lower(),
            })
