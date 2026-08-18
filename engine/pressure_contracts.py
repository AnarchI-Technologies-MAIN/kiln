from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv
import hashlib


PRESSURE_LADDERS: Dict[str, Tuple[str, ...]] = {
    "load": ("1x", "2x", "4x", "8x", "16x"),
    "state-staleness": (
        "current",
        "slightly-stale",
        "moderately-stale",
        "expired",
        "revoked",
    ),
    "authority-conflict": (
        "single-authority",
        "competing-authority",
        "stale-authority",
        "revoked-authority",
    ),
    "filesystem-state": (
        "clean",
        "missing-optional-state",
        "stale-state",
        "conflicting-state",
    ),
}


@dataclass(frozen=True)
class PressureContract:
    contract_id: str
    plan_id: str
    attack_surface: str
    pressure_levels: Tuple[str, ...]
    halt_on_first_fracture: bool
    coupling_required: bool
    execution_authorized: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def contract_identity(plan_id: str, attack_surface: str) -> str:
    material = f"{plan_id}|{attack_surface}|PRESSURE".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"KILN-PRESSURE-{digest}"


def build_contract(row: dict) -> PressureContract:
    if row.get("execution_authorized") != "true":
        raise RuntimeError(
            f"plan {row.get('plan_id')} is not execution-authorized"
        )

    surface = row.get("attack_surface", "").strip()

    if surface not in PRESSURE_LADDERS:
        raise RuntimeError(
            f"unsupported attack surface: {surface}"
        )

    return PressureContract(
        contract_id=contract_identity(row["plan_id"], surface),
        plan_id=row["plan_id"],
        attack_surface=surface,
        pressure_levels=PRESSURE_LADDERS[surface],
        halt_on_first_fracture=True,
        coupling_required=True,
        execution_authorized=False,
    )


def build_contracts(plan_path: Path) -> Tuple[PressureContract, ...]:
    rows = read_csv(plan_path)
    contracts = []

    for row in rows:
        if row.get("execution_authorized") != "true":
            continue

        contracts.append(build_contract(row))

    return tuple(
        sorted(
            contracts,
            key=lambda item: (item.plan_id, item.attack_surface),
        )
    )


def write_contracts(path: Path, contracts: Tuple[PressureContract, ...]):
    fields = [
        "contract_id",
        "plan_id",
        "attack_surface",
        "pressure_levels",
        "halt_on_first_fracture",
        "coupling_required",
        "pressure_execution_authorized",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in contracts:
            writer.writerow({
                "contract_id": item.contract_id,
                "plan_id": item.plan_id,
                "attack_surface": item.attack_surface,
                "pressure_levels": ";".join(item.pressure_levels),
                "halt_on_first_fracture": str(
                    item.halt_on_first_fracture
                ).lower(),
                "coupling_required": str(
                    item.coupling_required
                ).lower(),
                "pressure_execution_authorized": "false",
            })
