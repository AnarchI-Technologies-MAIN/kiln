import csv
import tempfile
import unittest
from pathlib import Path

from engine.fracture_classification import classify, classify_all


class FractureClassificationTests(unittest.TestCase):
    def valid_row(self):
        return {
            "fracture_id": "F-1",
            "plan_id": "P-1",
            "baseline_proven": "true",
            "coupling_proven": "true",
            "recovery_proven": "true",
        }

    def test_valid_fracture_remains_unresolved_without_root_cause(self):
        result = classify(self.valid_row())
        self.assertEqual(result.classification, "UNRESOLVED")
        self.assertFalse(result.repair_authorized)

    def test_unproven_coupling_is_harness_defect(self):
        row = self.valid_row()
        row["coupling_proven"] = "false"
        result = classify(row)
        self.assertEqual(result.classification, "HARNESS_DEFECT")

    def test_empty_fracture_registry_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fractures.csv"

            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "fracture_id",
                    "plan_id",
                    "baseline_proven",
                    "coupling_proven",
                    "recovery_proven",
                ])
                writer.writeheader()

            self.assertEqual(classify_all(path), tuple())

    def test_repair_never_auto_authorizes(self):
        result = classify(self.valid_row())
        self.assertFalse(result.repair_authorized)


if __name__ == "__main__":
    unittest.main()
