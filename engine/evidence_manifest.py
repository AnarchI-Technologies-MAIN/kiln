from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv
import json


@dataclass(frozen=True)
class EvidenceManifest:
    target_id: str
    source_commit: str
    target_fingerprint: str
    capability_evidence_hash: str
    injector_evidence_hash: str
    surface_evidence_hash: str
    authorized_actions: Tuple[str, ...]
    blocked_actions: Tuple[str, ...]
    final_disposition: str
    manifest_hash: str


def file_hash(path: Path) -> str:
    return sha256(
        Path(path).read_bytes()
    ).hexdigest()


def read_csv(path: Path):
    with Path(path).open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def split_actions(value: str):
    return tuple(
        item
        for item in str(value).split(";")
        if item
    )


def build_manifest(
    target,
    capability_path: Path,
    injector_path: Path,
    surface_path: Path,
):
    required = (
        Path(capability_path),
        Path(injector_path),
        Path(surface_path),
    )

    if any(
        not path.exists()
        for path in required
    ):
        raise RuntimeError(
            "required provenance evidence is missing"
        )

    capabilities = read_csv(
        capability_path
    )

    injectors = read_csv(
        injector_path
    )

    surfaces = read_csv(
        surface_path
    )

    if not capabilities:
        raise RuntimeError(
            "capability evidence is empty"
        )

    if not surfaces:
        raise RuntimeError(
            "surface evidence is empty"
        )

    authorized = set()
    blocked = set()

    for row in capabilities:
        authorized.update(
            split_actions(
                row.get(
                    "authorized_actions",
                    "",
                )
            )
        )

        blocked.update(
            split_actions(
                row.get(
                    "blocked_actions",
                    "",
                )
            )
        )

    authorized.difference_update(
        blocked
    )

    disposition = "EVIDENCE_CLOSED"

    if getattr(
        target,
        "disposition",
        "",
    ) != "TARGET_IDENTIFIED":
        disposition = "EVIDENCE_INCOMPLETE"

    payload = {
        "target_id": getattr(
            target,
            "target_id",
            "",
        ),
        "source_commit": getattr(
            target,
            "source_commit",
            "",
        ),
        "target_fingerprint": getattr(
            target,
            "target_fingerprint",
            "",
        ),
        "capability_evidence_hash": file_hash(
            capability_path
        ),
        "injector_evidence_hash": file_hash(
            injector_path
        ),
        "surface_evidence_hash": file_hash(
            surface_path
        ),
        "authorized_actions": sorted(
            authorized
        ),
        "blocked_actions": sorted(
            blocked
        ),
        "injector_rows": len(
            injectors
        ),
        "surface_rows": len(
            surfaces
        ),
        "final_disposition": disposition,
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    manifest_hash = sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return EvidenceManifest(
        target_id=payload["target_id"],
        source_commit=payload["source_commit"],
        target_fingerprint=payload[
            "target_fingerprint"
        ],
        capability_evidence_hash=payload[
            "capability_evidence_hash"
        ],
        injector_evidence_hash=payload[
            "injector_evidence_hash"
        ],
        surface_evidence_hash=payload[
            "surface_evidence_hash"
        ],
        authorized_actions=tuple(
            payload["authorized_actions"]
        ),
        blocked_actions=tuple(
            payload["blocked_actions"]
        ),
        final_disposition=disposition,
        manifest_hash=manifest_hash,
    )


def write_results(path: Path, results):
    fields = [
        "target_id",
        "source_commit",
        "target_fingerprint",
        "capability_evidence_hash",
        "injector_evidence_hash",
        "surface_evidence_hash",
        "authorized_actions",
        "blocked_actions",
        "final_disposition",
        "manifest_hash",
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
                "target_id": item.target_id,
                "source_commit": item.source_commit,
                "target_fingerprint": item.target_fingerprint,
                "capability_evidence_hash": item.capability_evidence_hash,
                "injector_evidence_hash": item.injector_evidence_hash,
                "surface_evidence_hash": item.surface_evidence_hash,
                "authorized_actions": ";".join(item.authorized_actions),
                "blocked_actions": ";".join(item.blocked_actions),
                "final_disposition": item.final_disposition,
                "manifest_hash": item.manifest_hash,
            })
