import unittest

from engine.environment_reconstruction import host_capabilities


class EnvironmentReconstructionTests(unittest.TestCase):

    def test_capability_inventory_is_deterministic(self):
        first = host_capabilities()
        second = host_capabilities()

        self.assertEqual(
            first,
            second,
        )

    def test_required_v010_adapters_are_declared(self):
        observed = {
            item.adapter
            for item in host_capabilities()
        }

        self.assertEqual(
            observed,
            {
                "python",
                "javascript-typescript",
                "powershell",
                "linux-wsl2",
            },
        )

    def test_available_backends_have_executables(self):
        for item in host_capabilities():
            if item.available:
                self.assertTrue(
                    item.executable
                )


    def test_python_reconstruction_materializes_runs_and_tears_down(self):
        import tempfile
        from pathlib import Path

        from engine.environment_reconstruction import reconstruct_python

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            test = root / "test_sample.py"

            test.write_text(
                "import unittest\n"
                "\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertEqual(2 + 2, 4)\n",
                encoding="utf-8",
            )

            before = test.read_text(
                encoding="utf-8"
            )

            result = reconstruct_python(
                root,
                "test_sample.py",
            )

            after = test.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.materialized
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.teardown_proven
            )

            self.assertTrue(
                result.original_untouched
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                result.disposition,
                "RECONSTRUCTION_PROVEN",
            )

    def test_javascript_reconstruction_materializes_runs_and_tears_down(self):
        import json
        import tempfile
        from pathlib import Path

        from engine.environment_reconstruction import reconstruct_javascript

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            package = {
                "name": "kiln-js-fixture",
                "version": "1.0.0",
                "scripts": {
                    "test": "node test.js"
                }
            }

            (root / "package.json").write_text(
                json.dumps(package),
                encoding="utf-8",
            )

            test = root / "test.js"

            test.write_text(
                "if (2 + 2 !== 4) process.exit(1);\n",
                encoding="utf-8",
            )

            before = test.read_text(
                encoding="utf-8"
            )

            result = reconstruct_javascript(
                root,
                "test",
            )

            after = test.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.materialized
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.teardown_proven
            )

            self.assertTrue(
                result.original_untouched
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                result.disposition,
                "RECONSTRUCTION_PROVEN",
            )

    def test_powershell_reconstruction_materializes_runs_and_tears_down(self):
        import shutil
        import tempfile
        from pathlib import Path

        from engine.environment_reconstruction import reconstruct_powershell

        if shutil.which("pwsh") is None:
            self.skipTest(
                "PowerShell reconstruction backend unavailable on this host"
            )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            script = root / "test.ps1"

            script.write_text(
                "if ((2 + 2) -ne 4) { exit 1 }\n"
                "exit 0\n",
                encoding="utf-8",
            )

            before = script.read_text(
                encoding="utf-8"
            )

            result = reconstruct_powershell(
                root,
                "test.ps1",
            )

            after = script.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.materialized
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.teardown_proven
            )

            self.assertTrue(
                result.original_untouched
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                result.disposition,
                "RECONSTRUCTION_PROVEN",
            )

    def test_wsl2_reconstruction_materializes_runs_and_tears_down(self):
        import shutil
        import tempfile
        from pathlib import Path

        from engine.environment_reconstruction import reconstruct_wsl2

        if shutil.which("wsl") is None:
            self.skipTest(
                "WSL2 reconstruction backend unavailable on this host"
            )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            script = root / "test.sh"

            script.write_text(
                "#!/bin/sh\n"
                "test \"$((2 + 2))\" -eq 4\n",
                encoding="utf-8",
            )

            before = script.read_text(
                encoding="utf-8"
            )

            result = reconstruct_wsl2(
                root,
                "test.sh",
            )

            after = script.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.materialized
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.teardown_proven
            )

            self.assertTrue(
                result.original_untouched
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                result.disposition,
                "RECONSTRUCTION_PROVEN",
            )

    def test_api_service_reconstruction_materializes_probes_and_tears_down(self):
        import tempfile
        from pathlib import Path

        from engine.environment_reconstruction import reconstruct_api_service

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            service = root / "service.py"

            service.write_text(
                "import os\n"
                "from http.server import BaseHTTPRequestHandler,HTTPServer\n"
                "\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        if self.path == '/health':\n"
                "            self.send_response(200)\n"
                "            self.end_headers()\n"
                "            self.wfile.write(b'OK')\n"
                "            return\n"
                "        self.send_response(404)\n"
                "        self.end_headers()\n"
                "\n"
                "    def log_message(self, format, *args):\n"
                "        return\n"
                "\n"
                "host = os.environ['KILN_HOST']\n"
                "port = int(os.environ['KILN_PORT'])\n"
                "HTTPServer((host, port), Handler).serve_forever()\n",
                encoding="utf-8",
            )

            before = service.read_text(
                encoding="utf-8"
            )

            result = reconstruct_api_service(
                root,
                "service.py",
            )

            after = service.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.materialized
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertTrue(
                result.teardown_proven
            )

            self.assertTrue(
                result.original_untouched
            )

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                result.disposition,
                "RECONSTRUCTION_PROVEN",
            )

    def test_proven_reconstruction_authorizes_destructive_testing(self):
        from engine.environment_reconstruction import (
            ReconstructionResult,
            adjudicate_reconstruction,
        )

        result = ReconstructionResult(
            adapter="python",
            source_root="source",
            specimen_root="",
            materialized=True,
            baseline_passed=True,
            exit_code=0,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_PROVEN",
        )

        decision = adjudicate_reconstruction(
            result
        )

        self.assertTrue(
            decision.destructive_testing_authorized
        )

        self.assertEqual(
            decision.disposition,
            "DESTRUCTIVE_TESTING_AUTHORIZED",
        )

    def test_failed_reconstruction_blocks_destructive_testing(self):
        from engine.environment_reconstruction import (
            ReconstructionResult,
            adjudicate_reconstruction,
        )

        result = ReconstructionResult(
            adapter="api-service",
            source_root="source",
            specimen_root="",
            materialized=True,
            baseline_passed=False,
            exit_code=1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTED_BASELINE_FAILED",
        )

        decision = adjudicate_reconstruction(
            result
        )

        self.assertFalse(
            decision.destructive_testing_authorized
        )

        self.assertIn(
            "BASELINE_NOT_PROVEN",
            decision.failed_gates,
        )

        self.assertEqual(
            decision.disposition,
            "DESTRUCTIVE_TESTING_BLOCKED",
        )

if __name__ == "__main__":
    unittest.main()
