import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.mutation_executor import discover_python_mutations
from engine.repair_lineage import repair_and_replay, verify_checkpoint


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
                {"candidate_id": candidate.mutation_id, "oracle": "unittest:tests", "repair_budget": 1},
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

    def test_malformed_and_stale_checkpoints_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "checkpoint.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                verify_checkpoint(path)
            path.write_text('{"checkpoint_id":"x","parent_checkpoint_id":null,"source_hash":"a","specimen_hash":"b","parameters_hash":"c","phase":"BASELINE"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "stale"):
                verify_checkpoint(path, {"repair_budget": 1})

    def test_wrong_repair_and_budget_exhaustion_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gate.py").write_text("def enabled(value):\n    return value == True\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_gate.py").write_text("import unittest\nfrom gate import enabled\nclass GateTest(unittest.TestCase):\n    def test_enabled(self): self.assertTrue(enabled(True))\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            candidate = discover_python_mutations(root)[0]
            from dataclasses import replace
            with self.assertRaisesRegex(RuntimeError, "mutation token no longer matches"):
                repair_and_replay(root, replace(candidate, original_token="!="), ["python", "-m", "unittest", "discover", "-s", "tests"], root.parent / (root.name + "-wrong"), {"repair_budget": 1})
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                repair_and_replay(root, candidate, ["python", "-m", "unittest", "discover", "-s", "tests"], root.parent / (root.name + "-budget"), {"repair_budget": 0})


if __name__ == "__main__":
    unittest.main()

