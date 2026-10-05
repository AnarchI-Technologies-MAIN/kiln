import subprocess
import sys
import tempfile
import unittest
import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

from engine.mutation_executor import discover_python_mutations
from engine.repair_lineage import (
    Checkpoint,
    RepairSpec,
    _restore_snapshot,
    repair_and_replay,
    repair_under_same_oracle,
    run_bounded_repair_lineage,
    verify_checkpoint,
)


class RepairLineageTests(unittest.TestCase):
    def _fixture(self, root, source):
        (root / "gate.py").write_text(source, encoding="utf-8")
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
            candidate = next(c for c in discover_python_mutations(root) if c.original_token == "==")
            baseline, repaired = repair_and_replay(
                root,
                candidate,
                ["python", "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"],
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
            from engine.repair_lineage import _checkpoint
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                _checkpoint(path, Path(raw), parent=None, source_hash="a", specimen_hash="b", parameters={}, phase="BASELINE")

    def test_explicit_repair_replays_identical_adverse_input(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root, "def enabled(value):\n    return value != True\n")
            (root / "tests" / "test_gate.py").write_text(
                "import unittest\nfrom gate import enabled\n\n"
                "class GateTest(unittest.TestCase):\n"
                "    def test_enabled_returns_bool(self):\n"
                "        self.assertIsInstance(enabled(True), bool)\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)
            regression = ["python", "-c", "import runpy; assert isinstance(runpy.run_path('gate.py')['enabled'](True), bool)"]
            adverse = ["python", "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"]
            baseline, repaired = repair_under_same_oracle(
                root,
                RepairSpec("gate.py", 2, 17, "!=", "=="),
                regression,
                adverse,
                root.parent / (root.name + "-explicit-checkpoints"),
                {"repair_budget": 1, "adverse_input": "enabled(True)"},
            )
            self.assertEqual(repaired.parent_checkpoint_id, baseline.checkpoint_id)
            self.assertEqual(repaired.phase, "REPAIRED_REPLAY")

    def test_malformed_and_stale_checkpoints_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "checkpoint.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                verify_checkpoint(path)
            path.write_text('{"checkpoint_id":"x","parent_checkpoint_id":null,"source_hash":"a","specimen_hash":"b","parameters_hash":"c","phase":"BASELINE"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                verify_checkpoint(path, {"repair_budget": 1})

    def test_wrong_repair_and_budget_exhaustion_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gate.py").write_text("def enabled(value):\n    return value == True\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_gate.py").write_text("import unittest\nfrom gate import enabled\nclass GateTest(unittest.TestCase):\n    def test_enabled(self): self.assertTrue(enabled(True))\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "e2e@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Kiln E2E"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            candidate = next(c for c in discover_python_mutations(root) if c.original_token == "==")
            with self.assertRaisesRegex(RuntimeError, "mutation token no longer matches"):
                repair_and_replay(root, replace(candidate, original_token="!="), ["python", "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"], root.parent / (root.name + "-wrong"), {"repair_budget": 1})
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                repair_and_replay(root, candidate, ["python", "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"], root.parent / (root.name + "-budget"), {"repair_budget": 0})

    def test_restore_rejects_archive_substitution_before_publish(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "gate.py").write_text("ok\n", encoding="utf-8")
            archive = root / "snapshot.zip"
            manifest = [{"path": "gate.py", "sha256": hashlib.sha256(b"ok\n").hexdigest()}]
            with zipfile.ZipFile(archive, "w") as bundle:
                file_info = zipfile.ZipInfo("gate.py")
                file_info.external_attr = 0o100644 << 16
                bundle.writestr(file_info, "tampered\n")
                bundle.writestr(".kiln-manifest.json", json.dumps(manifest, sort_keys=True))
            snapshot_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            checkpoint = Checkpoint(
                "id", None, "source", "".join([]), "parameters", "BASELINE",
                str(archive), snapshot_hash,
            )
            checkpoint = replace(checkpoint, specimen_hash=hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
            with self.assertRaisesRegex(RuntimeError, "extracted files do not match manifest"):
                _restore_snapshot(checkpoint, root / "destination")
            self.assertFalse((root / "destination").exists())

    def test_restore_rejects_duplicate_archive_members(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "snapshot.zip"
            manifest = [{"path": "gate.py", "sha256": hashlib.sha256(b"ok\n").hexdigest()}]
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("gate.py", "ok\n")
                bundle.writestr("gate.py", "ok\n")
                bundle.writestr(".kiln-manifest.json", json.dumps(manifest, sort_keys=True))
            checkpoint = Checkpoint(
                "id", None, "source", "x", "parameters", "BASELINE",
                str(archive), hashlib.sha256(archive.read_bytes()).hexdigest(),
            )
            with self.assertRaisesRegex(RuntimeError, "duplicate members"):
                _restore_snapshot(checkpoint, root / "destination")

    def test_operational_entrypoint_restores_repairs_replays_and_restores_successor(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root, "def enabled(value):\n    return value != True\n")
            repair = RepairSpec("gate.py", 2, 17, "!=", "==")
            regression = ["python", "-c", "import runpy; assert isinstance(runpy.run_path('gate.py')['enabled'](True), bool)"]
            adverse = ["python", "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"]
            baseline, successor = run_bounded_repair_lineage(
                root,
                repair,
                regression,
                adverse,
                root.parent / (root.name + "-operational"),
                {"repair_budget": 1},
            )
            self.assertEqual(successor.parent_checkpoint_id, baseline.checkpoint_id)
            self.assertEqual(successor.phase, "REPAIRED_REPLAY")

    def test_operational_cli_entrypoint_emits_checkpoint_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root, "def enabled(value):\n    return value != True\n")
            repair_file = root / "repair.json"
            repair_file.write_text(json.dumps({"relative_path": "gate.py", "line": 2, "column": 17, "expected_token": "!=", "replacement_token": "=="}), encoding="utf-8")
            checkpoint_root = root.parent / (root.name + "-cli")
            command = [
                sys.executable, str(Path(__file__).parents[1] / "ci" / "run_repair_lineage.py"),
                "--specimen", str(root), "--repair", str(repair_file), "--checkpoint-root", str(checkpoint_root),
                "--regression-oracle-json", json.dumps([sys.executable, "-c", "import runpy; assert isinstance(runpy.run_path('gate.py')['enabled'](True), bool)"]),
                "--adverse-oracle-json", json.dumps([sys.executable, "-c", "import runpy; assert runpy.run_path('gate.py')['enabled'](True) is True"]),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["successor"]["parent_checkpoint_id"], receipt["baseline"]["checkpoint_id"])
            self.assertTrue((checkpoint_root / "successor-restore" / "gate.py").is_file())

    def test_adverse_exit_must_match_declared_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root, "def enabled(value):\n    return value != True\n")
            with self.assertRaisesRegex(RuntimeError, "expected assertion failure"):
                run_bounded_repair_lineage(
                    root,
                    RepairSpec("gate.py", 2, 17, "!=", "=="),
                    [sys.executable, "-c", "import runpy; assert isinstance(runpy.run_path('gate.py')['enabled'](True), bool)"],
                    [sys.executable, "-c", "raise SystemExit(2)"],
                    root.parent / (root.name + "-bad-exit"),
                    {"repair_budget": 1, "expected_adverse_exit_code": 1},
                )

    def test_oracle_launch_failure_is_not_repair_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root, "def enabled(value):\n    return value != True\n")
            with self.assertRaisesRegex(RuntimeError, "launch failure"):
                run_bounded_repair_lineage(
                    root,
                    RepairSpec("gate.py", 2, 17, "!=", "=="),
                    [str(root / "missing-oracle")],
                    [sys.executable, "-c", "raise SystemExit(1)"],
                    root.parent / (root.name + "-launch-failure"),
                    {"repair_budget": 1},
                )

    def test_interrupted_snapshot_leaves_recoverable_orphan(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gate.py").write_text("ok\n", encoding="utf-8")
            checkpoint_root = root / "checkpoints"
            from engine.repair_lineage import _checkpoint
            with self.assertRaisesRegex(RuntimeError, "fault injected"):
                _checkpoint(
                    checkpoint_root / "baseline.json", root, parent=None,
                    source_hash="source", specimen_hash="", parameters={"fault_inject": "after_archive_fsync"}, phase="BASELINE",
                )
            self.assertTrue((checkpoint_root / "baseline.zip.tmp").is_file())
            result = _checkpoint(
                checkpoint_root / "baseline.json", root, parent=None,
                source_hash="source", specimen_hash="", parameters={}, phase="BASELINE",
            )
            self.assertTrue(Path(result.snapshot_path).is_file())

    def test_archive_published_before_record_is_recoverable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "gate.py").write_text("ok\n", encoding="utf-8")
            checkpoint_root = root / "checkpoints"
            from engine.repair_lineage import _checkpoint
            with self.assertRaisesRegex(RuntimeError, "after archive publication"):
                _checkpoint(
                    checkpoint_root / "baseline.json", root, parent=None,
                    source_hash="source", specimen_hash="", parameters={"fault_inject": "after_archive_publish"}, phase="BASELINE",
                )
            self.assertTrue((checkpoint_root / "baseline.zip").is_file())
            result = _checkpoint(
                checkpoint_root / "baseline.json", root, parent=None,
                source_hash="source", specimen_hash="", parameters={}, phase="BASELINE",
            )
            self.assertTrue(Path(result.snapshot_path).is_file())


if __name__ == "__main__":
    unittest.main()

