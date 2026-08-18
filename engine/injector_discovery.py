from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re


SURFACE_TERMS = {
    "state-staleness": (
        "stale",
        "expired",
        "expiry",
        "ttl",
        "timestamp",
        "updated_at",
        "version",
    ),
    "authority-conflict": (
        "authority",
        "owner",
        "permission",
        "role",
        "token",
        "authorized",
        "revoked",
    ),
    "filesystem-state": (
        "path",
        "file",
        "directory",
        "exists",
        "missing",
        "temp",
        "cache",
    ),
}


@dataclass(frozen=True)
class InjectorDiscovery:
    plan_id: str
    attack_surface: str
    repository_path: str
    carrier_terms: tuple[str, ...]
    carrier_line_count: int
    disposition: str
    injector_proof_authorized: bool


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def term_pattern(term: str):
    return re.compile(
        r"(?<![A-Za-z0-9])"
        + re.escape(term.lower())
        + r"(?![A-Za-z0-9])"
    )


def discover_file(path: Path, terms):
    if not path.is_file():
        return tuple(), 0

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return tuple(), 0

    patterns = {
        term: term_pattern(term)
        for term in terms
    }

    matched_terms = set()
    matched_lines = 0

    for line in text.splitlines():
        normalized = line.lower()
        line_hit = False

        for term, pattern in patterns.items():
            if pattern.search(normalized):
                matched_terms.add(term)
                line_hit = True

        if line_hit:
            matched_lines += 1

    return tuple(sorted(matched_terms)), matched_lines


def discover(surface_path, plan_path):
    surfaces = read_csv(surface_path)
    plans = read_csv(plan_path)

    discovery_surfaces = {
        row["attack_surface"]
        for row in surfaces
        if row.get("injector_discovery_authorized") == "true"
    }

    results = []

    for plan in plans:
        surface = plan.get("attack_surface", "")

        if surface not in discovery_surfaces:
            continue

        terms = SURFACE_TERMS.get(surface)

        if not terms:
            continue

        repo = Path(plan["repository_root"])
        target = repo / plan["repository_path"]

        matched_terms, matched_lines = discover_file(target, terms)

        disposition = "NO_NATIVE_CARRIER_FOUND"

        if matched_terms:
            disposition = "NATIVE_CARRIER_CANDIDATE"

        results.append(
            InjectorDiscovery(
                plan_id=plan["plan_id"],
                attack_surface=surface,
                repository_path=plan["repository_path"],
                carrier_terms=matched_terms,
                carrier_line_count=matched_lines,
                disposition=disposition,
                injector_proof_authorized=False,
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.attack_surface,
                -item.carrier_line_count,
                item.plan_id,
            ),
        )
    )


def write_results(path, results):
    fields = [
        "plan_id",
        "attack_surface",
        "repository_path",
        "carrier_terms",
        "carrier_line_count",
        "disposition",
        "injector_proof_authorized",
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
                "disposition": item.disposition,
                "injector_proof_authorized": "false",
            })
