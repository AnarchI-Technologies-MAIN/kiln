from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv


@dataclass(frozen=True)
class DryRunResult:
    plan_id: str
    pressure_contract_id: str
    coupling_id: str
    attack_surface: str
    recovery_mode: str
    dry_run_result: str
    live_execution_authorized: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def execute_dry_run(
    plans_path: Path,
    pressure_path: Path,
    coupling_path: Path,
) -> Tuple[DryRunResult, ...]:
    plans = read_csv(plans_path)
    pressures = read_csv(pressure_path)
    couplings = read_csv(coupling_path)

    pressure_by_plan: Dict[str, dict] = {}

    for row in pressures:
        plan_id = row["plan_id"]

        if plan_id in pressure_by_plan:
            raise RuntimeError(
                f"multiple pressure contracts for plan {plan_id}"
            )

        pressure_by_plan[plan_id] = row

    coupling_by_pressure: Dict[str, dict] = {}

    for row in couplings:
        pressure_id = row["pressure_contract_id"]

        if pressure_id in coupling_by_pressure:
            raise RuntimeError(
                f"multiple coupling contracts for pressure {pressure_id}"
            )

        coupling_by_pressure[pressure_id] = row

    results = []

    for plan in plans:
        if plan.get("execution_authorized") != "true":
            continue

        plan_id = plan["plan_id"]
        pressure = pressure_by_plan.get(plan_id)

        if pressure is None:
            raise RuntimeError(
                f"authorized plan {plan_id} lacks pressure contract"
            )

        coupling = coupling_by_pressure.get(pressure["contract_id"])

        if coupling is None:
            raise RuntimeError(
                f"pressure {pressure['contract_id']} lacks coupling contract"
            )

        if pressure.get("pressure_execution_authorized") != "false":
            raise RuntimeError(
                f"dry run found prematurely authorized pressure {pressure['contract_id']}"
            )

        if coupling.get("coupling_proven") != "false":
            raise RuntimeError(
                f"dry run found unearned coupling proof {coupling['coupling_id']}"
            )

        if pressure["attack_surface"] != plan["attack_surface"]:
            raise RuntimeError(
                f"plan/pressure attack-surface mismatch for {plan_id}"
            )

        if coupling["attack_surface"] != plan["attack_surface"]:
            raise RuntimeError(
                f"plan/coupling attack-surface mismatch for {plan_id}"
            )

        results.append(
            DryRunResult(
                plan_id=plan_id,
                pressure_contract_id=pressure["contract_id"],
                coupling_id=coupling["coupling_id"],
                attack_surface=plan["attack_surface"],
                recovery_mode=plan["recovery_mode"],
                dry_run_result="READY_FOR_LIVE_PREFLIGHT",
                live_execution_authorized=False,
            )
        )

    return tuple(
        sorted(results, key=lambda item: item.plan_id)
    )


def write_results(path: Path, results: Tuple[DryRunResult, ...]):
    fields = [
        "plan_id",
        "pressure_contract_id",
        "coupling_id",
        "attack_surface",
        "recovery_mode",
        "dry_run_result",
        "live_execution_authorized",
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
                "recovery_mode": item.recovery_mode,
                "dry_run_result": item.dry_run_result,
                "live_execution_authorized": "false",
            })
