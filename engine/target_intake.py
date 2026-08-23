from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple
import csv
import subprocess


MANIFEST_NAMES = {
    "CMakeLists.txt",
    "Cargo.toml",
    "DESCRIPTION",
    "Dockerfile",
    "Gemfile",
    "Makefile",
    "Package.swift",
    "Package.resolved",
    "build.gradle",
    "build.gradle.kts",
    "build.zig",
    "cabal.project",
    "composer.json",
    "deno.json",
    "deno.jsonc",
    "go.work",
    "go.mod",
    "kiln.coal.json",
    "mix.exs",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "pubspec.lock",
    "pubspec.yaml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}


MANIFEST_SUFFIXES = {
    ".cabal",
    ".csproj",
    ".fsproj",
    ".sln",
    ".vbproj",
}


LANGUAGE_BY_SUFFIX = {
    ".c": "c",
    ".cc": "cpp",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".dart": "dart",
    ".erl": "erlang",
    ".ex": "elixir",
    ".exs": "elixir",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".go": "go",
    ".groovy": "groovy",
    ".h": "c",
    ".hpp": "cpp",
    ".hs": "haskell",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lhs": "haskell",
    ".lua": "lua",
    ".mjs": "javascript",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".nim": "nim",
    ".pl": "perl",
    ".pm": "perl",
    ".php": "php",
    ".ps1": "powershell",
    ".py": "python",
    ".r": "r",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".sol": "solidity",
    ".sql": "sql",
    ".svelte": "svelte",
    ".swift": "swift",
    ".tcl": "tcl",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vb": "visual-basic",
    ".vue": "vue",
    ".zig": "zig",
}


@dataclass(frozen=True)
class TargetIdentity:
    target_id: str
    target_kind: str
    source_location: str
    repository_root: str
    git_repository: bool
    source_commit: str
    repository_clean: bool
    local_or_remote: str
    language_hints: Tuple[str, ...]
    manifest_hints: Tuple[str, ...]
    target_fingerprint: str
    disposition: str


def git(path: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def is_remote_target(value: str) -> bool:
    lowered = value.strip().lower()

    return (
        lowered.startswith("https://")
        or lowered.startswith("http://")
        or lowered.startswith("ssh://")
        or lowered.startswith("git://")
        or lowered.startswith("file://")
        or value.strip().startswith("git@")
    )


def discover_hints(root: Path):
    languages = set()
    manifests = set()

    excluded_parts = {
        ".git",
        ".venv",
        "dist",
        "build",
        "node_modules",
        "vendor",
        "__pycache__",
    }

    for path in root.rglob("*"):
        if any(
            part in excluded_parts
            for part in path.parts
        ):
            continue

        if not path.is_file():
            continue

        language = LANGUAGE_BY_SUFFIX.get(
            path.suffix.lower()
        )

        if language:
            languages.add(language)

        if (
            path.name in MANIFEST_NAMES
            or path.suffix.lower() in MANIFEST_SUFFIXES
        ):
            manifests.add(
                path.relative_to(root).as_posix()
            )

    return (
        tuple(sorted(languages)),
        tuple(sorted(manifests)),
    )


def directory_fingerprint(root: Path):
    digest = sha256()

    files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and ".git" not in item.parts
    )

    for path in sorted(
        files,
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()

        digest.update(
            relative.encode("utf-8")
        )

        digest.update(b"\0")

        digest.update(
            sha256(
                path.read_bytes()
            ).digest()
        )

    return digest.hexdigest()


def git_identity(
    root: Path,
    source_location: str,
    target_kind: str,
    local_or_remote: str,
):
    head = git(
        root,
        "rev-parse",
        "HEAD",
    )

    if head.returncode != 0:
        raise RuntimeError(
            "unable to resolve Git source revision"
        )

    source_commit = head.stdout.strip()

    status = git(
        root,
        "status",
        "--porcelain",
    )

    if status.returncode != 0:
        raise RuntimeError(
            "unable to inspect Git repository state"
        )

    repository_clean = not bool(
        status.stdout.strip()
    )

    languages, manifests = discover_hints(
        root
    )

    diff = git(
        root,
        "diff",
        "HEAD",
        "--binary",
    )

    if diff.returncode != 0:
        raise RuntimeError(
            "unable to fingerprint Git working tree"
        )

    untracked = git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )

    if untracked.returncode != 0:
        raise RuntimeError(
            "unable to fingerprint untracked Git files"
        )

    worktree = sha256()
    worktree.update(source_commit.encode("utf-8"))
    worktree.update(b"\0")
    worktree.update(diff.stdout.encode("utf-8"))

    for relative in sorted(
        item
        for item in untracked.stdout.split("\0")
        if item
    ):
        path = root / relative

        worktree.update(relative.encode("utf-8"))
        worktree.update(b"\0")

        if path.is_file():
            worktree.update(
                sha256(path.read_bytes()).digest()
            )

    fingerprint = worktree.hexdigest()

    identity_source = (
        f"{target_kind}\0"
        f"{source_location}\0"
        f"{source_commit}\0"
        f"{fingerprint}"
    )

    target_id = (
        "KILN-TARGET-"
        + sha256(
            identity_source.encode("utf-8")
        ).hexdigest()[:16].upper()
    )

    return TargetIdentity(
        target_id=target_id,
        target_kind=target_kind,
        source_location=source_location,
        repository_root=str(root),
        git_repository=True,
        source_commit=source_commit,
        repository_clean=repository_clean,
        local_or_remote=local_or_remote,
        language_hints=languages,
        manifest_hints=manifests,
        target_fingerprint=fingerprint,
        disposition="TARGET_IDENTIFIED",
    )


def inspect_remote_git(
    source_location: str,
) -> TargetIdentity:
    with TemporaryDirectory(
        prefix="kiln-target-"
    ) as temp:
        root = Path(temp) / "repository"

        clone = subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-tags",
                "--depth",
                "1",
                source_location,
                str(root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if clone.returncode != 0:
            return TargetIdentity(
                target_id="",
                target_kind="REMOTE_GIT_REPOSITORY",
                source_location=source_location,
                repository_root="",
                git_repository=True,
                source_commit="",
                repository_clean=False,
                local_or_remote="REMOTE",
                language_hints=tuple(),
                manifest_hints=tuple(),
                target_fingerprint="",
                disposition="REMOTE_ACQUISITION_FAILED",
            )

        result = git_identity(
            root,
            source_location,
            "REMOTE_GIT_REPOSITORY",
            "REMOTE",
        )

        return TargetIdentity(
            target_id=result.target_id,
            target_kind=result.target_kind,
            source_location=result.source_location,
            repository_root="",
            git_repository=result.git_repository,
            source_commit=result.source_commit,
            repository_clean=result.repository_clean,
            local_or_remote=result.local_or_remote,
            language_hints=result.language_hints,
            manifest_hints=result.manifest_hints,
            target_fingerprint=result.target_fingerprint,
            disposition=result.disposition,
        )


def inspect_target(
    target: Path | str,
) -> TargetIdentity:
    raw = str(target).strip()

    if is_remote_target(raw):
        return inspect_remote_git(raw)

    path = Path(raw).expanduser().resolve()

    if not path.exists():
        return TargetIdentity(
            target_id="",
            target_kind="UNKNOWN",
            source_location=str(path),
            repository_root="",
            git_repository=False,
            source_commit="",
            repository_clean=False,
            local_or_remote="LOCAL",
            language_hints=tuple(),
            manifest_hints=tuple(),
            target_fingerprint="",
            disposition="TARGET_NOT_FOUND",
        )

    if not path.is_dir():
        return TargetIdentity(
            target_id="",
            target_kind="UNKNOWN",
            source_location=str(path),
            repository_root="",
            git_repository=False,
            source_commit="",
            repository_clean=False,
            local_or_remote="LOCAL",
            language_hints=tuple(),
            manifest_hints=tuple(),
            target_fingerprint="",
            disposition="TARGET_NOT_DIRECTORY",
        )

    top = git(
        path,
        "rev-parse",
        "--show-toplevel",
    )

    if top.returncode == 0:
        root = Path(
            top.stdout.strip()
        ).resolve()

        return git_identity(
            root,
            str(root),
            "LOCAL_GIT_REPOSITORY",
            "LOCAL",
        )

    languages, manifests = discover_hints(
        path
    )

    fingerprint = directory_fingerprint(
        path
    )

    identity_source = (
        f"LOCAL_DIRECTORY\0"
        f"{path}\0"
        f"{fingerprint}"
    )

    target_id = (
        "KILN-TARGET-"
        + sha256(
            identity_source.encode("utf-8")
        ).hexdigest()[:16].upper()
    )

    return TargetIdentity(
        target_id=target_id,
        target_kind="LOCAL_DIRECTORY",
        source_location=str(path),
        repository_root=str(path),
        git_repository=False,
        source_commit="",
        repository_clean=True,
        local_or_remote="LOCAL",
        language_hints=languages,
        manifest_hints=manifests,
        target_fingerprint=fingerprint,
        disposition="TARGET_IDENTIFIED",
    )


def write_results(
    path: Path,
    results,
):
    fields = [
        "target_id",
        "target_kind",
        "source_location",
        "repository_root",
        "git_repository",
        "source_commit",
        "repository_clean",
        "local_or_remote",
        "language_hints",
        "manifest_hints",
        "target_fingerprint",
        "disposition",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for item in results:
            writer.writerow({
                "target_id": item.target_id,
                "target_kind": item.target_kind,
                "source_location": item.source_location,
                "repository_root": item.repository_root,
                "git_repository": str(
                    item.git_repository
                ).lower(),
                "source_commit": item.source_commit,
                "repository_clean": str(
                    item.repository_clean
                ).lower(),
                "local_or_remote": item.local_or_remote,
                "language_hints": ";".join(
                    item.language_hints
                ),
                "manifest_hints": ";".join(
                    item.manifest_hints
                ),
                "target_fingerprint": item.target_fingerprint,
                "disposition": item.disposition,
            })
