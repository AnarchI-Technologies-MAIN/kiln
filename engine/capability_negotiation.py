from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple
import csv


@dataclass(frozen=True)
class CapabilityNegotiation:
    attack_surface: str
    readiness: str
    execution_authorized: bool
    injector_available: bool
    injector_authorized: bool
    max_injector_trials: int
    disposition: str
    authorized_actions: Tuple[str, ...]
    blocked_actions: Tuple[str, ...]


def read_csv(path: Path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def negotiate(
    execution_path: Path,
    plan_path: Path,
    surface_path: Path,
    injector_path: Path,
):
    execution = read_csv(execution_path)
    plans = read_csv(plan_path)
    surfaces = read_csv(surface_path)
    injectors = read_csv(injector_path)

    surface_by_plan = {
        row["plan_id"]: row["attack_surface"]
        for row in plans
        if row.get("plan_id", "").strip()
        and row.get("attack_surface", "").strip()
    }

    authorized_surfaces = {
        surface_by_plan[row["plan_id"]]
        for row in execution
        if row.get("authorized") == "true"
        and row.get("plan_id") in surface_by_plan
    }

    injectors_by_surface = {}

    for row in injectors:
        surface = row.get("attack_surface", "").strip()
        if not surface:
            continue
        injectors_by_surface.setdefault(surface, []).append(row)

    results = []

    for surface in surfaces:
        attack_surface = surface["attack_surface"]
        execution_authorized = attack_surface in authorized_surfaces
        readiness = surface["readiness"]

        injector_rows = injectors_by_surface.get(
            attack_surface,
            [],
        )

        injector_available = len(injector_rows) > 0

        authorized_rows = [
            row
            for row in injector_rows
            if row.get("authorized") == "true"
        ]

        injector_authorized = len(authorized_rows) > 0

        max_trials = sum(
            int(row.get("max_trials", "0"))
            for row in authorized_rows
        )

        authorized_actions = []
        blocked_actions = []

        if execution_authorized:
            authorized_actions.append(
                "BASELINE_EXECUTION"
            )
        else:
            blocked_actions.append(
                "BASELINE_EXECUTION"
            )

        if readiness == "PROVEN":
            authorized_actions.append(
                "PRESSURE_EVIDENCE_ACCEPTED"
            )
        else:
            blocked_actions.append(
                "PRESSURE_EVIDENCE_ACCEPTED"
            )

        if injector_authorized:
            authorized_actions.append(
                "INJECTOR_PROOF_TRIAL"
            )
        else:
            blocked_actions.append(
                "INJECTOR_PROOF_TRIAL"
            )

        if injector_authorized:
            disposition = "CAPABILITY_PROVEN"
        elif injector_available:
            disposition = "CAPABILITY_PARTIAL"
        elif readiness == "PROVEN":
            disposition = "CAPABILITY_PROVEN"
        else:
            disposition = "CAPABILITY_BLOCKED"

        results.append(
            CapabilityNegotiation(
                attack_surface=attack_surface,
                readiness=readiness,
                execution_authorized=execution_authorized,
                injector_available=injector_available,
                injector_authorized=injector_authorized,
                max_injector_trials=max_trials,
                disposition=disposition,
                authorized_actions=tuple(
                    sorted(authorized_actions)
                ),
                blocked_actions=tuple(
                    sorted(blocked_actions)
                ),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda item: item.attack_surface,
        )
    )


def write_results(path: Path, results):
    fields = [
        "attack_surface",
        "readiness",
        "execution_authorized",
        "injector_available",
        "injector_authorized",
        "max_injector_trials",
        "disposition",
        "authorized_actions",
        "blocked_actions",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for item in results:
            writer.writerow({
                "attack_surface": item.attack_surface,
                "readiness": item.readiness,
                "execution_authorized": str(
                    item.execution_authorized
                ).lower(),
                "injector_available": str(
                    item.injector_available
                ).lower(),
                "injector_authorized": str(
                    item.injector_authorized
                ).lower(),
                "max_injector_trials": item.max_injector_trials,
                "disposition": item.disposition,
                "authorized_actions": ";".join(
                    item.authorized_actions
                ),
                "blocked_actions": ";".join(
                    item.blocked_actions
                ),
            })
