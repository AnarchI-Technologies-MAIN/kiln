import unittest

from engine.evidence_digest import (
    EvidenceField,
    build_evidence_digest,
)


class EvidenceDigestTests(unittest.TestCase):
    def fields(self):
        return (
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

    def test_raw_timing_change_preserves_semantic_digest(self):
        first = build_evidence_digest(
            b"Ran 191 tests in 25.711s\nOK\n",
            self.fields(),
        )

        second = build_evidence_digest(
            b"Ran 191 tests in 40.147s\nOK\n",
            self.fields(),
        )

        self.assertNotEqual(
            first.raw_evidence_hash,
            second.raw_evidence_hash,
        )

        self.assertEqual(
            first.evidence_digest,
            second.evidence_digest,
        )

    def test_semantic_field_change_changes_digest(self):
        first = build_evidence_digest(
            b"raw evidence",
            self.fields(),
        )

        second = build_evidence_digest(
            b"raw evidence",
            (
                EvidenceField(
                    name="tests.canonical.result",
                    value="FAIL",
                ),
                self.fields()[1],
                self.fields()[2],
            ),
        )

        self.assertNotEqual(
            first.evidence_digest,
            second.evidence_digest,
        )

    def test_field_order_is_deterministic(self):
        fields = self.fields()

        first = build_evidence_digest(
            b"raw evidence",
            fields,
        )

        second = build_evidence_digest(
            b"raw evidence",
            tuple(reversed(fields)),
        )

        self.assertEqual(
            first.evidence_digest,
            second.evidence_digest,
        )

    def test_invalid_field_authority_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build_evidence_digest(
                b"raw evidence",
                (
                    EvidenceField(
                        name="tests.canonical.result",
                        value="PASS",
                    ),
                    EvidenceField(
                        name=" tests.canonical.result ",
                        value="FAIL",
                    ),
                ),
            )

        with self.assertRaises(ValueError):
            build_evidence_digest(
                b"raw evidence",
                (
                    EvidenceField(
                        name="tests.canonical.result",
                        value="   ",
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()