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
from engine.coal_contracts import (
    CoalContract,
    available_coal_adapters,
    coal_failure_locations,
    coal_failure_test_ids,
    resolve_coal_contract,
)
from engine.mutation_executor import (
    MUTATION_IDENTITY_VERSION,
    MutationCandidate,
    canonical_source_hash,
    file_hash,
    mutation_identity,
    mutation_source_files,
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

DEFAULT_TEST_TIMEOUT_SECONDS = 300.0


def supported_cycle_adapters(
    root: Path | None = None,
) -> Tuple[str, ...]:
    return available_coal_adapters(root)


def adapter_available(
    adapter: str,
    root: Path,
) -> bool:
    return resolve_coal_contract(
        adapter,
        root,
    ) is not None


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

    if (
        lowered_name.endswith("_test.go")
        or lowered_name.endswith("_test.exs")
        or lowered_name.endswith("_spec.rb")
    ):
        return True

    return False


def discover_text_mutations(
    root: Path,
    extensions: set[str],
    replacements: dict[str, str],
    pattern: re.Pattern[str],
    kind: str,
    ignore_case: bool = False,
) -> Tuple[MutationCandidate, ...]:
    root = Path(root).resolve()
    candidates = []

    files = tuple(
        path
        for path in mutation_source_files(
            root,
            tuple(
                sorted(
                    extensions
                )
            ),
        )
        if not excluded_source(
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

        semantic_hash = canonical_source_hash(
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

                if ignore_case:
                    lookup = original.casefold()

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
                            kind,
                            original,
                            replacement,
                            semantic_hash,
                        ),
                        identity_version=MUTATION_IDENTITY_VERSION,
                        relative_path=relative,
                        line=line_number,
                        column=match.start(),
                        kind=kind,
                        original_token=original,
                        replacement_token=replacement,
                        source_hash=source_hash,
                        canonical_source_hash=semantic_hash,
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
        ignore_case=True,
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
        ignore_case=True,
    )


def discover_contract_mutations(
    root: Path,
    contract: CoalContract,
) -> Tuple[MutationCandidate, ...]:
    if contract.mutation_strategy == "python-tokenize":
        return discover_python_mutations(root)

    candidates = []

    for rule in contract.mutation_rules:
        flags = re.IGNORECASE if rule.ignore_case else 0
        replacements = dict(rule.replacements)

        if rule.ignore_case:
            replacements = {
                key.casefold(): value
                for key, value in replacements.items()
            }

        candidates.extend(
            discover_text_mutations(
                root,
                set(contract.source_extensions),
                replacements,
                re.compile(rule.pattern, flags),
                rule.kind,
                ignore_case=rule.ignore_case,
            )
        )

    identities = {
        candidate.mutation_id
        for candidate in candidates
    }

    if len(identities) != len(candidates):
        raise RuntimeError(
            "coal mutation rules produced duplicate identities"
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


def discover_mutations(
    adapter: str,
    root: Path,
) -> Tuple[MutationCandidate, ...]:
    root = Path(root).resolve()
    contract = resolve_coal_contract(
        adapter,
        root,
    )

    if contract is not None:
        return discover_contract_mutations(
            root,
            contract,
        )

    raise RuntimeError(
        f"coal contract not found for adapter: {adapter}"
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
    timeout_seconds: float,
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
        timeout=timeout_seconds,
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
        timeout=timeout_seconds,
    )


def probe_health(
    port: int,
    deadline: float | None = None,
) -> int:
    url = (
        f"http://127.0.0.1:{port}/health"
    )

    for _ in range(40):
        if (
            deadline is not None
            and time.monotonic() >= deadline
        ):
            return 0

        request_timeout = 0.25

        if deadline is not None:
            request_timeout = max(
                0.01,
                min(
                    request_timeout,
                    deadline - time.monotonic(),
                ),
            )

        try:
            with urllib.request.urlopen(
                url,
                timeout=request_timeout,
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
    timeout_seconds: float,
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

    deadline = time.monotonic() + timeout_seconds

    status = 0

    for _ in range(40):
        if time.monotonic() >= deadline:
            break

        if process.poll() is not None:
            break

        status = probe_health(
            port,
            deadline,
        )

        if status:
            break

    if process.poll() is None:
        process.terminate()

    timed_out = time.monotonic() >= deadline
    remaining = max(
        0.01,
        deadline - time.monotonic(),
    )

    try:
        stdout, stderr = process.communicate(
            timeout=min(
                3,
                remaining,
            )
        )
    except subprocess.TimeoutExpired:
        process.kill()

        stdout, stderr = process.communicate(
            timeout=3
        )
        timed_out = True

    if timed_out:
        raise subprocess.TimeoutExpired(
            cmd=[
                sys.executable,
                str(target),
            ],
            timeout=timeout_seconds,
            output=stdout,
            stderr=stderr,
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
    timeout_seconds: float = DEFAULT_TEST_TIMEOUT_SECONDS,
):
    specimen = Path(
        specimen
    ).resolve()

    if timeout_seconds <= 0:
        raise ValueError(
            "test timeout must be positive"
        )

    environment = dict(
        os.environ
    )

    environment["PYTHONPATH"] = str(
        specimen
    )

    contract = resolve_coal_contract(
        adapter,
        specimen,
    )

    if contract is None:
        raise RuntimeError(
            f"coal contract not found for adapter: {adapter}"
        )

    environment.update({
        key: value.replace(
            "{specimen}",
            str(specimen),
        ).replace(
            "{entry}",
            entry,
        )
        for key, value in contract.execution.environment
    })

    driver = contract.execution.driver

    if driver == "python-unittest":
        return subprocess.run(
            python_command(entry),
            cwd=str(specimen),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )

    if driver == "npm-script":
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
            timeout=timeout_seconds,
        )

    if driver == "powershell-file":
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
            timeout=timeout_seconds,
        )

    if driver == "wsl2-shell":
        return run_wsl2_tests(
            specimen,
            entry,
            timeout_seconds,
        )

    if driver == "api-health":
        return run_api_service_tests(
            specimen,
            entry,
            timeout_seconds,
        )

    if driver == "command":
        return run_contract_tests(
            contract,
            specimen,
            entry,
            environment,
            timeout_seconds,
        )

    raise RuntimeError("coal execution driver is not implemented")


def expand_contract_command(
    command: Tuple[str, ...],
    specimen: Path,
    entry: str,
) -> list[str]:
    expanded = [
        token.replace(
            "{specimen}",
            str(specimen),
        ).replace(
            "{entry}",
            entry,
        )
        for token in command
    ]

    executable = expanded[0]

    if not any(
        separator in executable
        for separator in ("/", "\\")
    ):
        resolved = executable_path(executable)

        if not resolved:
            raise RuntimeError(
                "coal command executable is unavailable: "
                + executable
            )

        expanded[0] = resolved

    return expanded


def run_contract_tests(
    contract: CoalContract,
    specimen: Path,
    entry: str,
    environment: dict[str, str],
    timeout_seconds: float,
):
    deadline = time.monotonic() + timeout_seconds
    stdout_parts = []
    stderr_parts = []
    commands = list(
        contract.execution.rebuild_commands
    )
    test_command = list(
        contract.execution.test_command
    )

    if contract.execution.append_entry and entry:
        test_command.append(entry)

    commands.append(tuple(test_command))
    last_args = []

    for index, command in enumerate(commands):
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise subprocess.TimeoutExpired(
                cmd=last_args or list(command),
                timeout=timeout_seconds,
                output="".join(stdout_parts),
                stderr="".join(stderr_parts),
            )

        args = expand_contract_command(
            tuple(command),
            specimen,
            entry,
        )
        last_args = args
        result = subprocess.run(
            args,
            cwd=str(specimen),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=remaining,
        )
        stdout_parts.append(result.stdout or "")
        stderr_parts.append(result.stderr or "")

        if result.returncode != 0:
            output = "".join(stdout_parts) + "\n" + "".join(stderr_parts)
            final_test_command = index == len(commands) - 1
            proven_test_failure = bool(
                final_test_command
                and coal_failure_locations(contract, output)
                and coal_failure_test_ids(contract, output)
            )
            normalized_returncode = (
                1
                if proven_test_failure
                else 2
                if result.returncode == 1
                else result.returncode
            )
            return subprocess.CompletedProcess(
                args=args,
                returncode=normalized_returncode,
                stdout="".join(stdout_parts),
                stderr="".join(stderr_parts),
            )

    return subprocess.CompletedProcess(
        args=last_args,
        returncode=0,
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
    )
