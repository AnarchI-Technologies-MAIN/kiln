from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import csv


@dataclass(frozen=True)
class BaselineAdjudication:
    plan_id: str
    baseline_result: str
    disposition: str
    pressure_eligible: bool
    repair_authorized: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adjudicate(row: dict) -> BaselineAdjudication:
    result = row.get("result", "").strip()

    if row.get("worktree_removed") != "true":
        raise RuntimeError("baseline recovery was not proven")

    if row.get("original_head_preserved") != "true":
        raise RuntimeError("original repository HEAD was not preserved")

    if result == "PASS":
        return BaselineAdjudication(
            plan_id=row["plan_id"],
            baseline_result=result,
            disposition="PROVEN_BASELINE",
            pressure_eligible=True,
            repair_authorized=False,
        )

    if result == "FAIL":
        return BaselineAdjudication(
            plan_id=row["plan_id"],
            baseline_result=result,
            disposition="BASELINE_FRACTURE",
            pressure_eligible=False,
            repair_authorized=False,
        )

    raise RuntimeError(f"unknown baseline result: {result}")


def adjudicate_all(path: Path) -> Tuple[BaselineAdjudication, ...]:
    return tuple(
        sorted(
            (adjudicate(row) for row in read_csv(path)),
            key=lambda item: item.plan_id,
        )
    )


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "baseline_result",
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
                "baseline_result": item.baseline_result,
                "disposition": item.disposition,
                "pressure_eligible": str(item.pressure_eligible).lower(),
                "repair_authorized": str(item.repair_authorized).lower(),
            })
