import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.coal_contracts import resolve_coal_contract
from engine.mutation_adapters import adapter_available, discover_mutations, run_adapter_tests
from tests.test_coal_contracts import coal_payload


class AdaptiveCoalTests(unittest.TestCase):
    def write_contract(self, root, payload):
        (root / "kiln.coal.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_auto_selects_exact_declared_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root, coal_payload(sys.executable))
            automatic = resolve_coal_contract("auto", root)
            explicit = resolve_coal_contract("nova", root)
            self.assertEqual(automatic, explicit)
            self.assertEqual(automatic.adapter, "nova")
            self.assertTrue(adapter_available("auto", root))

    def test_missing_declaration_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
            self.assertIsNone(resolve_coal_contract("auto", root))
            self.assertFalse(adapter_available("auto", root))

    def test_invalid_declaration_never_executes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = coal_payload(sys.executable)
            payload["execution"]["testCommand"].append("{host_home}")
            self.write_contract(root, payload)
            with patch("engine.mutation_adapters.subprocess.run") as execute:
                with self.assertRaises(RuntimeError):
                    run_adapter_tests("auto", root, "")
                execute.assert_not_called()

    def test_auto_executes_declared_rebuild_and_test_in_specimen(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root, coal_payload(sys.executable))
            (root / "logic.nova").write_text("yes\n", encoding="utf-8")
            result = run_adapter_tests("auto", root, "", timeout_seconds=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "rebuilt.marker").is_file())

    def test_auto_preserves_named_adapter_mutation_identities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root, coal_payload(sys.executable))
            (root / "logic.nova").write_text("yes\n", encoding="utf-8")
            self.assertEqual(
                discover_mutations("auto", root),
                discover_mutations("nova", root),
            )


if __name__ == "__main__":
    unittest.main()
