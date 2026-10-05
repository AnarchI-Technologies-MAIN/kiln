import json
import tempfile
import unittest
from pathlib import Path

from ci.validate_kiln_evidence import validate


class ValidateKilnEvidenceTests(unittest.TestCase):
    sha = "a" * 40

    def write_result(self, root: Path, **overrides):
        proof = root / "proof-metadata.json"
        proof.write_text(json.dumps({
            "schema": "kiln.proof-metadata-aggregate.v1",
            "proof_evidence_version": "KILN-PROOF-EVIDENCE-3",
            "trials": [
                {"pass_number": 1, "mutation_id": "m1", "metadata": {
                    "schema": "kiln.proof-metadata.v2",
                    "proof_metadata_version": "KILN-PROOF-METADATA-2",
                }},
                {"pass_number": 2, "mutation_id": "m2", "metadata": {
                    "schema": "kiln.proof-metadata.v2",
                    "proof_metadata_version": "KILN-PROOF-METADATA-2",
                }},
            ],
        }) + "\n", encoding="utf-8")
        result = {
            "source_commit": self.sha,
            "baseline_passed": True,
            "mutation_candidate_count": 1,
            "passes_requested": 2,
            "passes_executed": 2,
            "execution_failures": 0,
            "specimen_removed": True,
            "original_head_preserved": True,
            "disposition": "FRACTURE_EVIDENCE_PRODUCED",
            "proof_metadata_path": str(proof),
            "fractures_observed": 1,
            "survivors_observed": 1,
        }
        result.update(overrides)
        (root / "cycle-result.json").write_text(json.dumps(result), encoding="utf-8")

    def test_fracture_and_survivor_are_reported_but_do_not_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_result(root)
            outcome = validate(root, self.sha, 2)
            self.assertTrue(outcome["qualified"])
            self.assertEqual(outcome["survivors_observed"], 1)

    def test_zero_candidates_fail_as_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_result(root, mutation_candidate_count=0)
            with self.assertRaisesRegex(ValueError, "no mutation candidate"):
                validate(root, self.sha, 2)

    def test_incomplete_execution_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_result(root, passes_executed=1)
            with self.assertRaisesRegex(ValueError, "every requested pass"):
                validate(root, self.sha, 2)

    def test_stale_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_result(root)
            with self.assertRaisesRegex(ValueError, "different source commit"):
                validate(root, "b" * 40, 2)


if __name__ == "__main__":
    unittest.main()

