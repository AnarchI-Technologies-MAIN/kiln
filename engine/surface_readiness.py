from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


KNOWN_SURFACES = (
    "load",
    "state-staleness",
    "authority-conflict",
    "filesystem-state",
)


@dataclass(frozen=True)
class SurfaceReadiness:
    attack_surface: str
    pressure_contract_count: int
    coupled_contract_count: int
    proven_campaign_count: int
    readiness: str
    injector_discovery_authorized: bool


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def reconcile(campaign_path, pressure_path, coupling_path):
    campaigns = read_csv(campaign_path)
    pressures = read_csv(pressure_path)
    couplings = read_csv(coupling_path)

    pressure_by_id = {
        row["contract_id"]: row
        for row in pressures
    }

    coupled_pressure_ids = {
        row["pressure_contract_id"]
        for row in couplings
        if row.get("pressure_contract_id")
    }

    unknown_coupling_refs = sorted(
        pressure_id
        for pressure_id in coupled_pressure_ids
        if pressure_id not in pressure_by_id
    )

    if unknown_coupling_refs:
        raise RuntimeError(
            "coupling contracts reference unknown pressure contracts: "
            + ",".join(unknown_coupling_refs)
        )

    results = []

    for surface in KNOWN_SURFACES:
        surface_pressures = [
            row for row in pressures
            if row.get("attack_surface") == surface
        ]

        coupled_surface_pressures = [
            row for row in surface_pressures
            if row["contract_id"] in coupled_pressure_ids
        ]

        proven_campaigns = [
            row for row in campaigns
            if row.get("attack_surface") == surface
            and row.get("disposition") == "LOAD_PRESSURE_ENVELOPE_PROVEN"
        ]

        readiness = "UNSUPPORTED"
        discovery_authorized = False

        if proven_campaigns:
            readiness = "PROVEN"

        if (
            not proven_campaigns
            and surface_pressures
            and coupled_surface_pressures
        ):
            readiness = "CONTRACT_ONLY"
            discovery_authorized = True

        results.append(
            SurfaceReadiness(
                attack_surface=surface,
                pressure_contract_count=len(surface_pressures),
                coupled_contract_count=len(coupled_surface_pressures),
                proven_campaign_count=len(proven_campaigns),
                readiness=readiness,
                injector_discovery_authorized=discovery_authorized,
            )
        )

    return tuple(results)


def write_results(path, results):
    fields = [
        "attack_surface",
        "pressure_contract_count",
        "coupled_contract_count",
        "proven_campaign_count",
        "readiness",
        "injector_discovery_authorized",
    ]

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "attack_surface": item.attack_surface,
                "pressure_contract_count": item.pressure_contract_count,
                "coupled_contract_count": item.coupled_contract_count,
                "proven_campaign_count": item.proven_campaign_count,
                "readiness": item.readiness,
                "injector_discovery_authorized": str(
                    item.injector_discovery_authorized
                ).lower(),
            })
