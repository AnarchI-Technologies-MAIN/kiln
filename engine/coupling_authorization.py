from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv


@dataclass(frozen=True)
class CouplingAuthorization:
    plan_id: str
    pressure_contract_id: str
    coupling_id: str
    attack_surface: str
    authorized: bool
    disposition: str
    max_trials: int


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def authorize_trials(
    baseline_path: Path,
    pressure_path: Path,
    coupling_path: Path,
) -> Tuple[CouplingAuthorization, ...]:
    baselines = read_csv(baseline_path)
    pressures = read_csv(pressure_path)
    couplings = read_csv(coupling_path)

    baseline_by_plan = {row["plan_id"]: row for row in baselines}
    pressure_by_plan = {row["plan_id"]: row for row in pressures}
    coupling_by_pressure = {
        row["pressure_contract_id"]: row
        for row in couplings
    }

    results = []

    for plan_id in sorted(pressure_by_plan):
        pressure = pressure_by_plan[plan_id]
        baseline = baseline_by_plan.get(plan_id)

        if baseline is None:
            continue

        coupling = coupling_by_pressure.get(pressure["contract_id"])

        if coupling is None:
            raise RuntimeError(
                f"pressure contract {pressure['contract_id']} lacks coupling contract"
            )

        proven = baseline.get("disposition") == "PROVEN_BASELINE"
        pressure_eligible = baseline.get("pressure_eligible") == "true"
        coupling_unproven = coupling.get("coupling_proven") == "false"
        pressure_unexecuted = (
            pressure.get("pressure_execution_authorized") == "false"
        )

        executor_supported = pressure.get("attack_surface") == "load"

        authorized = all((
            proven,
            pressure_eligible,
            coupling_unproven,
            pressure_unexecuted,
            executor_supported,
        ))

        disposition = "COUPLING_TRIAL_AUTHORIZED"

        if not authorized:
            disposition = "COUPLING_TRIAL_BLOCKED"

        results.append(
            CouplingAuthorization(
                plan_id=plan_id,
                pressure_contract_id=pressure["contract_id"],
                coupling_id=coupling["coupling_id"],
                attack_surface=pressure["attack_surface"],
                authorized=authorized,
                disposition=disposition,
                max_trials=1 if authorized else 0,
            )
        )

    return tuple(results)


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "pressure_contract_id",
        "coupling_id",
        "attack_surface",
        "authorized",
        "disposition",
        "max_trials",
        "trials_executed",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "pressure_contract_id": item.pressure_contract_id,
                "coupling_id": item.coupling_id,
                "attack_surface": item.attack_surface,
                "authorized": str(item.authorized).lower(),
                "disposition": item.disposition,
                "max_trials": item.max_trials,
                "trials_executed": 0,
            })
