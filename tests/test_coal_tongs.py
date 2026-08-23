import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator

from engine.coal_contracts import (
    COAL_CONTRACT_FILENAME,
    available_coal_adapters,
    validate_coal_contract_payload,
)
from engine.coal_tongs import (
    COAL_CONTRACT_FILENAME as TONGS_CONTRACT_FILENAME,
    coal_pack,
    cycle_qualifies,
    discover_coal_packs,
    load_coal_fixture,
    mark_coal_specimen,
    matching_replay_hashes,
    move_coal_pack_to_specimen,
    probe_coal_capability,
    qualify_coal_pack,
    validate_fixture_proof,
    write_survivors,
    write_coal_fixture,
)
from engine.mutation_adapters import (
    discover_mutations,
    expand_contract_command,
    run_adapter_tests,
    run_contract_tests,
)
from tests.test_coal_contracts import coal_payload


EXPECTED_PACKS = {
    "c-cmake",
    "cpp-cmake",
    "dart",
    "dotnet",
    "elixir-mix",
    "go",
    "haskell-cabal",
    "java-maven",
    "kotlin-gradle",
    "lua",
    "php-composer",
    "python-unittest",
    "r",
    "ruby-bundler",
    "rust-cargo",
    "swift-swiftpm",
    "zig",
}


def command_payload(command) -> dict:
    payload = coal_payload(sys.executable)
    payload["execution"].update({
        "entryKind": "none",
        "appendEntry": False,
        "rebuildCommands": [],
        "testCommand": command,
    })
    return payload


class CoalTongsTests(unittest.TestCase):

    def test_pack_discovery_is_dynamic_and_complete(self):
        packs = discover_coal_packs()

        self.assertEqual({pack.adapter for pack in packs}, EXPECTED_PACKS)
        self.assertTrue(EXPECTED_PACKS.issubset(available_coal_adapters()))
        self.assertTrue(all(pack.contract.origin.startswith("coal-house:") for pack in packs))

    def test_every_contract_passes_the_canonical_json_schema(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "kiln.coal-contract.v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        for pack in discover_coal_packs():
            payload = json.loads(
                (pack.root / COAL_CONTRACT_FILENAME).read_text(encoding="utf-8")
            )
            validator.validate(payload)

    def test_every_pack_has_deterministic_mutation_and_proof_fixtures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            for pack in discover_coal_packs():
                repository = write_coal_fixture(pack, root / pack.adapter)
                first = discover_mutations(pack.adapter, repository)
                second = discover_mutations(pack.adapter, repository)
                metadata = validate_fixture_proof(pack, repository)

                self.assertEqual(first, second, pack.adapter)
                self.assertTrue(first, pack.adapter)
                self.assertTrue(metadata.detected_test_ids, pack.adapter)
                self.assertTrue(metadata.invariant_refs, pack.adapter)
                self.assertTrue(metadata.assertion_refs, pack.adapter)
                self.assertTrue(metadata.behavioral_fragment_refs, pack.adapter)

    def test_fixture_generation_does_not_grant_contract_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = write_coal_fixture(coal_pack("rust-cargo"), Path(temp) / "fixture")

            self.assertFalse((root / COAL_CONTRACT_FILENAME).exists())

    def test_pack_moves_only_into_a_marked_nested_specimen(self):
        with tempfile.TemporaryDirectory() as temp:
            boundary = Path(temp) / "sandbox"
            repository = boundary / "repository"
            repository.mkdir(parents=True)

            with self.assertRaisesRegex(RuntimeError, "marker"):
                move_coal_pack_to_specimen("rust-cargo", repository, boundary)

            mark_coal_specimen(boundary, repository)
            destination = move_coal_pack_to_specimen("rust-cargo", repository, boundary)

            self.assertEqual(destination.name, TONGS_CONTRACT_FILENAME)
            self.assertTrue(destination.is_file())
            self.assertTrue((repository / ".cargo").is_dir())
            self.assertTrue((repository / "target").is_dir())

            outside = Path(temp) / "outside"
            outside.mkdir()

            with self.assertRaisesRegex(RuntimeError, "authorize"):
                move_coal_pack_to_specimen("rust-cargo", outside, boundary)

    def test_runtime_unavailable_is_reported_not_passed(self):
        pack = coal_pack("rust-cargo")

        with patch("engine.coal_tongs.executable_path", return_value=""):
            capability = probe_coal_capability(pack)

        self.assertFalse(capability.runtime_available)
        self.assertTrue(capability.production_proven)
        self.assertFalse(capability.metal_earned)
        self.assertEqual(
            capability.disposition,
            "COAL_PRODUCTION_PROVEN_RUNTIME_UNAVAILABLE",
        )

    def test_current_survivors_route_to_configured_adjudication_inbox(self):
        evidence = Path(__file__).resolve().parents[1] / "coal_house" / "evidence"

        with tempfile.TemporaryDirectory() as temp:
            inbox = Path(temp) / "To-Adjudicate"
            inbox.mkdir()

            with patch.dict(
                os.environ,
                {"KILN_ADJUDICATION_INBOX": str(inbox)},
            ):
                destination = write_survivors(evidence)

            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(
                destination,
                inbox.resolve() / "kiln-adjudication-candidates.json",
            )
            self.assertEqual(
                payload["survivors"],
                [{
                    "adapter": "rust-cargo",
                    "campaign": "production",
                    "disposition": "REQUIRES_ADJUDICATION",
                    "mutation_id": "KILN-MUTATION-5CC75DD45EAF5E154453",
                }],
            )

    def test_future_qualification_refreshes_adjudication_inbox(self):
        pack = coal_pack("zig")
        unavailable = replace(
            probe_coal_capability(pack),
            runtime_available=False,
            production_proven=False,
            metal_earned=False,
            missing_commands=("zig",),
        )

        with tempfile.TemporaryDirectory() as temp, patch(
            "engine.coal_tongs.probe_coal_capability",
            return_value=unavailable,
        ), patch("engine.coal_tongs.write_survivors") as route:
            qualification = qualify_coal_pack("zig", Path(temp))

            self.assertFalse(qualification.runtime_available)
            route.assert_called_once_with(Path(temp).resolve())

    def test_failed_runtime_probe_is_unavailable(self):
        pack = coal_pack("rust-cargo")
        failed = subprocess.CompletedProcess(["cargo", "--version"], 1, "", "broken")

        with patch("engine.coal_tongs.executable_path", return_value="cargo"), patch(
            "engine.coal_tongs.subprocess.run",
            return_value=failed,
        ):
            capability = probe_coal_capability(pack)

        self.assertFalse(capability.runtime_available)

    def test_malformed_fixture_proof_output_fails_closed(self):
        pack = coal_pack("rust-cargo")
        fixture = replace(load_coal_fixture(pack), failure_output="not proof")

        with tempfile.TemporaryDirectory() as temp:
            repository = write_coal_fixture(pack, Path(temp) / "fixture")

            with patch("engine.coal_tongs.load_coal_fixture", return_value=fixture):
                with self.assertRaisesRegex(RuntimeError, "malformed or incomplete"):
                    validate_fixture_proof(pack, repository)

    def test_nondeterministic_replay_hashes_fail(self):
        first = {"mutation-trials.csv": "a", "proof-metadata.json": "b"}
        second = {"mutation-trials.csv": "a", "proof-metadata.json": "c"}

        self.assertFalse(matching_replay_hashes(first, second))
        self.assertTrue(matching_replay_hashes(first, dict(first)))

    def test_cleanup_failure_disqualifies_adapter(self):
        trial = SimpleNamespace(
            fracture_observed=True,
            detected_test_ids=("test",),
            invariant_refs=("invariant",),
            assertion_refs=("assertion",),
            behavioral_fragment_refs=("fragment",),
            restored=True,
            sandbox_removed=False,
        )
        result = SimpleNamespace(
            baseline_passed=True,
            passes_executed=1,
            fractures_observed=1,
            execution_failures=0,
            specimen_removed=False,
            original_head_preserved=True,
            trials=(trial,),
        )

        self.assertFalse(cycle_qualifies(result, require_fracture=True))

    def test_observation_without_assertion_cannot_earn_metal(self):
        trial = SimpleNamespace(
            fracture_observed=True,
            detected_test_ids=("test",),
            invariant_refs=("invariant",),
            assertion_refs=(),
            behavioral_fragment_refs=("observation",),
            restored=True,
            sandbox_removed=True,
        )
        result = SimpleNamespace(
            baseline_passed=True,
            passes_executed=1,
            fractures_observed=1,
            execution_failures=0,
            specimen_removed=True,
            original_head_preserved=True,
            trials=(trial,),
        )

        self.assertFalse(cycle_qualifies(result, require_fracture=True))

    def test_missing_runtime_command_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "engine.mutation_adapters.executable_path",
            return_value="",
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                expand_contract_command(("missing-kiln-runtime", "test"), Path(temp), "")

    def test_shared_deadline_times_out(self):
        payload = command_payload([sys.executable, "-c", "import time; time.sleep(1)"])
        contract = validate_coal_contract_payload(payload, external=True)

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_contract_tests(contract, Path(temp), "", dict(os.environ), 0.01)

    def test_test_failure_needs_parseable_proof(self):
        proven = command_payload([
            sys.executable,
            "-c",
            "print('CASE nova.case');print('FAIL test.nova:1');raise SystemExit(101)",
        ])
        malformed = command_payload([
            sys.executable,
            "-c",
            "print('not proof');raise SystemExit(1)",
        ])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "test.nova").write_text("check(yes)\n", encoding="utf-8")

            for payload, expected in ((proven, 1), (malformed, 2)):
                (root / COAL_CONTRACT_FILENAME).write_text(
                    json.dumps(payload, sort_keys=True),
                    encoding="utf-8",
                )
                result = run_adapter_tests("nova", root, "", timeout_seconds=10)
                self.assertEqual(result.returncode, expected)

    def test_shell_injection_token_is_one_inert_argument(self):
        payload = command_payload([
            sys.executable,
            "-c",
            "import sys;raise SystemExit(0 if sys.argv[1] == '; touch pwned' else 1)",
            "; touch pwned",
        ])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / COAL_CONTRACT_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
            result = run_adapter_tests("nova", root, "", timeout_seconds=10)

            self.assertEqual(result.returncode, 0)
            self.assertFalse((root / "pwned").exists())

    def test_runtime_rejects_casefolded_control_environment_and_bad_templates(self):
        environment = command_payload([sys.executable, "--version"])
        environment["execution"]["environment"]["kiln_port"] = "9000"

        with self.assertRaisesRegex(RuntimeError, "control variables"):
            validate_coal_contract_payload(environment, external=True)

        placeholder = command_payload([sys.executable, "--version"])
        placeholder["execution"]["environment"]["CACHE"] = "{specimen"

        with self.assertRaisesRegex(RuntimeError, "malformed placeholders"):
            validate_coal_contract_payload(placeholder, external=True)

    def test_runtime_rejects_authority_commands(self):
        payload = command_payload(["git", "push", "origin", "main"])

        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            validate_coal_contract_payload(payload, external=True)


if __name__ == "__main__":
    unittest.main()
