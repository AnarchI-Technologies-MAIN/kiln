from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from engine.isolation_boundary import repository_path_is_absolute
from typing import Dict, List, Tuple
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import time

from engine.isolation_boundary import (
    warn_insufficient_isolation,
    sanitize_environment,
)


@dataclass(frozen=True)
class BaselineResult:
    plan_id: str
    repository_root: str
    repository_path: str
    source_commit: str
    runner: str
    result: str
    exit_code: int
    duration_seconds: float
    worktree_removed: bool
    original_head_preserved: bool


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def validate_repository_path(repository_path: str, worktree: Path) -> None:
    """
    Validate that repository_path is safe and contained within the worktree.
    
    Raises RuntimeError if the path is absolute or escapes the worktree.
    """
    # Reject absolute paths
    if repository_path_is_absolute(repository_path):
        raise RuntimeError(
            f"repository_path must be relative, got absolute path: {repository_path}"
        )
    
    # Normalize path separators
    normalized = repository_path.replace("\\", "/")
    target = Path(normalized)
    
    # Resolve the full path and verify containment
    full_path = (worktree / target).resolve()
    worktree_resolved = worktree.resolve()
    
    try:
        # Verify the resolved path is relative to the worktree
        full_path.relative_to(worktree_resolved)
    except ValueError:
        raise RuntimeError(
            f"repository_path escapes worktree boundary: {repository_path}"
        )


def runner_command(runner: str, repository_path: str, worktree: Path):
    """
    Build the test runner command.
    
    Args:
        runner: The test runner to use (pytest, python-unittest, etc.)
        repository_path: The relative path to the test file within the repository
        worktree: The worktree root path for validation
    
    Returns:
        List of command arguments for subprocess execution
    """
    # Validate path safety before building command
    validate_repository_path(repository_path, worktree)
    
    normalized = repository_path.replace("\\", "/")
    target = Path(normalized)

    if runner == "python-unittest":
        start_directory = target.parent.as_posix()
        pattern = target.name

        if not start_directory or start_directory == ".":
            start_directory = "."

        if not pattern:
            raise RuntimeError(
                f"invalid unittest target path: {repository_path}"
            )

        return [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            start_directory,
            "-p",
            pattern,
        ]

    if runner in {"pytest", "pytest-compatible"}:
        return [sys.executable, "-m", "pytest", normalized]

    raise RuntimeError(f"unsupported baseline runner: {runner}")


def execute_one(plan: dict, preflight: dict, session_root: Path) -> BaselineResult:
    repo = Path(plan["repository_root"]).resolve()
    source_commit = preflight["source_commit"]

    # Emit security warning about insufficient isolation
    warn_insufficient_isolation("Baseline test execution")

    before = git(repo, "rev-parse", "HEAD")

    if before.returncode != 0:
        raise RuntimeError(f"unable to resolve original HEAD for {repo}")

    original_head = before.stdout.strip()

    if original_head != source_commit:
        raise RuntimeError(
            f"repository HEAD drifted after preflight: {repo}"
        )

    worktree = session_root / plan["plan_id"]

    add = git(
        repo,
        "worktree",
        "add",
        "--detach",
        str(worktree),
        source_commit,
    )

    if add.returncode != 0:
        raise RuntimeError(
            f"failed to create detached worktree for {plan['plan_id']}: "
            f"{add.stderr.strip()}"
        )

    start = time.perf_counter()
    exit_code = 1
    worktree_removed = False

    try:
        # Sanitize environment to filter sensitive credentials
        # Note: This is defense-in-depth, NOT a security boundary
        env = sanitize_environment(
            preserve_keys={"PYTHONPATH"}
        )
        env["PYTHONPATH"] = str(worktree)

        command = runner_command(
            plan["runner"],
            plan["repository_path"],
            worktree,
        )

        run = subprocess.run(
            command,
            cwd=str(worktree),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        exit_code = run.returncode

        logs = session_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)

        (logs / f"{plan['plan_id']}.stdout.txt").write_text(
            run.stdout,
            encoding="utf-8",
        )

        (logs / f"{plan['plan_id']}.stderr.txt").write_text(
            run.stderr,
            encoding="utf-8",
        )
    finally:
        remove = git(
            repo,
            "worktree",
            "remove",
            "--force",
            str(worktree),
        )

        worktree_removed = remove.returncode == 0

        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)

        git(repo, "worktree", "prune")

    duration = time.perf_counter() - start

    after = git(repo, "rev-parse", "HEAD")
    original_head_preserved = (
        after.returncode == 0
        and after.stdout.strip() == original_head
    )

    result = "PASS"

    if exit_code != 0:
        result = "FAIL"

    return BaselineResult(
        plan_id=plan["plan_id"],
        repository_root=str(repo),
        repository_path=plan["repository_path"],
        source_commit=source_commit,
        runner=plan["runner"],
        result=result,
        exit_code=exit_code,
        duration_seconds=round(duration, 6),
        worktree_removed=worktree_removed,
        original_head_preserved=original_head_preserved,
    )


def execute_baselines(plan_path: Path, preflight_path: Path, session_root: Path):
    plans = read_csv(plan_path)
    preflights = read_csv(preflight_path)

    plan_by_id: Dict[str, dict] = {row["plan_id"]: row for row in plans}

    results = []

    for preflight in preflights:
        if preflight.get("disposition") != "READY_FOR_ISOLATED_BASELINE":
            continue

        plan = plan_by_id.get(preflight["plan_id"])

        if plan is None:
            raise RuntimeError(
                f"preflight references missing plan {preflight['plan_id']}"
            )

        if plan.get("execution_authorized") != "true":
            raise RuntimeError(
                f"preflight-ready plan is not authorized: {plan['plan_id']}"
            )

        if plan.get("recovery_mode") != "DETACHED_WORKTREE":
            continue

        results.append(execute_one(plan, preflight, session_root))

    return tuple(results)


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "repository_root",
        "repository_path",
        "source_commit",
        "runner",
        "result",
        "exit_code",
        "duration_seconds",
        "worktree_removed",
        "original_head_preserved",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "plan_id": item.plan_id,
                "repository_root": item.repository_root,
                "repository_path": item.repository_path,
                "source_commit": item.source_commit,
                "runner": item.runner,
                "result": item.result,
                "exit_code": item.exit_code,
                "duration_seconds": item.duration_seconds,
                "worktree_removed": str(item.worktree_removed).lower(),
                "original_head_preserved": str(
                    item.original_head_preserved
                ).lower(),
            })
