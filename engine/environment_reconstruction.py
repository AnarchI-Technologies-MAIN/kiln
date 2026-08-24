from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Tuple


@dataclass(frozen=True)
class ReconstructionCapability:
    adapter: str
    available: bool
    executable: str
    disposition: str


def executable_path(name: str) -> str:
    resolved = which(name)

    if resolved:
        return str(Path(resolved).resolve())

    return ""


def host_capabilities() -> Tuple[ReconstructionCapability, ...]:
    adapters = (
        ("python", "python"),
        ("javascript-typescript", "node"),
        ("powershell", "pwsh"),
        ("linux-wsl2", "wsl"),
    )

    results = []

    for adapter, executable in adapters:
        path = executable_path(executable)
        available = bool(path)

        disposition = "RECONSTRUCTION_BACKEND_AVAILABLE"

        if not available:
            disposition = "RECONSTRUCTION_BACKEND_UNAVAILABLE"

        results.append(
            ReconstructionCapability(
                adapter=adapter,
                available=available,
                executable=path,
                disposition=disposition,
            )
        )

    return tuple(results)


@dataclass(frozen=True)
class ReconstructionResult:
    adapter: str
    source_root: str
    specimen_root: str
    materialized: bool
    baseline_passed: bool
    exit_code: int
    teardown_proven: bool
    original_untouched: bool
    disposition: str


def reconstruct_python(
    source_root: Path,
    relative_test: str,
) -> ReconstructionResult:
    import shutil
    import subprocess
    import sys
    import tempfile

    source = Path(source_root).resolve()

    if not source.exists():
        raise RuntimeError(
            "python reconstruction source is missing"
        )

    original_hashes = {}

    for path in source.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            relative = path.relative_to(source).as_posix()
            original_hashes[relative] = path.read_bytes()

    temp = tempfile.mkdtemp(
        prefix="kiln-python-specimen-"
    )

    specimen = Path(temp) / "specimen"

    shutil.copytree(
        source,
        specimen,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".venv",
        ),
    )

    target = specimen / relative_test

    if not target.exists():
        shutil.rmtree(temp, ignore_errors=True)

        return ReconstructionResult(
            adapter="python",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_TARGET_MISSING",
        )

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            target.parent.as_posix(),
            "-p",
            target.name,
        ],
        cwd=str(specimen),
        capture_output=True,
        text=True,
        check=False,
    )

    baseline_passed = run.returncode == 0

    shutil.rmtree(
        temp,
        ignore_errors=True,
    )

    teardown_proven = not Path(temp).exists()

    original_untouched = True

    for relative, content in original_hashes.items():
        path = source / relative

        if not path.exists():
            original_untouched = False
            break

        if path.read_bytes() != content:
            original_untouched = False
            break

    disposition = "RECONSTRUCTION_PROVEN"

    if not baseline_passed:
        disposition = "RECONSTRUCTED_BASELINE_FAILED"

    if not teardown_proven:
        disposition = "RECONSTRUCTION_TEARDOWN_FAILED"

    if not original_untouched:
        disposition = "SOURCE_MUTATION_DETECTED"

    return ReconstructionResult(
        adapter="python",
        source_root=str(source),
        specimen_root="",
        materialized=True,
        baseline_passed=baseline_passed,
        exit_code=run.returncode,
        teardown_proven=teardown_proven,
        original_untouched=original_untouched,
        disposition=disposition,
    )

def reconstruct_javascript(
    source_root: Path,
    script_name: str = "test",
) -> ReconstructionResult:
    import json
    import shutil
    import subprocess
    import tempfile

    source = Path(source_root).resolve()

    package = source / "package.json"

    if not package.exists():
        raise RuntimeError(
            "javascript reconstruction requires package.json"
        )

    original_hashes = {}

    for path in source.rglob("*"):
        if (
            path.is_file()
            and ".git" not in path.parts
            and "node_modules" not in path.parts
        ):
            relative = path.relative_to(source).as_posix()
            original_hashes[relative] = path.read_bytes()

    temp = tempfile.mkdtemp(
        prefix="kiln-js-specimen-"
    )

    specimen = Path(temp) / "specimen"

    shutil.copytree(
        source,
        specimen,
        ignore=shutil.ignore_patterns(
            ".git",
            "node_modules",
            "dist",
            "build",
        ),
    )

    specimen_package = specimen / "package.json"

    package_data = json.loads(
        specimen_package.read_text(
            encoding="utf-8"
        )
    )

    scripts = package_data.get(
        "scripts",
        {},
    )

    if script_name not in scripts:
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="javascript-typescript",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_TARGET_MISSING",
        )

    lockfile = specimen / "package-lock.json"

    npm_executable = (
        executable_path("npm.cmd")
        or executable_path("npm")
    )

    if not npm_executable:
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="javascript-typescript",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_BACKEND_UNAVAILABLE",
        )

    install_command = [
        npm_executable,
        "install",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    ]

    if lockfile.exists():
        install_command = [
            "npm",
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]

    install = subprocess.run(
        install_command,
        cwd=str(specimen),
        capture_output=True,
        text=True,
        check=False,
    )

    run_exit = install.returncode

    if install.returncode == 0:
        run = subprocess.run(
            [
                npm_executable,
                "run",
                script_name,
                "--",
            ],
            cwd=str(specimen),
            capture_output=True,
            text=True,
            check=False,
        )

        run_exit = run.returncode

    baseline_passed = (
        install.returncode == 0
        and run_exit == 0
    )

    shutil.rmtree(
        temp,
        ignore_errors=True,
    )

    teardown_proven = not Path(temp).exists()

    original_untouched = True

    for relative, content in original_hashes.items():
        path = source / relative

        if not path.exists():
            original_untouched = False
            break

        if path.read_bytes() != content:
            original_untouched = False
            break

    disposition = "RECONSTRUCTION_PROVEN"

    if install.returncode != 0:
        disposition = "DEPENDENCY_RECONSTRUCTION_FAILED"

    if install.returncode == 0 and run_exit != 0:
        disposition = "RECONSTRUCTED_BASELINE_FAILED"

    if not teardown_proven:
        disposition = "RECONSTRUCTION_TEARDOWN_FAILED"

    if not original_untouched:
        disposition = "SOURCE_MUTATION_DETECTED"

    return ReconstructionResult(
        adapter="javascript-typescript",
        source_root=str(source),
        specimen_root="",
        materialized=True,
        baseline_passed=baseline_passed,
        exit_code=run_exit,
        teardown_proven=teardown_proven,
        original_untouched=original_untouched,
        disposition=disposition,
    )

def reconstruct_powershell(
    source_root: Path,
    relative_script: str,
) -> ReconstructionResult:
    import shutil
    import subprocess
    import tempfile

    source = Path(source_root).resolve()

    if not source.exists():
        raise RuntimeError(
            "powershell reconstruction source is missing"
        )

    pwsh_executable = executable_path("pwsh")

    if not pwsh_executable:
        return ReconstructionResult(
            adapter="powershell",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_BACKEND_UNAVAILABLE",
        )

    original_hashes = {}

    for path in source.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            relative = path.relative_to(source).as_posix()
            original_hashes[relative] = path.read_bytes()

    temp = tempfile.mkdtemp(
        prefix="kiln-pwsh-specimen-"
    )

    specimen = Path(temp) / "specimen"

    shutil.copytree(
        source,
        specimen,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            "node_modules",
        ),
    )

    target = specimen / relative_script

    if not target.exists():
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="powershell",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_TARGET_MISSING",
        )

    run = subprocess.run(
        [
            pwsh_executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(target),
        ],
        cwd=str(specimen),
        capture_output=True,
        text=True,
        check=False,
    )

    baseline_passed = run.returncode == 0

    shutil.rmtree(
        temp,
        ignore_errors=True,
    )

    teardown_proven = not Path(temp).exists()

    original_untouched = True

    for relative, content in original_hashes.items():
        path = source / relative

        if not path.exists():
            original_untouched = False
            break

        if path.read_bytes() != content:
            original_untouched = False
            break

    disposition = "RECONSTRUCTION_PROVEN"

    if not baseline_passed:
        disposition = "RECONSTRUCTED_BASELINE_FAILED"

    if not teardown_proven:
        disposition = "RECONSTRUCTION_TEARDOWN_FAILED"

    if not original_untouched:
        disposition = "SOURCE_MUTATION_DETECTED"

    return ReconstructionResult(
        adapter="powershell",
        source_root=str(source),
        specimen_root="",
        materialized=True,
        baseline_passed=baseline_passed,
        exit_code=run.returncode,
        teardown_proven=teardown_proven,
        original_untouched=original_untouched,
        disposition=disposition,
    )

def reconstruct_wsl2(
    source_root: Path,
    relative_script: str,
) -> ReconstructionResult:
    import shutil
    import subprocess
    import tempfile
    import uuid

    source = Path(source_root).resolve()

    if not source.exists():
        raise RuntimeError(
            "wsl reconstruction source is missing"
        )

    wsl_executable = executable_path("wsl")

    if not wsl_executable:
        return ReconstructionResult(
            adapter="linux-wsl2",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_BACKEND_UNAVAILABLE",
        )

    probe = subprocess.run(
        [
            wsl_executable,
            "sh",
            "-lc",
            "printf KILN_WSL_READY",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if (
        probe.returncode != 0
        or "KILN_WSL_READY" not in probe.stdout
    ):
        return ReconstructionResult(
            adapter="linux-wsl2",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=probe.returncode,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_BACKEND_UNAVAILABLE",
        )

    original_hashes = {}

    for path in source.rglob("*"):
        if (
            path.is_file()
            and ".git" not in path.parts
            and "node_modules" not in path.parts
        ):
            relative = path.relative_to(source).as_posix()
            original_hashes[relative] = path.read_bytes()

    temp = tempfile.mkdtemp(
        prefix="kiln-wsl-source-"
    )

    staged = Path(temp) / "specimen"

    shutil.copytree(
        source,
        staged,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".venv",
            "node_modules",
            "dist",
            "build",
        ),
    )

    target = staged / relative_script

    if not target.exists():
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="linux-wsl2",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_TARGET_MISSING",
        )

    token = "kiln-" + uuid.uuid4().hex

    windows_path = str(staged).replace(
        "'",
        "''",
    )

    convert = subprocess.run(
        [
            wsl_executable,
            "--exec",
            "wslpath",
            "-a",
            windows_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if convert.returncode != 0:
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="linux-wsl2",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=convert.returncode,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_PATH_MAPPING_FAILED",
        )

    source_wsl = convert.stdout.strip()
    specimen_wsl = f"/tmp/{token}"

    materialize = subprocess.run(
        [
            wsl_executable,
            "sh",
            "-lc",
            (
                f"rm -rf '{specimen_wsl}' && "
                f"mkdir -p '{specimen_wsl}' && "
                f"cp -a '{source_wsl}/.' '{specimen_wsl}/'"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    run_exit = materialize.returncode

    if materialize.returncode == 0:
        run = subprocess.run(
            [
                wsl_executable,
                "sh",
                "-lc",
                (
                    f"cd '{specimen_wsl}' && "
                    f"sh './{relative_script}'"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        run_exit = run.returncode

    teardown = subprocess.run(
        [
            wsl_executable,
            "sh",
            "-lc",
            f"rm -rf '{specimen_wsl}' && test ! -e '{specimen_wsl}'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    shutil.rmtree(
        temp,
        ignore_errors=True,
    )

    teardown_proven = (
        teardown.returncode == 0
        and not Path(temp).exists()
    )

    baseline_passed = (
        materialize.returncode == 0
        and run_exit == 0
    )

    original_untouched = True

    for relative, content in original_hashes.items():
        path = source / relative

        if not path.exists():
            original_untouched = False
            break

        if path.read_bytes() != content:
            original_untouched = False
            break

    disposition = "RECONSTRUCTION_PROVEN"

    if materialize.returncode != 0:
        disposition = "RECONSTRUCTION_MATERIALIZATION_FAILED"

    if materialize.returncode == 0 and run_exit != 0:
        disposition = "RECONSTRUCTED_BASELINE_FAILED"

    if not teardown_proven:
        disposition = "RECONSTRUCTION_TEARDOWN_FAILED"

    if not original_untouched:
        disposition = "SOURCE_MUTATION_DETECTED"

    return ReconstructionResult(
        adapter="linux-wsl2",
        source_root=str(source),
        specimen_root="",
        materialized=materialize.returncode == 0,
        baseline_passed=baseline_passed,
        exit_code=run_exit,
        teardown_proven=teardown_proven,
        original_untouched=original_untouched,
        disposition=disposition,
    )

def reconstruct_api_service(
    source_root: Path,
    relative_service: str,
) -> ReconstructionResult:
    import shutil
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    import urllib.request

    source = Path(source_root).resolve()

    if not source.exists():
        raise RuntimeError(
            "api reconstruction source is missing"
        )

    original_hashes = {}

    for path in source.rglob("*"):
        if (
            path.is_file()
            and ".git" not in path.parts
            and "node_modules" not in path.parts
        ):
            relative = path.relative_to(source).as_posix()
            original_hashes[relative] = path.read_bytes()

    temp = tempfile.mkdtemp(
        prefix="kiln-api-specimen-"
    )

    specimen = Path(temp) / "specimen"

    shutil.copytree(
        source,
        specimen,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".venv",
            "node_modules",
            "dist",
            "build",
        ),
    )

    target = specimen / relative_service

    if not target.exists():
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )

        return ReconstructionResult(
            adapter="api-service",
            source_root=str(source),
            specimen_root="",
            materialized=False,
            baseline_passed=False,
            exit_code=-1,
            teardown_proven=True,
            original_untouched=True,
            disposition="RECONSTRUCTION_TARGET_MISSING",
        )

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    env = dict(__import__("os").environ)
    env["KILN_HOST"] = "127.0.0.1"
    env["KILN_PORT"] = str(port)

    process = subprocess.Popen(
        [
            sys.executable,
            str(target),
        ],
        cwd=str(specimen),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    ready = False

    for _ in range(40):
        if process.poll() is not None:
            break

        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health",
                timeout=0.25,
            ) as response:
                if response.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.05)

    baseline_passed = False

    if ready:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health",
                timeout=1,
            ) as response:
                baseline_passed = (
                    response.status == 200
                )
        except Exception:
            baseline_passed = False

    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    process_stopped = (
        process.poll() is not None
    )

    exit_code = process.returncode

    if process.stdout:
        process.stdout.close()

    if process.stderr:
        process.stderr.close()

    cleanup_deadline = (
        time.monotonic() + 2.0
    )

    specimen_removed = False

    while time.monotonic() < cleanup_deadline:
        try:
            shutil.rmtree(
                temp,
            )
        except FileNotFoundError:
            pass
        except OSError:
            time.sleep(
                0.05
            )

        if not Path(temp).exists():
            specimen_removed = True
            break

    teardown_proven = (
        process_stopped
        and specimen_removed
    )

    original_untouched = True

    for relative, content in original_hashes.items():
        path = source / relative

        if not path.exists():
            original_untouched = False
            break

        if path.read_bytes() != content:
            original_untouched = False
            break

    disposition = "RECONSTRUCTION_PROVEN"

    if not ready:
        disposition = "SERVICE_READINESS_FAILED"

    if ready and not baseline_passed:
        disposition = "RECONSTRUCTED_BASELINE_FAILED"

    if not teardown_proven:
        disposition = "RECONSTRUCTION_TEARDOWN_FAILED"

    if not original_untouched:
        disposition = "SOURCE_MUTATION_DETECTED"

    return ReconstructionResult(
        adapter="api-service",
        source_root=str(source),
        specimen_root="",
        materialized=True,
        baseline_passed=baseline_passed,
        exit_code=exit_code,
        teardown_proven=teardown_proven,
        original_untouched=original_untouched,
        disposition=disposition,
    )

@dataclass(frozen=True)
class ReconstructionAdjudication:
    adapter: str
    destructive_testing_authorized: bool
    disposition: str
    failed_gates: Tuple[str, ...]


def adjudicate_reconstruction(
    result: ReconstructionResult,
) -> ReconstructionAdjudication:
    failures = []

    if not result.materialized:
        failures.append("SPECIMEN_NOT_MATERIALIZED")

    if not result.baseline_passed:
        failures.append("BASELINE_NOT_PROVEN")

    if not result.teardown_proven:
        failures.append("TEARDOWN_NOT_PROVEN")

    if not result.original_untouched:
        failures.append("SOURCE_PRESERVATION_NOT_PROVEN")

    if result.disposition != "RECONSTRUCTION_PROVEN":
        failures.append("RECONSTRUCTION_NOT_PROVEN")

    authorized = len(failures) == 0

    disposition = "DESTRUCTIVE_TESTING_AUTHORIZED"

    if not authorized:
        disposition = "DESTRUCTIVE_TESTING_BLOCKED"

    return ReconstructionAdjudication(
        adapter=result.adapter,
        destructive_testing_authorized=authorized,
        disposition=disposition,
        failed_gates=tuple(sorted(set(failures))),
    )