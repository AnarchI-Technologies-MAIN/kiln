from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Tuple


SPECIMEN_MEMBERSHIP_VERSION = "KILN-SPECIMEN-MEMBERSHIP-1"

DEFAULT_EXCLUDED_DIRECTORY_NAMES = (
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "kiln-staging",
    "node_modules",
    "outputs",
    "proof-output",
    "proof-outputs",
    "release-output",
    "sandboxes",
    "sessions",
    "site-packages",
    "temp",
    "tmp",
    "training",
    "trial-output",
    "vendor",
    "vendors",
    "venv",
)

DEFAULT_EXCLUDED_DIRECTORY_PATTERNS = (
    "*.egg-info",
    ".kiln-*",
    "kiln-sandbox-*",
)


def normalize_specimen_path(path: str | Path) -> str:
    """Return one repository-relative spelling on Windows and POSIX."""
    normalized = PurePosixPath(
        str(path).replace(
            "\\",
            "/",
        )
    )

    if normalized.is_absolute():
        raise ValueError(
            "specimen membership path must be relative"
        )

    if ".." in normalized.parts:
        raise ValueError(
            "specimen membership path cannot escape proof root"
        )

    if normalized.parts and normalized.parts[0].endswith(
        ":"
    ):
        raise ValueError(
            "specimen membership path must not contain a drive"
        )

    value = normalized.as_posix()

    if value in ("", "."):
        return ""

    return value


def path_is_within(
    relative_path: str,
    declared_path: str,
) -> bool:
    relative = normalize_specimen_path(
        relative_path
    ).casefold()
    declared = normalize_specimen_path(
        declared_path
    ).casefold()

    return relative in (
        declared,
    ) or relative.startswith(
        f"{declared}/"
    )


@dataclass(frozen=True)
class SpecimenMembershipPolicy:
    """Content-based membership; Git index state is never consulted."""

    excluded_directory_names: Tuple[str, ...] = (
        DEFAULT_EXCLUDED_DIRECTORY_NAMES
    )
    excluded_directory_patterns: Tuple[str, ...] = (
        DEFAULT_EXCLUDED_DIRECTORY_PATTERNS
    )
    excluded_relative_paths: Tuple[str, ...] = ()
    included_relative_paths: Tuple[str, ...] = ()

    def includes(
        self,
        relative_path: str | Path,
    ) -> bool:
        relative = normalize_specimen_path(
            relative_path
        )

        if not relative:
            return bool()

        if any(
            path_is_within(
                relative,
                excluded,
            )
            for excluded in self.excluded_relative_paths
        ):
            return bool()

        if any(
            path_is_within(
                relative,
                included,
            )
            for included in self.included_relative_paths
        ):
            return bool(relative)

        directory_parts = PurePosixPath(
            relative
        ).parent.parts
        excluded_names = {
            name.casefold()
            for name in self.excluded_directory_names
        }

        if any(
            part.casefold() in excluded_names
            for part in directory_parts
        ):
            return bool()

        if any(
            fnmatchcase(
                part.casefold(),
                pattern.casefold(),
            )
            for part in directory_parts
            for pattern in self.excluded_directory_patterns
        ):
            return bool()

        return bool(relative)


DEFAULT_SPECIMEN_MEMBERSHIP = SpecimenMembershipPolicy()


def specimen_source_files(
    root: Path,
    extensions: Tuple[str, ...],
    membership_policy: SpecimenMembershipPolicy | None = None,
) -> Tuple[Path, ...]:
    """Enumerate declared specimen content independently of Git state."""
    root = Path(root).resolve()
    policy = (
        membership_policy
        or DEFAULT_SPECIMEN_MEMBERSHIP
    )
    eligible_extensions = {
        extension.casefold()
        for extension in extensions
    }
    paths = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.is_symlink():
            continue

        if path.suffix.casefold() not in eligible_extensions:
            continue

        relative = path.relative_to(
            root
        )

        if not policy.includes(
            relative
        ):
            continue

        paths.append(
            path
        )

    return tuple(
        sorted(
            paths,
            key=lambda path: (
                normalize_specimen_path(
                    path.relative_to(root)
                ).casefold(),
                normalize_specimen_path(
                    path.relative_to(root)
                ),
            ),
        )
    )
