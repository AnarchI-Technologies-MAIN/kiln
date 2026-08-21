import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from engine.cli import build_parser, main
from engine.version import VERSION


class KilnCliTests(unittest.TestCase):

    def test_version_surface(self):
        self.assertEqual(
            VERSION,
            "0.1.3",
        )

    def test_parser_exposes_full_cycle_surface(self):
        parser = build_parser()

        args = parser.parse_args([
            "cycle",
            ".",
            "--destructive",
            "--max-passes",
            "5",
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


if __name__ == "__main__":
    unittest.main()
