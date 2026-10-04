from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple
import json
import re

from engine.coal_schemas import validate_schema_payload


COAL_CONTRACT_VERSION = "KILN-COAL-CONTRACT-1"
COAL_CONTRACT_SCHEMA = "kiln.coal-contract.v1"
COAL_CONTRACT_FILENAME = "kiln.coal.json"
COAL_HOUSE_PACKS_DIRECTORY = "packs"


_PLACEHOLDER = re.compile(r"{([^{}]+)}")
_FORBIDDEN_EXECUTABLES = {
    "del",
    "format",
    "git",
    "kubectl",
    "rm",
    "rmdir",
    "shutdown",
    "terraform",
}
_FORBIDDEN_SUBCOMMANDS = {
    "cargo": {"install", "publish"},
    "docker": {"push"},
    "dotnet": {"publish"},
    "gem": {"push"},
    "gradle": {"deploy", "publish", "release"},
    "mvn": {"deploy", "release"},
    "npm": {"publish"},
    "pnpm": {"publish"},
    "yarn": {"npm", "publish"},
}

# Allowlist of executables permitted for external coal contracts
# These are common build/test tools that are considered safe when used
# without shell/interpreter wrapper flags
_EXTERNAL_ALLOWED_EXECUTABLES = {
    "rscript",
    "bundle",
    "cabal",
    "cargo",
    "cmake",
    "composer",
    "ctest",
    "dart",
    "dotnet",
    "gcc",
    "go",
    "gradle",
    "javac",
    "make",
    "lua",
    "maven",
    "mvn",
    "mix",
    "node",
    "npm",
    "npx",
    "pnpm",
    "php",
    "pytest",
    "python",
    "python2",
    "python3",
    "ruby",
    "rustc",
    "swift",
    "yarn",
    "zig",
}

# Shell executables that can execute arbitrary code via wrapper flags
_SHELL_EXECUTABLES = {
    "ash",
    "bash",
    "cmd",
    "dash",
    "ksh",
    "sh",
    "zsh",
}

# Flags that enable arbitrary code execution in shells/interpreters
_ARBITRARY_EXECUTION_FLAGS = {
    "-c",      # shell/python/ruby command string
    "-e",      # perl/ruby one-liner
    "/c",      # cmd.exe command
    "/k",      # cmd.exe command (keep window open)
    "--eval",  # node.js eval
    "-Command", # PowerShell command
}


@dataclass(frozen=True)
class CoalMutationRule:
    kind: str
    pattern: str
    replacements: Tuple[tuple[str, str], ...]
    ignore_case: bool


@dataclass(frozen=True)
class CoalExecution:
    driver: str
    rebuild_commands: Tuple[Tuple[str, ...], ...]
    test_command: Tuple[str, ...]
    entry_kind: str
    append_entry: bool
    environment: Tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CoalProof:
    parser: str
    location_patterns: Tuple[str, ...]
    test_patterns: Tuple[str, ...]
    assertion_patterns: Tuple[str, ...]


@dataclass(frozen=True)
class CoalContract:
    schema: str
    contract_version: str
    adapter: str
    languages: Tuple[str, ...]
    source_extensions: Tuple[str, ...]
    mutation_strategy: str
    mutation_rules: Tuple[CoalMutationRule, ...]
    execution: CoalExecution
    proof: CoalProof
    origin: str


COMMON_BOOLEAN_REPLACEMENTS = (
    ("!==", "==="),
    ("===", "!=="),
    ("false", "true"),
    ("true", "false"),
    ("!=", "=="),
    ("==", "!="),
    ("&&", "||"),
    ("||", "&&"),
)


def builtin_contract_payloads() -> Mapping[str, dict]:
    return {
        "python": {
            "schema": COAL_CONTRACT_SCHEMA,
            "contractVersion": COAL_CONTRACT_VERSION,
            "adapter": "python",
            "languages": ["python"],
            "sourceExtensions": [".py"],
            "mutation": {
                "strategy": "python-tokenize",
                "rules": [],
            },
            "execution": {
                "driver": "python-unittest",
                "rebuildCommands": [],
                "testCommand": [],
                "entryKind": "path",
                "appendEntry": False,
                "environment": {},
            },
            "proof": {
                "parser": "python",
                "locationPatterns": [],
                "testPatterns": [],
                "assertionPatterns": [],
            },
        },
        "javascript": {
            "schema": COAL_CONTRACT_SCHEMA,
            "contractVersion": COAL_CONTRACT_VERSION,
            "adapter": "javascript",
            "languages": ["javascript", "typescript"],
            "sourceExtensions": [
                ".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx",
            ],
            "mutation": {
                "strategy": "text-rules",
                "rules": [
                    {
                        "kind": "JAVASCRIPT_TOKEN_REPLACEMENT",
                        "pattern": (
                            r"\btrue\b|\bfalse\b|!==|===|==|!=|&&|\|\|"
                        ),
                        "replacements": dict(COMMON_BOOLEAN_REPLACEMENTS),
                        "ignoreCase": False,
                    },
                ],
            },
            "execution": {
                "driver": "npm-script",
                "rebuildCommands": [],
                "testCommand": [],
                "entryKind": "script",
                "appendEntry": False,
                "environment": {},
            },
            "proof": {
                "parser": "javascript",
                "locationPatterns": [],
                "testPatterns": [],
                "assertionPatterns": [
                    r"\bassert(?:\.[A-Za-z_$][\w$]*)?\s*\(",
                    r"\bexpect\s*\(",
                ],
            },
        },
        "powershell": {
            "schema": COAL_CONTRACT_SCHEMA,
            "contractVersion": COAL_CONTRACT_VERSION,
            "adapter": "powershell",
            "languages": ["powershell"],
            "sourceExtensions": [".ps1", ".psm1"],
            "mutation": {
                "strategy": "text-rules",
                "rules": [
                    {
                        "kind": "POWERSHELL_TOKEN_REPLACEMENT",
                        "pattern": (
                            r"\$true\b|\$false\b|-eq\b|-ne\b|-lt\b|"
                            r"-le\b|-gt\b|-ge\b"
                        ),
                        "replacements": {
                            "$true": "$false",
                            "$false": "$true",
                            "-eq": "-ne",
                            "-ne": "-eq",
                            "-lt": "-ge",
                            "-ge": "-lt",
                            "-le": "-gt",
                            "-gt": "-le",
                        },
                        "ignoreCase": True,
                    },
                ],
            },
            "execution": {
                "driver": "powershell-file",
                "rebuildCommands": [],
                "testCommand": [],
                "entryKind": "path",
                "appendEntry": False,
                "environment": {},
            },
            "proof": {
                "parser": "generic",
                "locationPatterns": [
                    (
                        r"(?P<path>(?:[A-Za-z]:[\\/]|/)[^:\r\n]+?"
                        r"\.(?:ps1|psm1)):\s*line\s+(?P<line>\d+)"
                    ),
                ],
                "testPatterns": [],
                "assertionPatterns": [
                    r"\bAssert-",
                    r"\bShould\b",
                ],
            },
        },
        "wsl2": {
            "schema": COAL_CONTRACT_SCHEMA,
            "contractVersion": COAL_CONTRACT_VERSION,
            "adapter": "wsl2",
            "languages": ["shell"],
            "sourceExtensions": [".bash", ".sh"],
            "mutation": {
                "strategy": "text-rules",
                "rules": [
                    {
                        "kind": "WSL2_SHELL_TOKEN_REPLACEMENT",
                        "pattern": (
                            r"\btrue\b|\bfalse\b|-eq\b|-ne\b|-lt\b|"
                            r"-le\b|-gt\b|-ge\b"
                        ),
                        "replacements": {
                            "true": "false",
                            "false": "true",
                            "-eq": "-ne",
                            "-ne": "-eq",
                            "-lt": "-ge",
                            "-ge": "-lt",
                            "-le": "-gt",
                            "-gt": "-le",
                        },
                        "ignoreCase": True,
                    },
                ],
            },
            "execution": {
                "driver": "wsl2-shell",
                "rebuildCommands": [],
                "testCommand": [],
                "entryKind": "path",
                "appendEntry": False,
                "environment": {},
            },
            "proof": {
                "parser": "generic",
                "locationPatterns": [
                    r"(?P<path>[^:\r\n]+\.(?:bash|sh)):(?P<line>\d+)",
                ],
                "testPatterns": [],
                "assertionPatterns": [
                    r"\[\[?",
                    r"\btest\b",
                ],
            },
        },
        "api-service": {
            "schema": COAL_CONTRACT_SCHEMA,
            "contractVersion": COAL_CONTRACT_VERSION,
            "adapter": "api-service",
            "languages": ["python"],
            "sourceExtensions": [".py"],
            "mutation": {
                "strategy": "python-tokenize",
                "rules": [],
            },
            "execution": {
                "driver": "api-health",
                "rebuildCommands": [],
                "testCommand": [],
                "entryKind": "path",
                "appendEntry": False,
                "environment": {},
            },
            "proof": {
                "parser": "python",
                "locationPatterns": [],
                "testPatterns": [],
                "assertionPatterns": [],
            },
        },
    }


def _canonical_strings(
    value,
    field: str,
) -> Tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, str)
            or not item
            or "\0" in item
            for item in value
        )
        or value != sorted(set(value))
    ):
        raise RuntimeError(
            "coal contract field must be a canonical string list: "
            + field
        )

    return tuple(value)


def _exact_keys(
    value: dict,
    expected: set[str],
    field: str,
) -> None:
    if set(value) != expected:
        raise RuntimeError(
            "coal contract fields are incomplete or unknown: "
            + field
        )


def _command(
    value,
    field: str,
    allow_empty: bool = False,
) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(
            "coal contract command must be a token array: "
            + field
        )

    if not value and allow_empty:
        return ()

    if (
        not value
        or any(
            not isinstance(item, str)
            or not item
            or "\0" in item
            or "\r" in item
            or "\n" in item
            for item in value
        )
    ):
        raise RuntimeError(
            "coal contract command contains invalid tokens: "
            + field
        )

    return tuple(value)


def _validate_template(
    value: str,
    field: str,
) -> None:
    allowed = {"entry", "specimen"}
    placeholders = set(_PLACEHOLDER.findall(value))
    remainder = _PLACEHOLDER.sub("", value)

    if "{" in remainder or "}" in remainder:
        raise RuntimeError(
            "coal template contains malformed placeholders: " + field
        )

    if placeholders - allowed:
        raise RuntimeError(
            "coal template uses an unknown placeholder: " + field
        )


def _command_executable_name(command: Tuple[str, ...]) -> str:
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1]
    return executable.casefold().removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")


def _validate_command_authority(
    command: Tuple[str, ...],
    field: str,
    external: bool = False,
) -> None:
    executable = _command_executable_name(command)
    lowered_tokens = {
        token.casefold()
        for token in command[1:]
        if token and not token.startswith("-")
    }

    if executable in _FORBIDDEN_EXECUTABLES:
        raise RuntimeError(
            "coal command requests forbidden destructive or repository authority: "
            + field
        )

    forbidden = _FORBIDDEN_SUBCOMMANDS.get(executable, set())

    if lowered_tokens & forbidden:
        raise RuntimeError(
            "coal command requests forbidden promotion or deployment authority: "
            + field
        )

    # Additional validation for external contracts
    if external:
        if executable in _SHELL_EXECUTABLES:
            raise RuntimeError(
                "coal command uses a shell executable that can bypass validation: "
                + field + " (executable: " + executable + ")"
            )
        # Enforce allowlist: only permit known safe executables
        if executable not in _EXTERNAL_ALLOWED_EXECUTABLES:
            raise RuntimeError(
                "coal command uses a non-allowlisted executable for external contracts: "
                + field
                + " (executable: "
                + executable
                + ")"
            )

        # Check for arbitrary execution flags in any position
        for token in command[1:]:
            token_lower = token.casefold()
            # Check exact matches and case-insensitive matches for flags
            if token in _ARBITRARY_EXECUTION_FLAGS or token_lower in {
                flag.casefold() for flag in _ARBITRARY_EXECUTION_FLAGS
            }:
                raise RuntimeError(
                    "coal command uses a flag that enables arbitrary code execution: "
                    + field
                    + " (flag: "
                    + token
                    + ")"
                )


def validate_coal_contract_payload(
    payload: dict,
    origin: str = "",
    external: bool = False,
) -> CoalContract:
    if not isinstance(payload, dict):
        raise RuntimeError("coal contract must be an object")

    if (
        payload.get("schema") != COAL_CONTRACT_SCHEMA
        or payload.get("contractVersion")
        != COAL_CONTRACT_VERSION
    ):
        raise RuntimeError("coal contract uses an unsupported schema")

    adapter = payload.get("adapter")

    _exact_keys(
        payload,
        {
            "adapter",
            "contractVersion",
            "execution",
            "languages",
            "mutation",
            "proof",
            "schema",
            "sourceExtensions",
        },
        "root",
    )

    if (
        not isinstance(adapter, str)
        or re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", adapter)
        is None
    ):
        raise RuntimeError("coal contract adapter name is invalid")

    languages = _canonical_strings(
        payload.get("languages"),
        "languages",
    )
    extensions = _canonical_strings(
        payload.get("sourceExtensions"),
        "sourceExtensions",
    )

    if not languages or not extensions:
        raise RuntimeError(
            "coal contract needs languages and source extensions"
        )

    if any(
        not item.startswith(".")
        or "/" in item
        or "\\" in item
        for item in extensions
    ):
        raise RuntimeError("coal source extension is invalid")

    mutation = payload.get("mutation")
    execution = payload.get("execution")
    proof = payload.get("proof")

    if not all(
        isinstance(item, dict)
        for item in (mutation, execution, proof)
    ):
        raise RuntimeError("coal contract sections are incomplete")

    _exact_keys(
        mutation,
        {"rules", "strategy"},
        "mutation",
    )
    _exact_keys(
        execution,
        {
            "appendEntry",
            "driver",
            "entryKind",
            "environment",
            "rebuildCommands",
            "testCommand",
        },
        "execution",
    )
    _exact_keys(
        proof,
        {
            "assertionPatterns",
            "locationPatterns",
            "parser",
            "testPatterns",
        },
        "proof",
    )

    strategy = mutation.get("strategy")

    if strategy not in {"python-tokenize", "text-rules"}:
        raise RuntimeError("coal mutation strategy is invalid")

    if external and strategy != "text-rules":
        raise RuntimeError(
            "repository coal contracts must use text-rules"
        )

    raw_rules = mutation.get("rules")

    if not isinstance(raw_rules, list):
        raise RuntimeError("coal mutation rules must be an array")

    rules = []

    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise RuntimeError("coal mutation rule must be an object")

        if not set(raw).issubset({
            "ignoreCase",
            "kind",
            "pattern",
            "replacements",
        }) or not {
            "kind",
            "pattern",
            "replacements",
        }.issubset(raw):
            raise RuntimeError(
                "coal mutation rule fields are incomplete or unknown"
            )

        kind = raw.get("kind")
        pattern = raw.get("pattern")
        replacements = raw.get("replacements")
        ignore_case = raw.get("ignoreCase", False)

        if (
            not isinstance(kind, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", kind) is None
            or not isinstance(pattern, str)
            or not pattern
            or not isinstance(replacements, dict)
            or not replacements
            or not isinstance(ignore_case, bool)
            or any(
                not isinstance(key, str)
                or not key
                or not isinstance(value, str)
                or not value
                or key == value
                for key, value in replacements.items()
            )
        ):
            raise RuntimeError("coal mutation rule is invalid")

        try:
            re.compile(
                pattern,
                re.IGNORECASE if ignore_case else 0,
            )
        except re.error as error:
            raise RuntimeError(
                "coal mutation pattern is invalid: " + str(error)
            ) from error

        rules.append(
            CoalMutationRule(
                kind=kind,
                pattern=pattern,
                replacements=tuple(
                    sorted(replacements.items())
                ),
                ignore_case=ignore_case,
            )
        )

    if len({rule.kind for rule in rules}) != len(rules):
        raise RuntimeError("coal mutation rule kinds must be unique")

    if strategy == "text-rules" and not rules:
        raise RuntimeError("text-rule coal has no mutation rules")

    driver = execution.get("driver")

    if driver not in {
        "api-health",
        "command",
        "npm-script",
        "powershell-file",
        "python-unittest",
        "wsl2-shell",
    }:
        raise RuntimeError("coal execution driver is invalid")

    if external and driver != "command":
        raise RuntimeError(
            "repository coal contracts must use the command driver"
        )

    raw_rebuild = execution.get("rebuildCommands")

    if not isinstance(raw_rebuild, list):
        raise RuntimeError("coal rebuild commands must be an array")

    rebuild_commands = tuple(
        _command(item, "rebuildCommands")
        for item in raw_rebuild
    )
    test_command = _command(
        execution.get("testCommand"),
        "testCommand",
        allow_empty=driver != "command",
    )

    if driver == "command" and not test_command:
        raise RuntimeError("command coal has no test command")

    entry_kind = execution.get("entryKind")

    if entry_kind not in {"none", "opaque", "path", "script"}:
        raise RuntimeError("coal entry kind is invalid")

    if external and entry_kind == "script":
        raise RuntimeError(
            "repository coal contracts cannot use the reserved script entry kind"
        )

    append_entry = execution.get("appendEntry", False)

    if not isinstance(append_entry, bool):
        raise RuntimeError("coal appendEntry must be boolean")

    environment = execution.get("environment")

    if (
        not isinstance(environment, dict)
        or any(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None
            or not isinstance(value, str)
            or "\0" in value
            or "\r" in value
            or "\n" in value
            for key, value in environment.items()
        )
    ):
        raise RuntimeError("coal environment is invalid")

    if external and any(
        key.upper().startswith("KILN_")
        for key in environment
    ):
        raise RuntimeError(
            "repository coal cannot override Kiln control variables"
        )

    commands = (*rebuild_commands, test_command)

    for index, command in enumerate(commands):
        field = (
            f"execution.rebuildCommands[{index}]"
            if index < len(rebuild_commands)
            else "execution.testCommand"
        )

        if external:
            _validate_command_authority(command, field, external=True)

        for token in command:
            _validate_template(token, field)

    for key, value in environment.items():
        _validate_template(value, "execution.environment." + key)

    entry_referenced = any(
        "{entry}" in token
        for command in commands
        for token in command
    ) or any(
        "{entry}" in value
        for value in environment.values()
    )

    if external and entry_kind == "none" and (
        append_entry or entry_referenced
    ):
        raise RuntimeError(
            "coal entryKind none cannot consume or append an entry"
        )

    parser = proof.get("parser")

    if parser not in {"generic", "javascript", "python"}:
        raise RuntimeError("coal proof parser is invalid")

    if external and parser != "generic":
        raise RuntimeError(
            "repository coal contracts must use the generic proof parser"
        )

    location_patterns = _canonical_strings(
        proof.get("locationPatterns"),
        "proof.locationPatterns",
    )
    test_patterns = _canonical_strings(
        proof.get("testPatterns"),
        "proof.testPatterns",
    )
    assertion_patterns = _canonical_strings(
        proof.get("assertionPatterns"),
        "proof.assertionPatterns",
    )

    for pattern in location_patterns:
        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error as error:
            raise RuntimeError(
                "coal proof location pattern is invalid: " + str(error)
            ) from error

        if not {"path", "line"}.issubset(compiled.groupindex):
            raise RuntimeError(
                "coal proof location pattern needs path and line groups"
            )

    for field, patterns, group in (
        ("test", test_patterns, "test"),
        ("assertion", assertion_patterns, ""),
    ):
        for pattern in patterns:
            try:
                compiled = re.compile(pattern, re.MULTILINE)
            except re.error as error:
                raise RuntimeError(
                    f"coal proof {field} pattern is invalid: " + str(error)
                ) from error

            if group and group not in compiled.groupindex:
                raise RuntimeError(
                    f"coal proof {field} pattern needs a {group} group"
                )

    contract = CoalContract(
        schema=COAL_CONTRACT_SCHEMA,
        contract_version=COAL_CONTRACT_VERSION,
        adapter=adapter,
        languages=languages,
        source_extensions=extensions,
        mutation_strategy=strategy,
        mutation_rules=tuple(
            sorted(rules, key=lambda item: item.kind)
        ),
        execution=CoalExecution(
            driver=driver,
            rebuild_commands=rebuild_commands,
            test_command=test_command,
            entry_kind=entry_kind,
            append_entry=append_entry,
            environment=tuple(sorted(environment.items())),
        ),
        proof=CoalProof(
            parser=parser,
            location_patterns=location_patterns,
            test_patterns=test_patterns,
            assertion_patterns=assertion_patterns,
        ),
        origin=origin,
    )

    if external:
        validate_schema_payload(
            "kiln.coal-contract.v1.schema.json",
            payload,
            "coal contract",
        )

    return contract


def builtin_coal_contracts() -> Mapping[str, CoalContract]:
    return {
        name: validate_coal_contract_payload(
            payload,
            origin="builtin:" + name,
        )
        for name, payload in builtin_contract_payloads().items()
    }


def coal_house_contracts() -> Mapping[str, CoalContract]:
    """Discover packaged coal contracts without imposing a language allowlist."""
    from coal_house import coal_house_root

    packs_root = coal_house_root() / COAL_HOUSE_PACKS_DIRECTORY

    if not packs_root.is_dir():
        return {}

    contracts = {}

    for pack_root in sorted(
        (path for path in packs_root.iterdir() if path.is_dir()),
        key=lambda path: (path.name.casefold(), path.name),
    ):
        contract_path = pack_root / COAL_CONTRACT_FILENAME

        if not contract_path.is_file():
            raise RuntimeError(
                "coal-house pack is missing kiln.coal.json: " + pack_root.name
            )

        try:
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "coal-house contract is unreadable: " + pack_root.name
            ) from error

        contract = validate_coal_contract_payload(
            payload,
            origin="coal-house:" + pack_root.name,
            external=True,
        )

        if contract.adapter != pack_root.name:
            raise RuntimeError(
                "coal-house directory does not match adapter: " + pack_root.name
            )

        if contract.adapter in contracts:
            raise RuntimeError(
                "coal-house contains a duplicate adapter: " + contract.adapter
            )

        contracts[contract.adapter] = contract

    return contracts


def repository_coal_contract(
    root: Path,
) -> CoalContract | None:
    path = Path(root).resolve() / COAL_CONTRACT_FILENAME

    if not path.is_file():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "repository coal contract is unreadable: " + str(error)
        ) from error

    return validate_coal_contract_payload(
        payload,
        origin=COAL_CONTRACT_FILENAME,
        external=True,
    )


def resolve_coal_contract(
    adapter: str,
    root: Path,
) -> CoalContract | None:
    # Adaptive selection uses only the target's validated declaration.
    # Missing declarations must not silently select a generic test environment.
    if adapter == "auto":
        return repository_coal_contract(root)

    builtins = builtin_coal_contracts()

    if adapter in builtins:
        return builtins[adapter]

    external = repository_coal_contract(root)

    if external is not None and external.adapter == adapter:
        return external

    library = coal_house_contracts()

    if adapter in library:
        return library[adapter]

    return None


def available_coal_adapters(
    root: Path | None = None,
) -> Tuple[str, ...]:
    names = list(builtin_coal_contracts())

    for name in coal_house_contracts():
        if name not in names:
            names.append(name)

    if root is not None:
        external = repository_coal_contract(root)

        if (
            external is not None
            and external.adapter not in names
        ):
            names.append(external.adapter)

    return tuple(sorted(names))


def coal_failure_locations(
    contract: CoalContract,
    output: str,
) -> Tuple[tuple[str, int], ...]:
    locations = set()

    for pattern in contract.proof.location_patterns:
        for match in re.finditer(pattern, output, re.MULTILINE):
            locations.add((
                match.group("path"),
                int(match.group("line")),
            ))

    return tuple(sorted(locations))


def coal_failure_test_ids(
    contract: CoalContract,
    output: str,
) -> Tuple[str, ...]:
    tests = set()

    for pattern in contract.proof.test_patterns:
        for match in re.finditer(pattern, output, re.MULTILINE):
            tests.add(match.group("test"))

    return tuple(sorted(tests))


def coal_assertion_matches(
    contract: CoalContract,
    source_text: str,
) -> bool:
    return any(
        re.search(pattern, source_text, re.MULTILINE) is not None
        for pattern in contract.proof.assertion_patterns
    )
