import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.cycle_orchestrator import (
    finalize_cycle_result,
    run_cycle,
)
from engine.mutation_adapters import (
    discover_javascript_mutations,
    discover_powershell_mutations,
    discover_wsl2_mutations,
    supported_cycle_adapters,
)


class MutationAdapterTests(unittest.TestCase):

    def initialize_repo(
        self,
        repo: Path,
    ):
        subprocess.run(
            [
                "git",
                "init",
                "-q",
                str(repo),
            ],
            check=True,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "config",
                "user.email",
                "kiln@example.invalid",
            ],
            check=True,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "config",
                "user.name",
                "Kiln Test",
            ],
            check=True,
        )

    def commit_repo(
        self,
        repo: Path,
    ):
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "add",
                ".",
            ],
            check=True,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "commit",
                "-q",
                "-m",
                "baseline",
            ],
            check=True,
        )

    def test_registry_exposes_all_v011_cycle_adapters(self):
        self.assertEqual(
            supported_cycle_adapters(),
            (
                "python",
                "javascript",
                "powershell",
                "wsl2",
                "api-service",
            ),
        )

    def test_javascript_discovery_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            (root/"app.js").write_text(
                "const enabled = true;\n",
                encoding="utf-8",
            )

            first=discover_javascript_mutations(
                root
            )

            second=discover_javascript_mutations(
                root
            )

            self.assertEqual(
                first,
                second,
            )

            self.assertEqual(
                first[0].replacement_token,
                "false",
            )

    def test_powershell_discovery_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            (root/"app.ps1").write_text(
                "$script:Enabled = $true\n",
                encoding="utf-8",
            )

            first=discover_powershell_mutations(
                root
            )

            second=discover_powershell_mutations(
                root
            )

            self.assertEqual(
                first,
                second,
            )

            self.assertEqual(
                first[0].replacement_token,
                "$false",
            )

    def test_wsl2_discovery_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            (root/"app.sh").write_text(
                "FLAG=true\n",
                encoding="utf-8",
            )

            first=discover_wsl2_mutations(
                root
            )

            second=discover_wsl2_mutations(
                root
            )

            self.assertEqual(
                first,
                second,
            )

            self.assertEqual(
                first[0].replacement_token,
                "false",
            )

    def test_wsl2_normalization_is_specimen_local(self):
        import tempfile
        from pathlib import Path

        from engine.mutation_adapters import normalize_wsl2_shell_sources

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"source"
            specimen=root/"specimen"

            source.mkdir()
            specimen.mkdir()

            original=source/"app.sh"
            copied=specimen/"app.sh"

            original.write_bytes(
                b"FLAG=true\r\n"
            )

            copied.write_bytes(
                original.read_bytes()
            )

            before=original.read_bytes()

            normalize_wsl2_shell_sources(
                specimen
            )

            self.assertEqual(
                copied.read_bytes(),
                b"FLAG=true\n",
            )

            self.assertEqual(
                original.read_bytes(),
                before,
            )

    @unittest.skipUnless(
        shutil.which("npm")
        or shutil.which("npm.cmd"),
        "npm unavailable",
    )
    def test_javascript_cycle_fractures_disposable_specimen(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            sessions=root/"sessions"

            repo.mkdir()

            self.initialize_repo(
                repo
            )

            (repo/"package.json").write_text(
                '{"scripts":{"test":"node test.js"}}\n',
                encoding="utf-8",
            )

            (repo/"app.js").write_text(
                "const FLAG = true;\n"
                "module.exports = { enabled: () => FLAG };\n",
                encoding="utf-8",
            )

            (repo/"test.js").write_text(
                "const app = require('./app');\n"
                "if (!app.enabled()) process.exit(1);\n",
                encoding="utf-8",
            )

            self.commit_repo(
                repo
            )

            raw=run_cycle(
                str(repo),
                "javascript",
                "test",
                1,
                "fracture",
                sessions,
            )

            result=finalize_cycle_result(
                raw,
                str(repo),
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertEqual(
                result.fractures_observed,
                1,
            )

            self.assertTrue(
                result.specimen_removed
            )

            self.assertTrue(
                result.original_head_preserved
            )

    @unittest.skipUnless(
        shutil.which("pwsh"),
        "PowerShell unavailable",
    )
    def test_powershell_cycle_fractures_disposable_specimen(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            sessions=root/"sessions"

            repo.mkdir()

            self.initialize_repo(
                repo
            )

            (repo/"app.ps1").write_text(
                "$script:Enabled = $true\n"
                "function Get-Enabled {\n"
                "    return $script:Enabled\n"
                "}\n",
                encoding="utf-8",
            )

            (repo/"test.ps1").write_text(
                '. "$PSScriptRoot\\app.ps1"\n'
                "if (-not (Get-Enabled)) {\n"
                "    exit 1\n"
                "}\n"
                "exit 0\n",
                encoding="utf-8",
            )

            self.commit_repo(
                repo
            )

            raw=run_cycle(
                str(repo),
                "powershell",
                "test.ps1",
                1,
                "fracture",
                sessions,
            )

            result=finalize_cycle_result(
                raw,
                str(repo),
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertEqual(
                result.fractures_observed,
                1,
            )

            self.assertTrue(
                result.original_head_preserved
            )

    @unittest.skipUnless(
        shutil.which("wsl"),
        "WSL2 unavailable",
    )
    def test_wsl2_cycle_fractures_disposable_specimen(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            sessions=root/"sessions"

            repo.mkdir()

            self.initialize_repo(
                repo
            )

            (repo/"app.sh").write_text(
                "FLAG=true\n",
                encoding="utf-8",
            )

            (repo/"test.sh").write_text(
                ". ./app.sh\n"
                'test "$FLAG" = "true"\n',
                encoding="utf-8",
            )

            self.commit_repo(
                repo
            )

            raw=run_cycle(
                str(repo),
                "wsl2",
                "test.sh",
                1,
                "fracture",
                sessions,
            )

            result=finalize_cycle_result(
                raw,
                str(repo),
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertEqual(
                result.fractures_observed,
                1,
            )

            self.assertTrue(
                result.specimen_removed
            )

            self.assertTrue(
                result.original_head_preserved
            )

    def test_api_service_cycle_fractures_and_releases_service(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            sessions=root/"sessions"

            repo.mkdir()

            self.initialize_repo(
                repo
            )

            (repo/"service.py").write_text(
                "import os\n"
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "\n"
                "FLAG = True\n"
                "\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        if self.path != '/health':\n"
                "            self.send_response(404)\n"
                "            self.end_headers()\n"
                "            return\n"
                "        status = 200 if FLAG else 503\n"
                "        self.send_response(status)\n"
                "        self.end_headers()\n"
                "    def log_message(self, format, *args):\n"
                "        return\n"
                "\n"
                "host = os.environ['KILN_HOST']\n"
                "port = int(os.environ['KILN_PORT'])\n"
                "HTTPServer((host, port), Handler).serve_forever()\n",
                encoding="utf-8",
            )

            self.commit_repo(
                repo
            )

            raw=run_cycle(
                str(repo),
                "api-service",
                "service.py",
                1,
                "fracture",
                sessions,
            )

            result=finalize_cycle_result(
                raw,
                str(repo),
            )

            self.assertTrue(
                result.baseline_passed
            )

            self.assertEqual(
                result.passes_executed,
                1,
            )

            self.assertEqual(
                result.fractures_observed,
                1,
            )

            self.assertTrue(
                result.specimen_removed
            )

            self.assertTrue(
                result.original_head_preserved
            )


if __name__ == "__main__":
    unittest.main()
