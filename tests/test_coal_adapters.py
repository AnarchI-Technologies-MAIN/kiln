import json
import tempfile
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator

from engine.coal_adapters import coal_adapter_bundle, discover_adapter_bundles
from engine.coal_tongs import coal_pack, discover_coal_packs
from engine.coal_tongs import write_coal_evidence_manifest
from engine.coal_venvs import (
    coal_venv_adapter,
    discover_coal_venvs,
    materialize_coal_venv,
    validate_coal_venv_payload,
)


EXPECTED_VENVS = {
    "cmake-sandbox",
    "dart-pub",
    "dotnet-nuget",
    "elixir-mix",
    "go-modules",
    "haskell-cabal",
    "java-maven",
    "kotlin-gradle",
    "lua-path",
    "php-composer",
    "python-runtime",
    "r-library",
    "ruby-bundler",
    "rust-cargo",
    "swift-swiftpm",
    "zig-cache",
}


def venv_payload() -> dict:
    return {
        "adapter": "nova-venv",
        "directories": [".nova/cache"],
        "environment": {"NOVA_HOME": "{specimen}/.nova"},
        "schema": "kiln.coal-venv.v1",
    }


class CoalAdapterTests(unittest.TestCase):

    def test_language_build_test_and_venv_adapters_are_reusable_components(self):
        bundles = discover_adapter_bundles()

        self.assertEqual(
            {bundle.adapter for bundle in bundles},
            {pack.adapter for pack in discover_coal_packs()},
        )

        rust = coal_adapter_bundle("rust-cargo")
        self.assertEqual(rust.language.languages, ("rust",))
        self.assertEqual(rust.language.source_extensions, (".rs",))
        self.assertEqual(rust.build.build_systems, ("cargo",))
        self.assertEqual(rust.build.rebuild_commands[0][0], "cargo")
        self.assertEqual(rust.test.test_runners, ("cargo-test",))
        self.assertEqual(rust.test.test_command[0], "cargo")
        self.assertEqual(rust.venv.adapter, "rust-cargo")

    def test_venv_discovery_is_dynamic_and_shared_bindings_are_explicit(self):
        venvs = discover_coal_venvs()

        self.assertEqual({venv.adapter for venv in venvs}, EXPECTED_VENVS)
        self.assertEqual(coal_pack("c-cmake").venv_adapter, "cmake-sandbox")
        self.assertEqual(coal_pack("cpp-cmake").venv_adapter, "cmake-sandbox")

        for pack in discover_coal_packs():
            venv = coal_venv_adapter(pack.venv_adapter)
            self.assertEqual(venv.environment, pack.contract.execution.environment, pack.adapter)

    def test_pack_fixture_and_venv_sidecars_pass_their_json_schemas(self):
        root = Path(__file__).resolve().parents[1]
        schema_root = root / "schemas"
        schemas = {
            name: json.loads((schema_root / name).read_text(encoding="utf-8"))
            for name in (
                "kiln.coal-pack.v1.schema.json",
                "kiln.coal-fixture.v1.schema.json",
                "kiln.coal-venv.v1.schema.json",
            )
        }

        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)

        pack_validator = Draft202012Validator(schemas["kiln.coal-pack.v1.schema.json"])
        fixture_validator = Draft202012Validator(schemas["kiln.coal-fixture.v1.schema.json"])
        venv_validator = Draft202012Validator(schemas["kiln.coal-venv.v1.schema.json"])

        for pack in discover_coal_packs():
            pack_validator.validate(json.loads((pack.root / "pack.json").read_text(encoding="utf-8")))
            fixture_validator.validate(json.loads(pack.fixture_path.read_text(encoding="utf-8")))

        for venv in discover_coal_venvs():
            venv_validator.validate(json.loads(venv.root.read_text(encoding="utf-8")))

    def test_materialization_is_confined_and_expands_without_a_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            boundary = Path(temp)
            specimen = boundary / "specimen"
            specimen.mkdir()
            venv = materialize_coal_venv(coal_venv_adapter("rust-cargo"), specimen)

            self.assertEqual({path.name for path in venv.directories}, {".cargo", "target"})
            self.assertTrue(all(path.is_dir() for path in venv.directories))
            self.assertEqual(
                Path(dict(venv.environment)["CARGO_HOME"]).resolve(),
                specimen.resolve() / ".cargo",
            )
            self.assertEqual(set(boundary.iterdir()), {specimen})

    def test_venv_validation_rejects_unknown_fields_and_escapes(self):
        unknown = venv_payload()
        unknown["repairCommand"] = ["fix"]

        with self.assertRaisesRegex(RuntimeError, "unknown fields"):
            validate_coal_venv_payload(unknown)

        traversal = venv_payload()
        traversal["directories"] = ["../outside"]

        with self.assertRaisesRegex(RuntimeError, "escaped"):
            validate_coal_venv_payload(traversal)

    def test_venv_validation_rejects_control_environment_and_placeholders(self):
        control = venv_payload()
        control["environment"] = {"kiln_port": "9000"}

        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            validate_coal_venv_payload(control)

        placeholder = venv_payload()
        placeholder["environment"] = {"NOVA_HOME": "{source}/.nova"}

        with self.assertRaisesRegex(RuntimeError, "invalid placeholders"):
            validate_coal_venv_payload(placeholder)

        malformed = venv_payload()
        malformed["environment"] = {"NOVA_HOME": "{specimen"}

        with self.assertRaisesRegex(RuntimeError, "malformed placeholders"):
            validate_coal_venv_payload(malformed)

    def test_venv_identity_must_match_its_sidecar_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "different.json"
            path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "filename"):
                validate_coal_venv_payload(venv_payload(), origin=path)

    def test_per_adapter_evidence_manifest_is_deterministic(self):
        evidence = Path(__file__).resolve().parents[1] / "coal_house" / "evidence"

        with tempfile.TemporaryDirectory() as temp:
            first = write_coal_evidence_manifest(evidence, Path(temp) / "first.json")
            second = write_coal_evidence_manifest(evidence, Path(temp) / "second.json")
            first_bytes = first.read_bytes()

            self.assertEqual(first_bytes, second.read_bytes())
            payload = json.loads(first_bytes)
            self.assertEqual(
                {item["adapter"] for item in payload["adapters"]},
                {pack.adapter for pack in discover_coal_packs()},
            )
            self.assertTrue(all(item["contractHash"] for item in payload["adapters"]))
            self.assertTrue(all(item["venvHash"] for item in payload["adapters"]))


if __name__ == "__main__":
    unittest.main()
