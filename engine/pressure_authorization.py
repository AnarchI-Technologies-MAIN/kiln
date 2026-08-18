from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv


@dataclass(frozen=True)
class PressureAuthorization:
    plan_id: str
    contract_id: str
    attack_surface: str
    authorized: bool
    disposition: str
    max_levels: int


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def authorize(baseline_path, coupling_path, pressure_path):
    baselines = {row["plan_id"]: row for row in read_csv(baseline_path)}
    couplings = {row["plan_id"]: row for row in read_csv(coupling_path)}
    pressures = read_csv(pressure_path)

    results = []

    for pressure in pressures:
        plan_id = pressure["plan_id"]
        baseline = baselines.get(plan_id)
        coupling = couplings.get(plan_id)

        baseline_ok = (
            baseline is not None
            and baseline.get("disposition") == "PROVEN_BASELINE"
            and baseline.get("pressure_eligible") == "true"
        )

        coupling_ok = (
            coupling is not None
            and coupling.get("disposition") == "PROVEN_COUPLING"
            and coupling.get("pressure_eligible") == "true"
        )

        levels = [
            item for item in pressure.get("pressure_levels", "").split(";")
            if item
        ]

        bounded = bool(levels) and len(levels) <= 16
        halt = pressure.get("halt_on_first_fracture") == "true"

        authorized = all((baseline_ok, coupling_ok, bounded, halt))

        disposition = "PRESSURE_AUTHORIZED"

        if not authorized:
            disposition = "PRESSURE_BLOCKED"

        results.append(
            PressureAuthorization(
                plan_id=plan_id,
                contract_id=pressure["contract_id"],
                attack_surface=pressure["attack_surface"],
                authorized=authorized,
                disposition=disposition,
                max_levels=len(levels) if authorized else 0,
            )
        )

    return tuple(sorted(results, key=lambda item: item.plan_id))


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "contract_id",
        "attack_surface",
        "authorized",
        "disposition",
        "max_levels",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "contract_id": item.contract_id,
                "attack_surface": item.attack_surface,
                "authorized": str(item.authorized).lower(),
                "disposition": item.disposition,
                "max_levels": item.max_levels,
            })
