import unittest

from ci.sanitized_receipt import build_receipt


class SanitizedReceiptTests(unittest.TestCase):
    sha = "a" * 40

    def result(self):
        return {
            "cycle_id": "cycle-1", "source_commit": self.sha, "adapter": "python", "entry": "ci",
            "until": "stable", "baseline_passed": True, "mutation_candidate_count": 1,
            "passes_requested": 1, "passes_executed": 1, "fractures_observed": 0,
            "survivors_observed": 1, "execution_failures": 0, "specimen_removed": True,
            "original_head_preserved": True, "disposition": "CYCLE_COMPLETE",
            "trials": [{"pass_number": 1, "mutation_id": "m1", "sandbox_id": "s1",
                        "canonical_source_hash": "b" * 64, "test_exit_code": 0,
                        "survived": True, "fracture_observed": False, "restored": True,
                        "sandbox_removed": True, "disposition": "MUTATION_SURVIVED",
                        "private_path": "C:\\secret\\raw.txt"}],
        }

    def test_receipt_is_complete_and_path_free(self):
        receipt = build_receipt(self.result(), "owner/repo", self.sha, "c" * 40, "d" * 40)
        self.assertEqual(receipt["trial_count"], 1)
        self.assertEqual(len(receipt["trials"][0]["trial_identity_hash"]), 64)
        rendered = str(receipt)
        self.assertNotIn("private_path", rendered)
        self.assertNotIn("secret", rendered)

    def test_source_or_runtime_identity_mismatch_fails(self):
        with self.assertRaises(ValueError):
            build_receipt(self.result(), "owner/repo", "e" * 40, "c" * 40, "d" * 40)


if __name__ == "__main__":
    unittest.main()
