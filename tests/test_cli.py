import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engine.cli import build_parser, main
from engine.version import VERSION


class KilnCliTests(unittest.TestCase):

    def test_version_surface(self):
        self.assertEqual(
            VERSION,
            "0.1.4",
        )

    def test_parser_exposes_full_cycle_surface(self):
        parser = build_parser()

        args = parser.parse_args([
            "cycle",
            ".",
            "--destructive",
            "--max-passes",
            "5",
            "--workers",
            "3",
            "--until",
            "stable",
            "--promote",
            "--approve-promotion",
        ])

        self.assertEqual(
            args.command,
            "cycle",
        )

        self.assertTrue(
            args.destructive
        )

        self.assertEqual(
            args.max_passes,
            5,
        )

        self.assertEqual(
            args.workers,
            3,
        )

        self.assertEqual(
            args.until,
            "stable",
        )

        self.assertTrue(
            args.promote
        )

        self.assertTrue(
            args.approve_promotion
        )

    def test_cycle_fails_closed_without_destructive_authorization(self):
        with tempfile.TemporaryDirectory() as temp:
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = main([
                    "cycle",
                    temp,
                    "--json",
                ])

            self.assertEqual(
                code,
                5,
            )

            self.assertIn(
                "DESTRUCTIVE_AUTHORIZATION_REQUIRED",
                output.getvalue(),
            )

    def test_inspect_local_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = main([
                    "inspect",
                    temp,
                    "--json",
                ])

            self.assertEqual(
                code,
                0,
            )

            self.assertIn(
                "TARGET_IDENTIFIED",
                output.getvalue(),
            )

    def test_capabilities_command(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main([
                "capabilities",
                "--json",
            ])

        self.assertEqual(
            code,
            0,
        )

        self.assertIn(
            "adapter",
            output.getvalue(),
        )

    def test_coal_command_reports_normalized_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = main([
                    "coal",
                    temp,
                    "--adapter",
                    "python",
                    "--json",
                ])

            self.assertEqual(code, 0)
            self.assertIn(
                "KILN-COAL-CONTRACT-1",
                output.getvalue(),
            )
            self.assertIn(
                "COAL_CONTRACT_ACCEPTED",
                output.getvalue(),
            )

    def test_parser_accepts_repository_defined_adapter_name(self):
        parser = build_parser()
        args = parser.parse_args([
            "preflight",
            ".",
            "--adapter",
            "future-language",
            "--entry",
            "all",
        ])

        self.assertEqual(args.adapter, "future-language")

    def test_coal_house_reports_implemented_available_and_proven_separately(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main(["coal-house", "--json"])

        payload = json.loads(output.getvalue())
        rust = next(item for item in payload["capabilities"] if item["adapter"] == "rust-cargo")
        self.assertEqual(code, 0)
        self.assertTrue(rust["implemented"])
        self.assertEqual(rust["venv_adapter"], "rust-cargo")
        self.assertIn("runtime_available", rust)
        self.assertIn("production_proven", rust)

    def test_coal_venvs_reports_reusable_environment_adapters(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main(["coal-venvs", "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["disposition"], "COAL_VENV_LIBRARY_READY")
        self.assertEqual(len(payload["adapters"]), 16)

    def test_coal_fixture_and_qualification_authority_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture_output = io.StringIO()
            fixture = Path(temp) / "fixture"

            with contextlib.redirect_stdout(fixture_output):
                fixture_code = main([
                    "coal-fixture",
                    str(fixture),
                    "--adapter",
                    "rust-cargo",
                    "--json",
                ])

            qualification_output = io.StringIO()

            with contextlib.redirect_stdout(qualification_output):
                qualification_code = main([
                    "coal-qualify",
                    "--adapter",
                    "rust-cargo",
                    "--evidence-root",
                    str(Path(temp) / "evidence"),
                    "--json",
                ])

            self.assertEqual(fixture_code, 0)
            self.assertTrue((fixture / "Cargo.toml").is_file())
            self.assertFalse((fixture / "kiln.coal.json").exists())
            self.assertEqual(qualification_code, 12)
            self.assertIn("DESTRUCTIVE_AUTHORIZATION_REQUIRED", qualification_output.getvalue())


if __name__ == "__main__":
    unittest.main()
