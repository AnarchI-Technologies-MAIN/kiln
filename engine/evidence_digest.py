from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Tuple


@dataclass(frozen=True)
class EvidenceField:
    name: str
    value: str


@dataclass(frozen=True)
class EvidenceDigest:
    raw_evidence_hash: str
    fields: Tuple[EvidenceField, ...]
    evidence_digest: str


def normalize_field(field: EvidenceField) -> EvidenceField:
    name = field.name.strip()
    value = field.value.strip()

    if not name:
        raise ValueError(
            "evidence field name is required"
        )

    if not value:
        raise ValueError(
            f"evidence field {name!r} requires a value"
        )

    return EvidenceField(
        name=name,
        value=value,
    )


def build_evidence_digest(
    raw_evidence: bytes,
    fields,
) -> EvidenceDigest:
    if not isinstance(
        raw_evidence,
        bytes,
    ):
        raise TypeError(
            "raw evidence must be bytes"
        )

    normalized = tuple(
        sorted(
            (
                normalize_field(field)
                for field in fields
            ),
            key=lambda field: field.name,
        )
    )

    if not normalized:
        raise RuntimeError(
            "semantic evidence requires fields"
        )

    names = tuple(
        field.name
        for field in normalized
    )

    if len(names) != len(set(names)):
        raise RuntimeError(
            "semantic evidence contains duplicate field authority"
        )

    raw_evidence_hash = sha256(
        raw_evidence
    ).hexdigest()

    payload = {
        "fields": [
            {
                "name": field.name,
                "value": field.value,
            }
            for field in normalized
        ],
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    evidence_digest = sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return EvidenceDigest(
        raw_evidence_hash=raw_evidence_hash,
        fields=normalized,
        evidence_digest=evidence_digest,
    )