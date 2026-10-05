import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.mutation_executor import discover_python_mutations
from repair_lineage import repair_and_replay


class RepairLineageTests(unittest.TestCase):
    def test_bounded_repair_replays_and_links_checkpoint(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gate.py").write_text(
                "def enabled(value):\n    return value == True\n",
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_gate.py").write_text(
                "import unittest\nfrom gate import enabled\n\n"
                "class GateTest(unittest.TestCase):\n"
                "    def test_enabled(self):\n"
                "        self.assertTrue(enabled(True))\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "e2e@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Kiln E2E"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            candidate = discover_python_mutations(root)[0]
            baseline, repaired = repair_and_replay(
                root,
                candidate,
                ["python", "-m", "unittest", "discover", "-s", "tests"],
                root.parent / (root.name + "-checkpoints"),
                {"candidate_id": candidate.mutation_id, "oracle": "unittest:tests", "budget": 1},
            )
            self.assertEqual(repaired.parent_checkpoint_id, baseline.checkpoint_id)
            self.assertEqual(baseline.phase, "BASELINE")
            self.assertEqual(repaired.phase, "REPAIRED_REPLAY")
            self.assertEqual((root / "gate.py").read_text(encoding="utf-8"),
                             "def enabled(value):\n    return value == True\n")

    def test_checkpoint_collision_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "baseline.json"
            path.write_text("tampered\n", encoding="utf-8")
            from repair_lineage import _checkpoint
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                _checkpoint(path, parent=None, source_hash="a", specimen_hash="b", parameters={}, phase="BASELINE")


if __name__ == "__main__":
    unittest.main()

