from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple
import csv

from .library_index import KilnLibraryIndex
from .state_machine import KilnState


class KilnEligibility(str, Enum):
    UNADJUDICATED = "UNADJUDICATED"
    ELIGIBLE = "ELIGIBLE"
    REQUIRES_ISOLATION = "REQUIRES_ISOLATION"
    REQUIRES_SANDBOX = "REQUIRES_SANDBOX"
    RUNNER_BLOCKED = "RUNNER_BLOCKED"
    SUPPORT_ONLY = "SUPPORT_ONLY"
    BLOCKED = "BLOCKED"


class KilnConfidence(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class InvalidKilnAnnotation(ValueError):
    pass


@dataclass(frozen=True)
class AttackSurfaceClaim:
    name: str
    evidence_refs: Tuple[str, ...]
    confidence: KilnConfidence

    def __post_init__(self) -> None:
        normalized = self.name.strip()

        if not normalized:
            raise InvalidKilnAnnotation("attack surface name is required")

        if not self.evidence_refs:
            raise InvalidKilnAnnotation(
                f"attack surface {normalized!r} requires evidence"
            )

        for ref in self.evidence_refs:
            if not str(ref).strip():
                raise InvalidKilnAnnotation(
                    f"attack surface {normalized!r} contains empty evidence reference"
                )


@dataclass(frozen=True)
class KilnAnnotationRecord:
    occurrence_id: str
    content_id: str
    eligibility: KilnEligibility
    confidence: KilnConfidence
    attack_surfaces: Tuple[AttackSurfaceClaim, ...] = field(default_factory=tuple)
    recovery_requirement: str = ""
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    last_state: KilnState = KilnState.DISCOVERED

    def __post_init__(self) -> None:
        if not self.occurrence_id.strip():
            raise InvalidKilnAnnotation("occurrence_id is required")

        if not self.content_id.strip():
            raise InvalidKilnAnnotation("content_id is required")

        surface_names = [surface.name for surface in self.attack_surfaces]

        if len(surface_names) != len(set(surface_names)):
            raise InvalidKilnAnnotation(
                f"duplicate attack-surface claim for {self.occurrence_id}"
            )


class KilnEligibilityIndex:
    """Kiln-owned annotations keyed by shared Test Library identities.

    The Test Library remains authoritative for occurrence/content identity.
    Kiln owns only the annotations stored here.
    """

    def __init__(self, library_index: KilnLibraryIndex) -> None:
        self.library_index = library_index
        self._records: Dict[str, KilnAnnotationRecord] = {}

    def _validate_shared_identity(
        self,
        occurrence_id: str,
        content_id: str,
    ) -> None:
        shared = self.library_index.get(occurrence_id)

        if shared is None:
            raise InvalidKilnAnnotation(
                f"unknown shared Test Library occurrence: {occurrence_id}"
            )

        if shared.content_id != content_id:
            raise InvalidKilnAnnotation(
                "content identity mismatch for "
                f"{occurrence_id}: shared={shared.content_id!r}, annotation={content_id!r}"
            )

    def put(self, record: KilnAnnotationRecord) -> KilnAnnotationRecord:
        self._validate_shared_identity(
            record.occurrence_id,
            record.content_id,
        )

        existing = self._records.get(record.occurrence_id)

        if existing is not None and existing == record:
            return existing

        if existing is not None and existing != record:
            raise InvalidKilnAnnotation(
                "conflicting duplicate annotation for "
                f"{record.occurrence_id}"
            )

        self._records[record.occurrence_id] = record
        return record

    def get(self, occurrence_id: str) -> Optional[KilnAnnotationRecord]:
        return self._records.get(occurrence_id)

    def all(self) -> Tuple[KilnAnnotationRecord, ...]:
        return tuple(
            self._records[key]
            for key in sorted(self._records)
        )

    def seed_unadjudicated(self) -> int:
        added = 0

        for shared in self.library_index.all():
            if shared.occurrence_id in self._records:
                continue

            self.put(
                KilnAnnotationRecord(
                    occurrence_id=shared.occurrence_id,
                    content_id=shared.content_id,
                    eligibility=KilnEligibility.UNADJUDICATED,
                    confidence=KilnConfidence.NONE,
                    attack_surfaces=tuple(),
                    recovery_requirement="",
                    evidence_refs=tuple(),
                    last_state=KilnState.DISCOVERED,
                )
            )

            added += 1

        return added

    def eligible(self) -> Tuple[KilnAnnotationRecord, ...]:
        allowed = {
            KilnEligibility.ELIGIBLE,
            KilnEligibility.REQUIRES_ISOLATION,
            KilnEligibility.REQUIRES_SANDBOX,
        }

        return tuple(
            record
            for record in self.all()
            if record.eligibility in allowed
        )

    def with_attack_surface(self, name: str) -> Tuple[KilnAnnotationRecord, ...]:
        return tuple(
            record
            for record in self.all()
            if any(surface.name == name for surface in record.attack_surfaces)
        )

    def write_csv(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fields = [
            "occurrence_id",
            "content_id",
            "eligibility",
            "confidence",
            "attack_surfaces",
            "attack_surface_evidence",
            "recovery_requirement",
            "evidence_refs",
            "last_state",
        ]

        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()

            for record in self.all():
                writer.writerow(
                    {
                        "occurrence_id": record.occurrence_id,
                        "content_id": record.content_id,
                        "eligibility": record.eligibility.value,
                        "confidence": record.confidence.value,
                        "attack_surfaces": ";".join(
                            surface.name for surface in record.attack_surfaces
                        ),
                        "attack_surface_evidence": ";".join(
                            f"{surface.name}:" + ",".join(surface.evidence_refs)
                            for surface in record.attack_surfaces
                        ),
                        "recovery_requirement": record.recovery_requirement,
                        "evidence_refs": ";".join(record.evidence_refs),
                        "last_state": record.last_state.value,
                    }
                )

    def __len__(self) -> int:
        return len(self._records)
