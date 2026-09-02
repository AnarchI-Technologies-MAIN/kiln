import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.coal_contracts import (
    COAL_CONTRACT_SCHEMA,
    COAL_CONTRACT_VERSION,
    available_coal_adapters,
    repository_coal_contract,
    validate_coal_contract_payload,
)
from engine.cycle_orchestrator import (
    finalize_cycle_result,
    run_cycle,
)
from engine.mutation_adapters import (
    discover_mutations,
    run_adapter_tests,
)
from engine.proof_metadata import (
    build_proof_metadata,
    proof_metadata_payload,
    validate_proof_metadata_payload,
)


def coal_payload(
    python_executable: str,
) -> dict:
    return {
        "schema": COAL_CONTRACT_SCHEMA,
        "contractVersion": COAL_CONTRACT_VERSION,
        "adapter": "nova",
        "languages": ["nova"],
        "sourceExtensions": [".nova"],
        "mutation": {
            "strategy": "text-rules",
            "rules": [
                {
                    "kind": "NOVA_BOOLEAN_REPLACEMENT",
                    "pattern": r"\bno\b|\byes\b",
                    "replacements": {
                        "no": "yes",
                        "yes": "no",
                    },
                    "ignoreCase": False,
                }
            ],
        },
        "execution": {
            "driver": "command",
            "rebuildCommands": [
                [
                    "python3",
                    "build.py",
                ]
            ],
            "testCommand": [
                "python3",
                "test.py",
            ],
            "entryKind": "opaque",
            "appendEntry": False,
            "environment": {
                "NOVA_ENV": "isolated",
            },
        },
        "proof": {
            "parser": "generic",
            "locationPatterns": [
                r"FAIL (?P<path>[^:\r\n]+\.nova):(?P<line>\d+)",
            ],
            "testPatterns": [
                r"CASE (?P<test>[^\r\n]+)",
            ],
            "assertionPatterns": [
                r"\bcheck\s*\(",
            ],
        },
    }


class CoalContractTests(unittest.TestCase):

    def write_contract(self, root: Path) -> None:
        (root / "kiln.coal.json").write_text(
            json.dumps(
                coal_payload(sys.executable),
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        # Create the build and test scripts referenced by the contract
        (root / "build.py").write_text(
            "from pathlib import Path\n"
            "Path('rebuilt.marker').write_text('ready')\n",
            encoding="utf-8",
        )
        (root / "test.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "sys.exit(0 if Path('rebuilt.marker').read_text() == 'ready' else 1)\n",
            encoding="utf-8",
        )

    def test_repository_contract_opens_adapter_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root)

            contract = repository_coal_contract(root)

            self.assertIsNotNone(contract)
            self.assertEqual(contract.adapter, "nova")
            self.assertIn("nova", available_coal_adapters(root))

    def test_external_contract_rejects_non_command_driver(self):
        payload = coal_payload(sys.executable)
        payload["execution"]["driver"] = "python-unittest"

        with self.assertRaisesRegex(
            RuntimeError,
            "command driver",
        ):
            validate_coal_contract_payload(
                payload,
                external=True,
            )

    def test_contract_rejects_unknown_fields_and_placeholders(self):
        unknown_field = coal_payload(sys.executable)
        unknown_field["surprise"] = True

        with self.assertRaisesRegex(RuntimeError, "unknown"):
            validate_coal_contract_payload(
                unknown_field,
                external=True,
            )

        unknown_placeholder = coal_payload(sys.executable)
        unknown_placeholder["execution"]["testCommand"].append(
            "{host_home}"
        )

        with self.assertRaisesRegex(RuntimeError, "placeholder"):
            validate_coal_contract_payload(
                unknown_placeholder,
                external=True,
            )

    def test_contract_cannot_override_kiln_control_environment(self):
        payload = coal_payload(sys.executable)
        payload["execution"]["environment"]["KILN_PORT"] = "9000"

        with self.assertRaisesRegex(RuntimeError, "control variables"):
            validate_coal_contract_payload(
                payload,
                external=True,
            )

    def test_external_contract_rejects_arbitrary_execution_flags(self):
        # Test that -c flag is rejected for external contracts
        payload = coal_payload(sys.executable)
        payload["execution"]["testCommand"] = ["python3", "-c", "print('hello')"]

        with self.assertRaisesRegex(
            RuntimeError,
            "arbitrary code execution",
        ):
            validate_coal_contract_payload(
                payload,
                external=True,
            )

        # Test that shell executables are rejected
        payload = coal_payload(sys.executable)
        payload["execution"]["testCommand"] = ["sh", "test.sh"]

        with self.assertRaisesRegex(
            RuntimeError,
            "shell executable",
        ):
            validate_coal_contract_payload(
                payload,
                external=True,
            )

        # Test that non-allowlisted executables are rejected
        payload = coal_payload(sys.executable)
        payload["execution"]["testCommand"] = ["arbitrary_exe", "arg"]

        with self.assertRaisesRegex(
            RuntimeError,
            "non-allowlisted executable",
        ):
            validate_coal_contract_payload(
                payload,
                external=True,
            )

    def test_external_mutations_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root)
            (root / "engine.nova").write_text(
                "enabled = yes\n",
                encoding="utf-8",
            )

            first = discover_mutations("nova", root)
            second = discover_mutations("nova", root)

            self.assertEqual(first, second)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].original_token, "yes")
            self.assertEqual(first[0].replacement_token, "no")

    def test_external_rebuild_and_test_commands_are_tokenized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root)

            result = run_adapter_tests(
                "nova",
                root,
                "all",
                timeout_seconds=10,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                (root / "rebuilt.marker").read_text(encoding="utf-8"),
                "ready",
            )

    def test_generic_proof_patterns_link_a_foreign_assertion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root)
            tests = root / "tests"
            tests.mkdir()
            source = tests / "engine.test.nova"
            source.write_text(
                "value = no\n"
                "check(value)\n",
                encoding="utf-8",
            )
            metadata = build_proof_metadata(
                root,
                "nova",
                "CASE rejects disabled state\n"
                "FAIL tests/engine.test.nova:2\n",
                "",
                "MUTATION-NOVA-1",
                "all",
            )

            self.assertIn(
                "rejects disabled state",
                metadata.detected_test_ids,
            )
            self.assertIn(
                "tests/engine.test.nova::line-2",
                metadata.detected_test_ids,
            )
            self.assertEqual(len(metadata.assertion_records), 1)
            self.assertEqual(len(metadata.fragment_contracts), 1)
            self.assertEqual(
                metadata.fragment_contracts[0].adapter,
                "nova",
            )
            validate_proof_metadata_payload(
                proof_metadata_payload(metadata),
                "MUTATION-NOVA-1",
            )

    def test_contract_commands_never_invoke_a_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_contract(root)

            with patch(
                "engine.mutation_adapters.subprocess.run",
                wraps=subprocess.run,
            ) as run:
                result = run_adapter_tests(
                    "nova",
                    root,
                    "all",
                    timeout_seconds=10,
                )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(run.call_args_list)
            self.assertTrue(
                all(
                    call.kwargs.get("shell", False) is False
                    for call in run.call_args_list
                )
            )

    def test_external_coal_runs_a_complete_isolated_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            sessions = root / "sessions"
            repo.mkdir()
            payload = coal_payload(sys.executable)
            payload["execution"]["rebuildCommands"] = []
            payload["execution"]["testCommand"] = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path;"
                    "value=Path('engine.nova').read_text();"
                    "ok='check(yes)' in value;"
                    "print('CASE keeps the engine enabled') if not ok else None;"
                    "print('FAIL engine.nova:1') if not ok else None;"
                    "raise SystemExit(0 if ok else 1)"
                ),
            ]
            (repo / "kiln.coal.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (repo / "engine.nova").write_text(
                "check(yes)\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(repo), "config",
                    "user.email", "kiln@example.invalid",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(repo), "config",
                    "user.name", "Kiln Test",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(repo), "commit", "-q",
                    "-m", "baseline",
                ],
                check=True,
            )

            raw = run_cycle(
                str(repo),
                "nova",
                "all",
                1,
                "fracture",
                sessions,
            )
            result = finalize_cycle_result(raw, str(repo))

            self.assertTrue(result.baseline_passed)
            self.assertEqual(result.passes_executed, 1)
            self.assertEqual(result.fractures_observed, 1)
            self.assertEqual(result.execution_failures, 0)
            self.assertTrue(result.original_head_preserved)
            self.assertTrue(result.specimen_removed)
            self.assertTrue(result.trials[0].assertion_refs)
            self.assertTrue(
                result.trials[0].behavioral_fragment_refs
            )


if __name__ == "__main__":
    unittest.main()
