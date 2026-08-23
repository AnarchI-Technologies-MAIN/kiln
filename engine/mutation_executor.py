from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import io
import tokenize

from engine.specimen_membership import (
    SpecimenMembershipPolicy,
    normalize_specimen_path,
    specimen_source_files,
)


TOKEN_MUTATIONS = {
    "True": "False",
    "False": "True",
    "==": "!=",
    "!=": "==",
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "+": "-",
    "-": "+",
}


MUTATION_IDENTITY_VERSION = "KILN-MUTATION-IDENTITY-2"


@dataclass(frozen=True)
class MutationCandidate:
    mutation_id: str
    identity_version: str
    relative_path: str
    line: int
    column: int
    kind: str
    original_token: str
    replacement_token: str
    source_hash: str
    canonical_source_hash: str


@dataclass(frozen=True)
class MutationApplication:
    mutation_id: str
    relative_path: str
    applied: bool
    original_hash: str
    mutated_hash: str
    disposition: str


def file_hash(path: Path) -> str:
    return sha256(
        path.read_bytes()
    ).hexdigest()


def canonical_source_hash(path: Path) -> str:
    """Hash semantic text with repository-independent line endings."""
    text = Path(path).read_text(
        encoding="utf-8"
    )

    normalized = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    return sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def mutation_identity(
    relative_path: str,
    line: int,
    column: int,
    kind: str,
    original_token: str,
    replacement_token: str,
    canonical_hash: str,
) -> str:
    material = "\0".join((
        MUTATION_IDENTITY_VERSION,
        relative_path,
        str(line),
        str(column),
        kind,
        original_token,
        replacement_token,
        canonical_hash,
    ))

    return (
        "KILN-MUTATION-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def mutation_source_files(
    root: Path,
    extensions: Tuple[str, ...],
    membership_policy: SpecimenMembershipPolicy | None = None,
) -> Tuple[Path, ...]:
    """Enumerate declared specimen content independently of Git state."""
    root = Path(root).resolve()
    paths = specimen_source_files(
        root,
        extensions,
        membership_policy,
    )

    if len(paths) != len(
        set(paths)
    ):
        raise RuntimeError(
            "specimen membership produced duplicate paths"
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
            reverse=False,
        )
    )


def discover_python_mutations(
    root: Path,
    membership_policy: SpecimenMembershipPolicy | None = None,
) -> Tuple[MutationCandidate, ...]:
    root = Path(root).resolve()
    candidates = []

    files = tuple(
        path
        for path in mutation_source_files(
            root,
            (".py",),
            membership_policy,
        )
        if "tests" not in {
            part.lower()
            for part in path.relative_to(root).parts
        }
        and not path.name.lower().startswith("test_")
    )

    for path in files:
        relative = path.relative_to(root).as_posix()
        content = path.read_text(
            encoding="utf-8"
        )
        source_hash = file_hash(
            path
        )

        semantic_hash = canonical_source_hash(
            path
        )

        stream = io.StringIO(
            content
        ).readline

        for token in tokenize.generate_tokens(stream):
            original = token.string

            if original not in TOKEN_MUTATIONS:
                continue

            replacement = TOKEN_MUTATIONS[
                original
            ]

            kind = "TOKEN_REPLACEMENT"

            candidates.append(
                    MutationCandidate(
                        mutation_id=mutation_identity(
                            relative,
                            token.start[0],
                            token.start[1],
                            kind,
                            original,
                            replacement,
                            semantic_hash,
                        ),
                        identity_version=MUTATION_IDENTITY_VERSION,
                        relative_path=relative,
                        line=token.start[0],
                        column=token.start[1],
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


def apply_mutation(
    root: Path,
    candidate: MutationCandidate,
) -> MutationApplication:
    root = Path(root).resolve()
    path = (
        root
        / candidate.relative_path
    ).resolve()

    try:
        path.relative_to(root)
    except ValueError:
        raise RuntimeError(
            "mutation path escaped specimen"
        )

    if not path.exists():
        raise RuntimeError(
            "mutation source file is missing"
        )

    original_hash = file_hash(
        path
    )

    if original_hash != candidate.source_hash:
        raise RuntimeError(
            "mutation source drift detected"
        )

    lines = path.read_text(
        encoding="utf-8"
    ).splitlines(
        keepends=True
    )

    if candidate.line < 1:
        raise RuntimeError(
            "invalid mutation line"
        )

    if candidate.line > len(lines):
        raise RuntimeError(
            "mutation line exceeds source"
        )

    index = candidate.line - 1
    line = lines[index]
    start = candidate.column
    end = start + len(
        candidate.original_token
    )

    if line[start:end] != candidate.original_token:
        raise RuntimeError(
            "mutation token no longer matches source"
        )

    lines[index] = (
        line[:start]
        + candidate.replacement_token
        + line[end:]
    )

    path.write_text(
        "".join(lines),
        encoding="utf-8",
        newline="",
    )

    mutated_hash = file_hash(
        path
    )

    applied = (
        mutated_hash != original_hash
    )

    disposition = "MUTATION_APPLIED"

    if not applied:
        disposition = "MUTATION_NO_EFFECT"

    return MutationApplication(
        mutation_id=candidate.mutation_id,
        relative_path=candidate.relative_path,
        applied=applied,
        original_hash=original_hash,
        mutated_hash=mutated_hash,
        disposition=disposition,
    )
