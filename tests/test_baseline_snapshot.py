import unittest

from engine.baseline_snapshot import (
    BaselineFact,
    build_snapshot,
)
from engine.evidence_digest import (
    EvidenceField,
    build_evidence_digest,
)
from engine.target_intake import TargetIdentity


class BaselineSnapshotTests(unittest.TestCase):
    def target(self):
        return TargetIdentity(
            target_id="KILN-TARGET-BASELINE",
            target_kind="LOCAL_GIT_REPOSITORY",
            source_location="fixture",
            repository_root="fixture",
            git_repository=True,
            source_commit="abc123",
            repository_clean=True,
            local_or_remote="LOCAL",
            language_hints=("python",),
            manifest_hints=("pyproject.toml",),
            target_fingerprint="fingerprint",
            disposition="TARGET_IDENTIFIED",
        )

    def facts(self):
        return (
            BaselineFact(
                name="runtime.python.version",
                value="3.12.10",
                evidence_ref="E-RUNTIME-001",
            ),
            BaselineFact(
                name="tests.canonical.result",
                value="PASS",
                evidence_ref="E-TEST-001",
            ),
        )

    def test_snapshot_is_deterministic_and_order_independent(self):
        facts = self.facts()

        first = build_snapshot(
            self.target(),
            facts,
        )

        second = build_snapshot(
            self.target(),
            tuple(reversed(facts)),
        )

        self.assertEqual(
            first.snapshot_hash,
            second.snapshot_hash,
        )

        self.assertEqual(
            tuple(
                fact.name
                for fact in first.facts
            ),
            (
                "runtime.python.version",
                "tests.canonical.result",
            ),
        )

    def test_fact_change_changes_snapshot_hash(self):
        first = build_snapshot(
            self.target(),
            self.facts(),
        )

        second = build_snapshot(
            self.target(),
            (
                BaselineFact(
                    name="runtime.python.version",
                    value="3.12.11",
                    evidence_ref="E-RUNTIME-002",
                ),
                self.facts()[1],
            ),
        )

        self.assertNotEqual(
            first.snapshot_hash,
            second.snapshot_hash,
        )

    def test_missing_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            build_snapshot(
                self.target(),
                (
                    BaselineFact(
                        name="tests.canonical.result",
                        value="PASS",
                        evidence_ref="",
                    ),
                ),
            )

    def test_duplicate_fact_authority_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build_snapshot(
                self.target(),
                (
                    BaselineFact(
                        name="tests.canonical.result",
                        value="PASS",
                        evidence_ref="E-TEST-001",
                    ),
                    BaselineFact(
                        name="tests.canonical.result",
                        value="FAIL",
                        evidence_ref="E-TEST-002",
                    ),
                ),
            )

    def test_unidentified_target_cannot_be_frozen(self):
        target = TargetIdentity(
            target_id="",
            target_kind="MISSING",
            source_location="fixture",
            repository_root="",
            git_repository=False,
            source_commit="",
            repository_clean=False,
            local_or_remote="LOCAL",
            language_hints=tuple(),
            manifest_hints=tuple(),
            target_fingerprint="",
            disposition="TARGET_NOT_FOUND",
        )

        with self.assertRaises(RuntimeError):
            build_snapshot(
                target,
                self.facts(),
            )


    def test_evidence_reference_change_changes_snapshot_hash(self):
        first = build_snapshot(
            self.target(),
            self.facts(),
        )

        second = build_snapshot(
            self.target(),
            (
                BaselineFact(
                    name="runtime.python.version",
                    value="3.12.10",
                    evidence_ref="E-RUNTIME-CHANGED",
                ),
                self.facts()[1],
            ),
        )

        self.assertNotEqual(
            first.snapshot_hash,
            second.snapshot_hash,
        )

    def test_duplicate_names_after_normalization_fail_closed(self):
        with self.assertRaises(RuntimeError):
            build_snapshot(
                self.target(),
                (
                    BaselineFact(
                        name=" tests.canonical.result ",
                        value="PASS",
                        evidence_ref="E-TEST-001",
                    ),
                    BaselineFact(
                        name="tests.canonical.result",
                        value="FAIL",
                        evidence_ref="E-TEST-002",
                    ),
                ),
            )

    def test_repository_clean_state_is_bound_into_snapshot(self):
        clean = build_snapshot(
            self.target(),
            self.facts(),
        )

        dirty_target = TargetIdentity(
            target_id="KILN-TARGET-BASELINE",
            target_kind="LOCAL_GIT_REPOSITORY",
            source_location="fixture",
            repository_root="fixture",
            git_repository=True,
            source_commit="abc123",
            repository_clean=False,
            local_or_remote="LOCAL",
            language_hints=("python",),
            manifest_hints=("pyproject.toml",),
            target_fingerprint="fingerprint",
            disposition="TARGET_IDENTIFIED",
        )

        dirty = build_snapshot(
            dirty_target,
            self.facts(),
        )

        self.assertNotEqual(
            clean.snapshot_hash,
            dirty.snapshot_hash,
        )

        self.assertFalse(
            dirty.repository_clean
        )

    def test_blank_fact_value_fails_closed(self):
        with self.assertRaises(ValueError):
            build_snapshot(
                self.target(),
                (
                    BaselineFact(
                        name="tests.canonical.result",
                        value="   ",
                        evidence_ref="E-TEST-001",
                    ),
                ),
            )

    def test_snapshot_hash_ignores_occurrence_specific_target_id(self):
        first_target = TargetIdentity(
            target_id="KILN-TARGET-OCCURRENCE-A",
            target_kind="LOCAL_GIT_REPOSITORY",
            source_location="fixture-a",
            repository_root="fixture-a",
            git_repository=True,
            source_commit="abc123",
            repository_clean=True,
            local_or_remote="LOCAL",
            language_hints=("python",),
            manifest_hints=("pyproject.toml",),
            target_fingerprint="same-fingerprint",
            disposition="TARGET_IDENTIFIED",
        )

        second_target = TargetIdentity(
            target_id="KILN-TARGET-OCCURRENCE-B",
            target_kind="LOCAL_GIT_REPOSITORY",
            source_location="fixture-b",
            repository_root="fixture-b",
            git_repository=True,
            source_commit="abc123",
            repository_clean=True,
            local_or_remote="LOCAL",
            language_hints=("python",),
            manifest_hints=("pyproject.toml",),
            target_fingerprint="same-fingerprint",
            disposition="TARGET_IDENTIFIED",
        )

        first = build_snapshot(
            first_target,
            self.facts(),
        )

        second = build_snapshot(
            second_target,
            self.facts(),
        )

        self.assertNotEqual(
            first.target_id,
            second.target_id,
        )

        self.assertEqual(
            first.source_commit,
            second.source_commit,
        )

        self.assertEqual(
            first.target_fingerprint,
            second.target_fingerprint,
        )

        self.assertEqual(
            first.snapshot_hash,
            second.snapshot_hash,
        )

    def test_semantically_equal_evidence_preserves_snapshot_hash(self):
        fields = (
            EvidenceField(
                name="tests.canonical.result",
                value="PASS",
            ),
            EvidenceField(
                name="tests.canonical.count",
                value="191",
            ),
            EvidenceField(
                name="tests.canonical.exit_code",
                value="0",
            ),
        )

        first_evidence = build_evidence_digest(
            b"Ran 191 tests in 25.711s\nOK\n",
            fields,
        )

        second_evidence = build_evidence_digest(
            b"Ran 191 tests in 40.147s\nOK\n",
            fields,
        )

        self.assertNotEqual(
            first_evidence.raw_evidence_hash,
            second_evidence.raw_evidence_hash,
        )

        self.assertEqual(
            first_evidence.evidence_digest,
            second_evidence.evidence_digest,
        )

        first_snapshot = build_snapshot(
            self.target(),
            (
                BaselineFact(
                    name="tests.canonical.result",
                    value="PASS",
                    evidence_ref=first_evidence.evidence_digest,
                ),
                BaselineFact(
                    name="tests.canonical.count",
                    value="191",
                    evidence_ref=first_evidence.evidence_digest,
                ),
                BaselineFact(
                    name="tests.canonical.exit_code",
                    value="0",
                    evidence_ref=first_evidence.evidence_digest,
                ),
            ),
        )

        second_snapshot = build_snapshot(
            self.target(),
            (
                BaselineFact(
                    name="tests.canonical.result",
                    value="PASS",
                    evidence_ref=second_evidence.evidence_digest,
                ),
                BaselineFact(
                    name="tests.canonical.count",
                    value="191",
                    evidence_ref=second_evidence.evidence_digest,
                ),
                BaselineFact(
                    name="tests.canonical.exit_code",
                    value="0",
                    evidence_ref=second_evidence.evidence_digest,
                ),
            ),
        )

        self.assertEqual(
            first_snapshot.snapshot_hash,
            second_snapshot.snapshot_hash,
        )

if __name__ == "__main__":
    unittest.main()
