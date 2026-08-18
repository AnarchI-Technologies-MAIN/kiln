from pathlib import Path
import csv
import tempfile
import unittest

from engine.annotations import (
    AttackSurfaceClaim,
    InvalidKilnAnnotation,
    KilnAnnotationRecord,
    KilnConfidence,
    KilnEligibility,
    KilnEligibilityIndex,
)
from engine.library_index import KilnLibraryIndex
from engine.state_machine import KilnState


class KilnAnnotationTests(unittest.TestCase):
    def _write_occurrences(self, root):
        registry = root / "registry"
        registry.mkdir(parents=True, exist_ok=True)

        path = registry / "test-occurrence-registry-001.csv"

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "occurrence_id",
                    "content_id",
                    "repository_root",
                    "repository_path",
                    "absolute_path",
                    "language",
                ],
            )

            writer.writeheader()
            writer.writerow(
                {
                    "occurrence_id": "OCC-001",
                    "content_id": "CONTENT-001",
                    "repository_root": "C:/repo",
                    "repository_path": "tests/test_one.py",
                    "absolute_path": "C:/repo/tests/test_one.py",
                    "language": "python",
                }
            )

    def _index(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        self._write_occurrences(root)
        shared = KilnLibraryIndex(root).load()
        return temp, KilnEligibilityIndex(shared)

    def test_unknown_shared_identity_is_rejected(self):
        temp, index = self._index()

        try:
            with self.assertRaises(InvalidKilnAnnotation):
                index.put(
                    KilnAnnotationRecord(
                        occurrence_id="OCC-UNKNOWN",
                        content_id="CONTENT-UNKNOWN",
                        eligibility=KilnEligibility.ELIGIBLE,
                        confidence=KilnConfidence.HIGH,
                    )
                )
        finally:
            temp.cleanup()

    def test_content_identity_mismatch_is_rejected(self):
        temp, index = self._index()

        try:
            with self.assertRaises(InvalidKilnAnnotation):
                index.put(
                    KilnAnnotationRecord(
                        occurrence_id="OCC-001",
                        content_id="WRONG",
                        eligibility=KilnEligibility.ELIGIBLE,
                        confidence=KilnConfidence.HIGH,
                    )
                )
        finally:
            temp.cleanup()

    def test_attack_surface_requires_evidence(self):
        with self.assertRaises(InvalidKilnAnnotation):
            AttackSurfaceClaim(
                name="authority-conflict",
                evidence_refs=tuple(),
                confidence=KilnConfidence.HIGH,
            )

    def test_duplicate_identical_annotation_is_idempotent(self):
        temp, index = self._index()

        try:
            record = KilnAnnotationRecord(
                occurrence_id="OCC-001",
                content_id="CONTENT-001",
                eligibility=KilnEligibility.ELIGIBLE,
                confidence=KilnConfidence.HIGH,
                attack_surfaces=(
                    AttackSurfaceClaim(
                        name="authority-conflict",
                        evidence_refs=("E-001",),
                        confidence=KilnConfidence.HIGH,
                    ),
                ),
                evidence_refs=("E-001",),
                last_state=KilnState.PROVEN,
            )

            first = index.put(record)
            second = index.put(record)

            self.assertIs(first, second)
            self.assertEqual(len(index), 1)
        finally:
            temp.cleanup()

    def test_conflicting_duplicate_is_rejected(self):
        temp, index = self._index()

        try:
            index.put(
                KilnAnnotationRecord(
                    occurrence_id="OCC-001",
                    content_id="CONTENT-001",
                    eligibility=KilnEligibility.UNADJUDICATED,
                    confidence=KilnConfidence.NONE,
                )
            )

            with self.assertRaises(InvalidKilnAnnotation):
                index.put(
                    KilnAnnotationRecord(
                        occurrence_id="OCC-001",
                        content_id="CONTENT-001",
                        eligibility=KilnEligibility.ELIGIBLE,
                        confidence=KilnConfidence.HIGH,
                    )
                )
        finally:
            temp.cleanup()

    def test_seed_is_conservative_and_deterministic(self):
        temp, index = self._index()

        try:
            added = index.seed_unadjudicated()
            added_again = index.seed_unadjudicated()

            self.assertEqual(added, 1)
            self.assertEqual(added_again, 0)

            record = index.get("OCC-001")

            self.assertEqual(
                record.eligibility,
                KilnEligibility.UNADJUDICATED,
            )
            self.assertEqual(record.attack_surfaces, tuple())
            self.assertEqual(record.last_state, KilnState.DISCOVERED)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
