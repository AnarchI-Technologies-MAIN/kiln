from pathlib import Path
import csv
import tempfile
import unittest

from engine.library_index import KilnLibraryIndex


class KilnLibraryIndexTests(unittest.TestCase):
    def _write_csv(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)

        if not rows:
            path.write_text("", encoding="utf-8")
            return

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_index_references_shared_library(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry"

            self._write_csv(
                registry / "test-occurrence-registry-001.csv",
                [
                    {
                        "occurrence_id": "OCC-001",
                        "content_id": "CONTENT-001",
                        "repository_root": "C:/repo",
                        "repository_path": "tests/test_alpha.py",
                        "absolute_path": "C:/repo/tests/test_alpha.py",
                        "language": "python",
                    }
                ],
            )

            self._write_csv(
                registry / "test-runner-topology-001.csv",
                [
                    {
                        "occurrence_id": "OCC-001",
                        "runner": "pytest",
                    }
                ],
            )

            self._write_csv(
                registry / "test-taxonomy-relations-001.csv",
                [
                    {
                        "occurrence_id": "OCC-001",
                        "taxonomy_value": "regression",
                    },
                    {
                        "occurrence_id": "OCC-001",
                        "taxonomy_value": "authorization",
                    },
                ],
            )

            index = KilnLibraryIndex(root).load()

            self.assertEqual(len(index), 1)

            record = index.get("OCC-001")

            self.assertIsNotNone(record)
            self.assertEqual(record.content_id, "CONTENT-001")
            self.assertEqual(record.runner, "pytest")
            self.assertEqual(
                record.taxonomy,
                ("authorization", "regression"),
            )

    def test_filtering_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry"

            self._write_csv(
                registry / "test-occurrence-registry-001.csv",
                [
                    {
                        "occurrence_id": "OCC-B",
                        "content_id": "CONTENT-B",
                    },
                    {
                        "occurrence_id": "OCC-A",
                        "content_id": "CONTENT-A",
                    },
                ],
            )

            index = KilnLibraryIndex(root).load()

            observed = [record.occurrence_id for record in index.all()]

            self.assertEqual(observed, ["OCC-A", "OCC-B"])


if __name__ == "__main__":
    unittest.main()
