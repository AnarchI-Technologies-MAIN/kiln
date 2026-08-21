from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Tuple


@dataclass(frozen=True)
class BaselineFact:
    name: str
    value: str
    evidence_ref: str


@dataclass(frozen=True)
class BaselineSnapshot:
    target_id: str
    source_commit: str
    target_fingerprint: str
    repository_clean: bool
    facts: Tuple[BaselineFact, ...]
    snapshot_hash: str


def normalize_fact(fact: BaselineFact) -> BaselineFact:
    name = fact.name.strip()
    value = fact.value.strip()
    evidence_ref = fact.evidence_ref.strip()

    if not name:
        raise ValueError("baseline fact name is required")

    if not value:
        raise ValueError(
            f"baseline fact {name!r} requires a value"
        )

    if not evidence_ref:
        raise ValueError(
            f"baseline fact {name!r} requires evidence"
        )

    return BaselineFact(
        name=name,
        value=value,
        evidence_ref=evidence_ref,
    )


def build_snapshot(
    target,
    facts,
) -> BaselineSnapshot:
    if getattr(
        target,
        "disposition",
        "",
    ) != "TARGET_IDENTIFIED":
        raise RuntimeError(
            "baseline snapshot requires identified target"
        )

    target_id = getattr(
        target,
        "target_id",
        "",
    ).strip()

    source_commit = getattr(
        target,
        "source_commit",
        "",
    ).strip()

    target_fingerprint = getattr(
        target,
        "target_fingerprint",
        "",
    ).strip()

    if not target_id:
        raise RuntimeError(
            "baseline snapshot requires target_id"
        )

    if not source_commit:
        raise RuntimeError(
            "baseline snapshot requires source_commit"
        )

    if not target_fingerprint:
        raise RuntimeError(
            "baseline snapshot requires target_fingerprint"
        )

    normalized = tuple(
        sorted(
            (
                normalize_fact(fact)
                for fact in facts
            ),
            key=lambda fact: fact.name,
        )
    )

    if not normalized:
        raise RuntimeError(
            "baseline snapshot requires evidence-backed facts"
        )

    names = tuple(
        fact.name
        for fact in normalized
    )

    if len(names) != len(set(names)):
        raise RuntimeError(
            "baseline snapshot contains duplicate fact authority"
        )

    payload = {
        "source_commit": source_commit,
        "target_fingerprint": target_fingerprint,
        "repository_clean": bool(
            getattr(
                target,
                "repository_clean",
                False,
            )
        ),
        "facts": [
            {
                "name": fact.name,
                "value": fact.value,
                "evidence_ref": fact.evidence_ref,
            }
            for fact in normalized
        ],
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    snapshot_hash = sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return BaselineSnapshot(
        target_id=target_id,
        source_commit=source_commit,
        target_fingerprint=target_fingerprint,
        repository_clean=payload[
            "repository_clean"
        ],
        facts=normalized,
        snapshot_hash=snapshot_hash,
    )
