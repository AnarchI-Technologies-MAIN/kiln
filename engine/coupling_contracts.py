from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv
import hashlib


COUPLING_METHODS: Dict[str, str] = {
    "load": "TARGET_NATIVE_EXECUTION_COUNT_OR_CONCURRENCY",
    "state-staleness": "TARGET_NATIVE_STATE_OBSERVATION",
    "authority-conflict": "TARGET_NATIVE_AUTHORITY_OBSERVATION",
    "filesystem-state": "TARGET_NATIVE_FILESYSTEM_OBSERVATION",
}


@dataclass(frozen=True)
class CouplingContract:
    coupling_id: str
    pressure_contract_id: str
    plan_id: str
    attack_surface: str
    proof_method: str
    requires_baseline_observation: bool
    requires_pressured_observation: bool
    requires_behavioral_difference: bool
    coupling_proven: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def coupling_identity(contract_id: str, method: str) -> str:
    material = f"{contract_id}|{method}|COUPLING".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"KILN-COUPLING-{digest}"


def build_contract(row: dict) -> CouplingContract:
    if row.get("coupling_required") != "true":
        raise RuntimeError(
            f"pressure contract {row.get('contract_id')} does not require coupling"
        )

    if row.get("pressure_execution_authorized") != "false":
        raise RuntimeError(
            "Core 009 requires pressure to remain unauthorized"
        )

    surface = row.get("attack_surface", "").strip()

    if surface not in COUPLING_METHODS:
        raise RuntimeError(f"unsupported coupling surface: {surface}")

    method = COUPLING_METHODS[surface]

    return CouplingContract(
        coupling_id=coupling_identity(row["contract_id"], method),
        pressure_contract_id=row["contract_id"],
        plan_id=row["plan_id"],
        attack_surface=surface,
        proof_method=method,
        requires_baseline_observation=True,
        requires_pressured_observation=True,
        requires_behavioral_difference=True,
        coupling_proven=False,
    )


def build_contracts(path: Path) -> Tuple[CouplingContract, ...]:
    rows = read_csv(path)
    contracts = [build_contract(row) for row in rows]

    return tuple(
        sorted(
            contracts,
            key=lambda item: (item.plan_id, item.attack_surface),
        )
    )


def write_contracts(path: Path, contracts: Tuple[CouplingContract, ...]):
    fields = [
        "coupling_id",
        "pressure_contract_id",
        "plan_id",
        "attack_surface",
        "proof_method",
        "requires_baseline_observation",
        "requires_pressured_observation",
        "requires_behavioral_difference",
        "coupling_proven",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in contracts:
            writer.writerow({
                "coupling_id": item.coupling_id,
                "pressure_contract_id": item.pressure_contract_id,
                "plan_id": item.plan_id,
                "attack_surface": item.attack_surface,
                "proof_method": item.proof_method,
                "requires_baseline_observation": "true",
                "requires_pressured_observation": "true",
                "requires_behavioral_difference": "true",
                "coupling_proven": "false",
            })
