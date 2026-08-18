from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class CampaignClosure:
    plan_id: str
    attack_surface: str
    disposition: str
    highest_proven_level: str
    baseline_proven: bool
    coupling_proven: bool
    fracture_count: int
    repair_authorized: bool


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def close_campaign(
    pressure_path,
    fracture_path,
    classification_path,
    baseline_path,
    coupling_path,
):
    pressures = read_csv(pressure_path)
    fractures = read_csv(fracture_path)
    classifications = read_csv(classification_path)
    baselines = {row["plan_id"]: row for row in read_csv(baseline_path)}
    couplings = {row["plan_id"]: row for row in read_csv(coupling_path)}

    if len(classifications) != len(fractures):
        raise RuntimeError(
            "fracture record/classification cardinality mismatch"
        )

    fracture_counts = {}

    for row in fractures:
        fracture_counts[row["plan_id"]] = (
            fracture_counts.get(row["plan_id"], 0) + 1
        )

    results = []

    for pressure in pressures:
        plan_id = pressure["plan_id"]

        if pressure.get("disposition") != "PRESSURE_ENVELOPE_SURVIVED":
            continue

        baseline = baselines.get(plan_id)
        coupling = couplings.get(plan_id)

        baseline_proven = (
            baseline is not None
            and baseline.get("disposition") == "PROVEN_BASELINE"
        )

        coupling_proven = (
            coupling is not None
            and coupling.get("disposition") == "PROVEN_COUPLING"
        )

        fracture_count = fracture_counts.get(plan_id, 0)

        if not baseline_proven:
            raise RuntimeError(
                f"survived campaign lacks proven baseline: {plan_id}"
            )

        if not coupling_proven:
            raise RuntimeError(
                f"survived campaign lacks proven coupling: {plan_id}"
            )

        if fracture_count != 0:
            raise RuntimeError(
                f"survival campaign unexpectedly has fracture records: {plan_id}"
            )

        results.append(
            CampaignClosure(
                plan_id=plan_id,
                attack_surface="load",
                disposition="LOAD_PRESSURE_ENVELOPE_PROVEN",
                highest_proven_level=pressure["highest_survived_level"],
                baseline_proven=True,
                coupling_proven=True,
                fracture_count=0,
                repair_authorized=False,
            )
        )

    return tuple(sorted(results, key=lambda item: item.plan_id))


def write_results(path, results):
    fields = [
        "plan_id",
        "attack_surface",
        "disposition",
        "highest_proven_level",
        "baseline_proven",
        "coupling_proven",
        "fracture_count",
        "repair_authorized",
    ]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "attack_surface": item.attack_surface,
                "disposition": item.disposition,
                "highest_proven_level": item.highest_proven_level,
                "baseline_proven": "true",
                "coupling_proven": "true",
                "fracture_count": item.fracture_count,
                "repair_authorized": "false",
            })
