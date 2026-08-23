import copy
import tempfile
import unittest
from pathlib import Path

from engine.proof_metadata import (
    build_proof_metadata,
    failure_test_ids,
    proof_metadata_payload,
    validate_proof_metadata_payload,
)


class ProofMetadataTests(unittest.TestCase):

    def test_unittest_failure_identifies_test_invariant_and_fragment(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            tests=root/"tests"
            tests.mkdir()
            source=tests/"test_app.py"
            source.write_text(
                "import unittest\n"
                "\n"
                "class AppTests(unittest.TestCase):\n"
                "    def test_enabled(self):\n"
                "        value = False\n"
                "        self.assertTrue(value)\n",
                encoding="utf-8",
            )

            stderr=(
                "FAIL: test_enabled (tests.test_app.AppTests.test_enabled)\n"
                "----------------------------------------------------------------------\n"
                f'  File "{source}", line 6, in test_enabled\n'
                "    self.assertTrue(value)\n"
                "AssertionError: False is not true\n"
            )

            metadata=build_proof_metadata(
                root,
                "python",
                "",
                stderr,
                "MUTATION-1",
                "tests",
            )

            self.assertIn(
                "tests.test_app.AppTests.test_enabled",
                metadata.detected_test_ids,
            )
            self.assertIn(
                "tests/test_app.py::AppTests.test_enabled",
                metadata.detected_test_ids,
            )
            self.assertEqual(
                len(metadata.invariant_refs),
                1,
            )
            self.assertEqual(
                len(metadata.assertion_refs),
                1,
            )
            self.assertEqual(
                len(metadata.behavioral_fragment_refs),
                1,
            )
            self.assertEqual(len(metadata.assertion_records), 1)
            self.assertEqual(len(metadata.fragment_contracts), 1)
            self.assertEqual(len(metadata.fragment_proof_links), 1)
            contract = metadata.fragment_contracts[0]
            self.assertEqual(contract.role, "ASSERTION")
            self.assertEqual(contract.source_path, "tests/test_app.py")
            self.assertEqual(
                contract.reproduction_selector,
                "tests/test_app.py::AppTests.test_enabled",
            )
            self.assertEqual(
                metadata.fragment_proof_links[0].mutation_id,
                "MUTATION-1",
            )
            validate_proof_metadata_payload(
                proof_metadata_payload(metadata),
                "MUTATION-1",
            )

    def test_proof_metadata_validation_rejects_contract_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / "tests"
            tests.mkdir()
            source = tests / "test_nested.py"
            source.write_text(
                "import tempfile\n"
                "import unittest\n"
                "class Tests(unittest.TestCase):\n"
                "    def test_nested(self):\n"
                "        with tempfile.TemporaryDirectory():\n"
                "            with self.assertRaises(ValueError):\n"
                "                raise TypeError()\n",
                encoding="utf-8",
            )
            metadata = build_proof_metadata(
                root,
                "python",
                "",
                f'  File "{source}", line 6, in test_nested\n',
                "MUTATION-2",
                "tests",
            )
            payload = proof_metadata_payload(metadata)

        validate_proof_metadata_payload(payload, "MUTATION-2")

        with self.assertRaisesRegex(RuntimeError, "proof link"):
            validate_proof_metadata_payload(payload, "OTHER-MUTATION")

        absolute = copy.deepcopy(payload)
        absolute["fragment_contracts"][0]["source_path"] = (
            "C:/transient/test_nested.py"
        )

        with self.assertRaisesRegex(RuntimeError, "invalid or incomplete"):
            validate_proof_metadata_payload(absolute, "MUTATION-2")

        dangling = copy.deepcopy(payload)
        dangling["fragment_contracts"][0]["assertion_refs"].append(
            "KILN-ASSERTION-UNKNOWN"
        )

        with self.assertRaisesRegex(RuntimeError, "invalid or incomplete"):
            validate_proof_metadata_payload(dangling, "MUTATION-2")

        incomplete = copy.deepcopy(payload)
        del incomplete["fragment_contracts"][0]["reproduction_selector"]

        with self.assertRaisesRegex(RuntimeError, "invalid or incomplete"):
            validate_proof_metadata_payload(incomplete, "MUTATION-2")

    def test_failure_test_ids_are_deterministic(self):
        output=(
            "ERROR: test_b (tests.test_b.Case.test_b)\n"
            "FAIL: test_a (tests.test_a.Case.test_a)\n"
            "FAILED (failures=1, errors=1)\n"
        )

        self.assertEqual(
            failure_test_ids(output),
            (
                "tests.test_a.Case.test_a",
                "tests.test_b.Case.test_b",
            ),
        )


if __name__ == "__main__":
    unittest.main()
