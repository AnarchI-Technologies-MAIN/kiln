from __future__ import annotations

from pathlib import Path
from typing import Tuple
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from engine.environment_reconstruction import executable_path
from engine.mutation_executor import (
    MutationCandidate,
    file_hash,
    mutation_identity,
    discover_python_mutations,
)


JAVASCRIPT_EXTENSIONS = {
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
}

JAVASCRIPT_REPLACEMENTS = {
    "true": "false",
    "false": "true",
    "===": "!==",
    "!==": "===",
    "==": "!=",
    "!=": "==",
    "&&": "||",
    "||": "&&",
}

POWERSHELL_REPLACEMENTS = {
    "$true": "$false",
    "$false": "$true",
    "-eq": "-ne",
    "-ne": "-eq",
    "-lt": "-ge",
    "-ge": "-lt",
    "-le": "-gt",
    "-gt": "-le",
}

SHELL_REPLACEMENTS = {
    "true": "false",
    "false": "true",
    "-eq": "-ne",
    "-ne": "-eq",
    "-lt": "-ge",
    "-ge": "-lt",
    "-le": "-gt",
    "-gt": "-le",
}


def supported_cycle_adapters() -> Tuple[str, ...]:
    return (
        "python",
        "javascript",
        "powershell",
        "wsl2",
        "api-service",
    )


def excluded_source(
    root: Path,
    path: Path,
) -> bool:
    relative = path.relative_to(
        root
    )

    lowered_parts = {
        part.lower()
        for part in relative.parts
    }

    if lowered_parts & {
        ".git",
        "__pycache__",
        "node_modules",
        "tests",
        "test",
        "__tests__",
    }:
        return True

    lowered_name = path.name.lower()

    if lowered_name.startswith(
        "test_"
    ):
        return True

    if lowered_name.startswith(
        "test."
    ):
        return True

    if ".test." in lowered_name:
        return True

    if ".spec." in lowered_name:
        return True

    return False


def discover_text_mutations(
    root: Path,
    extensions: set[str],
    replacements: dict[str, str],
    pattern: re.Pattern[str],
    kind: str,
) -> Tuple[MutationCandidate, ...]:
    root = Path(root).resolve()
    candidates = []

    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in extensions
        and not excluded_source(
            root,
            path,
        )
    )

    for path in files:
        relative = path.relative_to(
            root
        ).as_posix()

        text = path.read_text(
            encoding="utf-8"
        )

        source_hash = file_hash(
            path
        )

        lines = text.splitlines(
            keepends=True
        )

        for line_number, line in enumerate(
            lines,
            start=1,
        ):
            for match in pattern.finditer(
                line
            ):
                original = match.group(
                    0
                )

                lookup = original

                if kind in {
                    "POWERSHELL_TOKEN_REPLACEMENT",
                    "WSL2_SHELL_TOKEN_REPLACEMENT",
                }:
                    lookup = original.lower()

                replacement = replacements.get(
                    lookup
                )

                if not replacement:
                    continue

                candidates.append(
                    MutationCandidate(
                        mutation_id=mutation_identity(
                            relative,
                            line_number,
                            match.start(),
                            original,
                            replacement,
                            source_hash,
                        ),
                        relative_path=relative,
                        line=line_number,
                        column=match.start(),
                        kind=kind,
                        original_token=original,
                        replacement_token=replacement,
                        source_hash=source_hash,
                    )
                )

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.relative_path,
                item.line,
                item.column,
                item.mutation_id,
            ),
        )
    )


def discover_javascript_mutations(
    root: Path,
) -> Tuple[MutationCandidate, ...]:
    return discover_text_mutations(
        root,
        JAVASCRIPT_EXTENSIONS,
        JAVASCRIPT_REPLACEMENTS,
        re.compile(
            r"\btrue\b|\bfalse\b|!==|===|==|!=|&&|\|\|"
        ),
        "JAVASCRIPT_TOKEN_REPLACEMENT",
    )


def discover_powershell_mutations(
    root: Path,
) -> Tuple[MutationCandidate, ...]:
    return discover_text_mutations(
        root,
        {".ps1", ".psm1"},
        POWERSHELL_REPLACEMENTS,
        re.compile(
            r"\$true\b|\$false\b|-eq\b|-ne\b|-lt\b|-le\b|-gt\b|-ge\b",
            re.IGNORECASE,
        ),
        "POWERSHELL_TOKEN_REPLACEMENT",
    )


def discover_wsl2_mutations(
    root: Path,
) -> Tuple[MutationCandidate, ...]:
    return discover_text_mutations(
        root,
        {".sh", ".bash"},
        SHELL_REPLACEMENTS,
        re.compile(
            r"\btrue\b|\bfalse\b|-eq\b|-ne\b|-lt\b|-le\b|-gt\b|-ge\b",
            re.IGNORECASE,
        ),
        "WSL2_SHELL_TOKEN_REPLACEMENT",
    )


def discover_mutations(
    adapter: str,
    root: Path,
) -> Tuple[MutationCandidate, ...]:
    if adapter == "python":
        return discover_python_mutations(
            root
        )

    if adapter == "javascript":
        return discover_javascript_mutations(
            root
        )

    if adapter == "powershell":
        return discover_powershell_mutations(
            root
        )

    if adapter == "wsl2":
        return discover_wsl2_mutations(
            root
        )

    if adapter == "api-service":
        return discover_python_mutations(
            root
        )

    raise RuntimeError(
        f"unsupported mutation adapter: {adapter}"
    )


def python_command(
    entry: str,
):
    normalized = entry.replace(
        "\\",
        "/",
    )

    target = Path(
        normalized
    )

    if target.suffix == ".py":
        module = target.with_suffix(
            ""
        ).as_posix().replace(
            "/",
            ".",
        )

        return [
            sys.executable,
            "-W",
            "error::ResourceWarning",
            "-m",
            "unittest",
            module,
        ]

    return [
        sys.executable,
        "-W",
        "error::ResourceWarning",
        "-m",
        "unittest",
        "discover",
        "-s",
        normalized,
    ]


def validated_entry(
    specimen: Path,
    entry: str,
) -> Path:
    specimen = Path(
        specimen
    ).resolve()

    target = (
        specimen
        / entry
    ).resolve()

    try:
        target.relative_to(
            specimen
        )
    except ValueError:
        raise RuntimeError(
            "adapter entry escaped specimen"
        )

    if not target.exists():
        raise RuntimeError(
            "adapter entry is missing"
        )

    return target


def normalize_wsl2_shell_sources(
    specimen: Path,
):
    specimen = Path(
        specimen
    ).resolve()

    for path in specimen.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {
            ".sh",
            ".bash",
        }:
            continue

        content = path.read_bytes()

        normalized = content.replace(
            b"\r\n",
            b"\n",
        ).replace(
            b"\r",
            b"\n",
        )

        if normalized != content:
            path.write_bytes(
                normalized
            )


def run_wsl2_tests(
    specimen: Path,
    entry: str,
):
    normalize_wsl2_shell_sources(
        specimen
    )

    target = validated_entry(
        specimen,
        entry,
    )

    wsl = executable_path(
        "wsl"
    )

    if not wsl:
        raise RuntimeError(
            "WSL2 backend is unavailable"
        )

    convert = subprocess.run(
        [
            wsl,
            "--exec",
            "wslpath",
            "-a",
            str(specimen),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if convert.returncode != 0:
        return convert

    specimen_wsl = convert.stdout.strip()

    relative = target.relative_to(
        specimen
    ).as_posix()

    command = (
        "cd "
        + shlex.quote(specimen_wsl)
        + " && sh "
        + shlex.quote("./" + relative)
    )

    return subprocess.run(
        [
            wsl,
            "sh",
            "-lc",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def probe_health(
    port: int,
) -> int:
    url = (
        f"http://127.0.0.1:{port}/health"
    )

    for _ in range(40):
        try:
            with urllib.request.urlopen(
                url,
                timeout=0.25,
            ) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        except Exception:
            time.sleep(
                0.05
            )

    return 0


def run_api_service_tests(
    specimen: Path,
    entry: str,
):
    target = validated_entry(
        specimen,
        entry,
    )

    with socket.socket() as probe:
        probe.bind(
            (
                "127.0.0.1",
                0,
            )
        )

        port = probe.getsockname()[1]

    environment = dict(
        os.environ
    )

    environment["KILN_HOST"] = (
        "127.0.0.1"
    )

    environment["KILN_PORT"] = str(
        port
    )

    process = subprocess.Popen(
        [
            sys.executable,
            str(target),
        ],
        cwd=str(specimen),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    status = 0

    for _ in range(40):
        if process.poll() is not None:
            break

        status = probe_health(
            port
        )

        if status:
            break

    if process.poll() is None:
        process.terminate()

    try:
        stdout, stderr = process.communicate(
            timeout=3
        )
    except subprocess.TimeoutExpired:
        process.kill()

        stdout, stderr = process.communicate(
            timeout=3
        )

    port_released = False

    with socket.socket() as verify:
        try:
            verify.bind(
                (
                    "127.0.0.1",
                    port,
                )
            )

            port_released = True
        except OSError:
            port_released = False

    return_code = 1

    if (
        status == 200
        and port_released
    ):
        return_code = 0

    if not port_released:
        return_code = 2

    return subprocess.CompletedProcess(
        args=[
            sys.executable,
            str(target),
        ],
        returncode=return_code,
        stdout=stdout,
        stderr=stderr,
    )


def run_adapter_tests(
    adapter: str,
    specimen: Path,
    entry: str,
):
    specimen = Path(
        specimen
    ).resolve()

    environment = dict(
        os.environ
    )

    environment["PYTHONPATH"] = str(
        specimen
    )

    if adapter == "python":
        return subprocess.run(
            python_command(entry),
            cwd=str(specimen),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    if adapter == "javascript":
        npm = executable_path(
            "npm"
        )

        return subprocess.run(
            [
                npm,
                "run",
                entry,
            ],
            cwd=str(specimen),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    if adapter == "powershell":
        pwsh = executable_path(
            "pwsh"
        )

        script = validated_entry(
            specimen,
            entry,
        )

        return subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(script),
            ],
            cwd=str(specimen),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    if adapter == "wsl2":
        return run_wsl2_tests(
            specimen,
            entry,
        )

    if adapter == "api-service":
        return run_api_service_tests(
            specimen,
            entry,
        )

    raise RuntimeError(
        f"unsupported cycle adapter: {adapter}"
    )
