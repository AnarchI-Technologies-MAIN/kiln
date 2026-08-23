from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from string import Formatter
from typing import Mapping, Tuple
import json
import re

from coal_house import coal_house_root
from engine.coal_schemas import validate_schema_payload


COAL_VENV_SCHEMA = "kiln.coal-venv.v1"
COAL_VENVS_DIRECTORY = "venvs"

_ADAPTER_NAME = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDERS = {"entry", "specimen"}


@dataclass(frozen=True)
class CoalVenvAdapter:
    """A non-executing plan for a specimen-local runtime environment."""

    adapter: str
    root: Path
    directories: Tuple[str, ...]
    environment: Tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MaterializedCoalVenv:
    adapter: str
    specimen: Path
    directories: Tuple[Path, ...]
    environment: Tuple[tuple[str, str], ...]


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("coal venv adapter is unreadable: " + str(path)) from error

    if not isinstance(value, dict):
        raise RuntimeError("coal venv adapter must be an object: " + str(path))

    return value


def _validate_template(value: str, field: str) -> None:
    if any(character in value for character in ("\0", "\r", "\n")):
        raise RuntimeError("coal venv value contains forbidden characters: " + field)

    try:
        parsed = tuple(Formatter().parse(value))
    except ValueError as error:
        raise RuntimeError("coal venv value has malformed placeholders: " + field) from error

    for _, name, format_spec, conversion in parsed:
        if name is None:
            continue

        if name not in _PLACEHOLDERS or format_spec or conversion:
            raise RuntimeError("coal venv value has invalid placeholders: " + field)


def validate_coal_venv_payload(
    payload: Mapping,
    *,
    origin: Path | None = None,
) -> CoalVenvAdapter:
    if not isinstance(payload, dict) or set(payload) != {
        "adapter",
        "directories",
        "environment",
        "schema",
    }:
        raise RuntimeError("coal venv adapter contains incomplete or unknown fields")

    if payload.get("schema") != COAL_VENV_SCHEMA:
        raise RuntimeError("coal venv adapter uses an unsupported schema")

    adapter = payload.get("adapter")

    if not isinstance(adapter, str) or _ADAPTER_NAME.fullmatch(adapter) is None:
        raise RuntimeError("coal venv adapter identity is invalid")

    directories = payload.get("directories")

    if (
        not isinstance(directories, list)
        or not directories
        or directories != sorted(set(directories))
    ):
        raise RuntimeError("coal venv directories must be a canonical non-empty list")

    for directory in directories:
        path = PurePosixPath(directory) if isinstance(directory, str) else None

        if (
            path is None
            or not directory
            or "\\" in directory
            or directory.startswith("/")
            or path.is_absolute()
            or "." in path.parts
            or ".." in path.parts
            or path.as_posix() != directory
        ):
            raise RuntimeError("coal venv directory escaped its specimen")

    environment = payload.get("environment")

    if not isinstance(environment, dict) or list(environment) != sorted(environment):
        raise RuntimeError("coal venv environment must be a canonical object")

    normalized_environment = []

    for name, value in environment.items():
        if (
            not isinstance(name, str)
            or _ENVIRONMENT_NAME.fullmatch(name) is None
            or name.casefold().startswith("kiln_")
        ):
            raise RuntimeError("coal venv environment name is forbidden: " + str(name))

        if not isinstance(value, str):
            raise RuntimeError("coal venv environment value must be a string: " + name)

        _validate_template(value, "environment." + name)
        normalized_environment.append((name, value))

    root = Path(origin).resolve() if origin is not None else Path()

    if origin is not None and root.stem != adapter:
        raise RuntimeError("coal venv adapter identity does not match its filename")

    validate_schema_payload(
        "kiln.coal-venv.v1.schema.json",
        payload,
        "coal venv adapter",
    )

    return CoalVenvAdapter(
        adapter=adapter,
        root=root,
        directories=tuple(directories),
        environment=tuple(normalized_environment),
    )


def discover_coal_venvs(root: Path | None = None) -> Tuple[CoalVenvAdapter, ...]:
    venv_root = (
        Path(root).resolve()
        if root is not None
        else coal_house_root() / COAL_VENVS_DIRECTORY
    )

    if not venv_root.is_dir():
        return ()

    adapters = tuple(
        validate_coal_venv_payload(_read_json(path), origin=path)
        for path in sorted(
            (item for item in venv_root.iterdir() if item.is_file() and item.suffix == ".json"),
            key=lambda item: (item.name.casefold(), item.name),
        )
    )

    names = tuple(adapter.adapter for adapter in adapters)

    if len(names) != len(set(names)):
        raise RuntimeError("coal venv adapter identities are not unique")

    return adapters


def coal_venv_adapter(adapter: str, root: Path | None = None) -> CoalVenvAdapter:
    matches = tuple(item for item in discover_coal_venvs(root) if item.adapter == adapter)

    if len(matches) != 1:
        raise RuntimeError("coal venv adapter not found: " + adapter)

    return matches[0]


def materialize_coal_venv(
    adapter: CoalVenvAdapter,
    specimen: Path,
    entry: str = "",
) -> MaterializedCoalVenv:
    """Create declared directories only below a specimen and return its environment."""
    specimen = Path(specimen).resolve()

    if not specimen.is_dir():
        raise RuntimeError("coal venv specimen must be an existing directory")

    directories = []

    for relative in adapter.directories:
        destination = (specimen / Path(*PurePosixPath(relative).parts)).resolve()

        try:
            destination.relative_to(specimen)
        except ValueError as error:
            raise RuntimeError("coal venv directory escaped its specimen") from error

        destination.mkdir(parents=True, exist_ok=True)
        directories.append(destination)

    environment = tuple(
        (
            name,
            value.replace("{specimen}", str(specimen)).replace("{entry}", entry),
        )
        for name, value in adapter.environment
    )
    return MaterializedCoalVenv(
        adapter=adapter.adapter,
        specimen=specimen,
        directories=tuple(directories),
        environment=environment,
    )
