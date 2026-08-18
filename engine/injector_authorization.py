from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class InjectorAuthorization:
    plan_id: str
    attack_surface: str
    repository_path: str
    carrier_terms: tuple[str, ...]
    carrier_line_count: int
    authorized: bool
    disposition: str
    max_trials: int


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_terms(value):
    return tuple(
        sorted({
            item.strip()
            for item in str(value).split(";")
            if item.strip()
        })
    )


def authorize(discovery_path, baseline_path, surface_path):
    discoveries = read_csv(discovery_path)
    baselines = {row["plan_id"]: row for row in read_csv(baseline_path)}
    surfaces = {
        row["attack_surface"]: row
        for row in read_csv(surface_path)
    }

    eligible = []

    for row in discoveries:
        if row.get("disposition") != "NATIVE_CARRIER_CANDIDATE":
            continue

        surface = row["attack_surface"]
        surface_state = surfaces.get(surface)
        baseline = baselines.get(row["plan_id"])

        if surface_state is None:
            continue

        if surface_state.get("readiness") != "CONTRACT_ONLY":
            continue

        if baseline is None:
            continue

        if baseline.get("disposition") != "PROVEN_BASELINE":
            continue

        terms = split_terms(row.get("carrier_terms", ""))
        lines = int(row.get("carrier_line_count", "0"))

        if len(terms) < 1:
            continue

        if lines < 1:
            continue

        eligible.append((
            surface,
            -len(terms),
            -lines,
            row["plan_id"],
            row,
            terms,
        ))

    eligible.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3],
        )
    )

    selected_surfaces = set()
    results = []

    for surface, _, _, _, row, terms in eligible:
        authorized = surface not in selected_surfaces

        disposition = "INJECTOR_PROOF_NOT_SELECTED"
        max_trials = 0

        if authorized:
            selected_surfaces.add(surface)
            disposition = "INJECTOR_PROOF_AUTHORIZED"
            max_trials = 1

        results.append(
            InjectorAuthorization(
                plan_id=row["plan_id"],
                attack_surface=surface,
                repository_path=row["repository_path"],
                carrier_terms=terms,
                carrier_line_count=int(row["carrier_line_count"]),
                authorized=authorized,
                disposition=disposition,
                max_trials=max_trials,
            )
        )

    return tuple(results)


def write_results(path, results):
    fields = [
        "plan_id",
        "attack_surface",
        "repository_path",
        "carrier_terms",
        "carrier_line_count",
        "authorized",
        "disposition",
        "max_trials",
        "trials_executed",
    ]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "attack_surface": item.attack_surface,
                "repository_path": item.repository_path,
                "carrier_terms": ";".join(item.carrier_terms),
                "carrier_line_count": item.carrier_line_count,
                "authorized": str(item.authorized).lower(),
                "disposition": item.disposition,
                "max_trials": item.max_trials,
                "trials_executed": 0,
            })
