from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib


@dataclass(frozen=True)
class FractureRecord:
    fracture_id: str
    plan_id: str
    occurrence_id: str
    content_id: str
    source_commit: str
    attack_surface: str
    fracture_level: str
    highest_survived_level: str
    baseline_proven: bool
    coupling_proven: bool
    recovery_proven: bool
    repair_authorized: bool


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fracture_identity(plan_id, source_commit, surface, level):
    material = "|".join((
        plan_id,
        source_commit,
        surface,
        level,
    )).encode("utf-8")

    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"KILN-FRACTURE-{digest}"


def build_records(
    adjudication_path,
    pressure_results_path,
    baseline_path,
    coupling_path,
    plans_path,
):
    adjudications = read_csv(adjudication_path)
    pressure_rows = read_csv(pressure_results_path)
    baselines = {row["plan_id"]: row for row in read_csv(baseline_path)}
    couplings = {row["plan_id"]: row for row in read_csv(coupling_path)}
    plans = {row["plan_id"]: row for row in read_csv(plans_path)}

    pressure_by_plan = {}

    for row in pressure_rows:
        pressure_by_plan.setdefault(row["plan_id"], []).append(row)

    records = []

    for adjudication in adjudications:
        if adjudication.get("disposition") != "PRESSURE_FRACTURE":
            continue

        plan_id = adjudication["plan_id"]
        plan = plans.get(plan_id)
        baseline = baselines.get(plan_id)
        coupling = couplings.get(plan_id)

        if plan is None or baseline is None or coupling is None:
            raise RuntimeError(
                f"incomplete fracture provenance for {plan_id}"
            )

        fracture_level = adjudication["fracture_level"]
        matching = [
            row for row in pressure_by_plan.get(plan_id, [])
            if row["pressure_level"] == fracture_level
        ]

        if len(matching) != 1:
            raise RuntimeError(
                f"expected one fracture observation for {plan_id} at {fracture_level}"
            )

        fracture_observation = matching[0]

        baseline_proven = baseline.get("result") == "PASS"
        coupling_proven = coupling.get("coupling_proven") == "true"
        recovery_proven = (
            fracture_observation.get("worktree_removed") == "true"
            and fracture_observation.get("original_head_preserved") == "true"
        )

        if not baseline_proven:
            raise RuntimeError(
                f"fracture lacks proven baseline: {plan_id}"
            )

        if not coupling_proven:
            raise RuntimeError(
                f"fracture lacks proven coupling: {plan_id}"
            )

        if not recovery_proven:
            raise RuntimeError(
                f"fracture lacks recovery proof: {plan_id}"
            )

        source_commit = baseline["source_commit"]

        records.append(
            FractureRecord(
                fracture_id=fracture_identity(
                    plan_id,
                    source_commit,
                    plan["attack_surface"],
                    fracture_level,
                ),
                plan_id=plan_id,
                occurrence_id=plan["occurrence_id"],
                content_id=plan["content_id"],
                source_commit=source_commit,
                attack_surface=plan["attack_surface"],
                fracture_level=fracture_level,
                highest_survived_level=adjudication["highest_survived_level"],
                baseline_proven=True,
                coupling_proven=True,
                recovery_proven=True,
                repair_authorized=False,
            )
        )

    return tuple(sorted(records, key=lambda item: item.fracture_id))


def write_records(path, records):
    fields = [
        "fracture_id",
        "plan_id",
        "occurrence_id",
        "content_id",
        "source_commit",
        "attack_surface",
        "fracture_level",
        "highest_survived_level",
        "baseline_proven",
        "coupling_proven",
        "recovery_proven",
        "repair_authorized",
    ]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in records:
            writer.writerow({
                "fracture_id": item.fracture_id,
                "plan_id": item.plan_id,
                "occurrence_id": item.occurrence_id,
                "content_id": item.content_id,
                "source_commit": item.source_commit,
                "attack_surface": item.attack_surface,
                "fracture_level": item.fracture_level,
                "highest_survived_level": item.highest_survived_level,
                "baseline_proven": "true",
                "coupling_proven": "true",
                "recovery_proven": "true",
                "repair_authorized": "false",
            })
