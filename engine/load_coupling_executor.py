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
import time


@dataclass(frozen=True)
class LoadCouplingResult:
    plan_id: str
    coupling_id: str
    source_commit: str
    baseline_invocations: int
    pressured_invocations: int
    baseline_passed: bool
    pressured_passed: int
    coupling_proven: bool
    resilience_proven: bool
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


def execute_command(command, worktree: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(worktree)

    return subprocess.run(
        command,
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def execute_one(plan, preflight, authorization, session_root: Path):
    if authorization.get("authorized") != "true":
        raise RuntimeError("coupling trial is not authorized")

    if authorization.get("attack_surface") != "load":
        raise RuntimeError(
            "Core 015 supports only the load coupling surface"
        )

    if int(authorization.get("max_trials", "0")) != 1:
        raise RuntimeError("coupling authorization is not bounded to one trial")

    repo = Path(plan["repository_root"]).resolve()
    source_commit = preflight["source_commit"]

    before = git(repo, "rev-parse", "HEAD")

    if before.returncode != 0:
        raise RuntimeError("unable to resolve original repository HEAD")

    original_head = before.stdout.strip()

    if original_head != source_commit:
        raise RuntimeError("repository HEAD drifted after baseline proof")

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
            f"failed to create coupling worktree: {add.stderr.strip()}"
        )

    logs = session_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    worktree_removed = False

    try:
        command = runner_command(
            plan["runner"],
            plan["repository_path"],
            worktree,
        )

        baseline = execute_command(command, worktree)

        (logs / f"{plan['plan_id']}.baseline.stdout.txt").write_text(
            baseline.stdout,
            encoding="utf-8",
        )

        (logs / f"{plan['plan_id']}.baseline.stderr.txt").write_text(
            baseline.stderr,
            encoding="utf-8",
        )

        pressured_runs = []

        for index in range(2):
            run = execute_command(command, worktree)
            pressured_runs.append(run)

            (
                logs / f"{plan['plan_id']}.pressure-{index + 1}.stdout.txt"
            ).write_text(run.stdout, encoding="utf-8")

            (
                logs / f"{plan['plan_id']}.pressure-{index + 1}.stderr.txt"
            ).write_text(run.stderr, encoding="utf-8")

        baseline_passed = baseline.returncode == 0
        pressured_passed = sum(
            1 for item in pressured_runs if item.returncode == 0
        )

        # The carrier proof is intentionally mechanical:
        # one baseline invocation vs two pressured invocations.
        coupling_proven = (
            baseline_passed
            and len(pressured_runs) == 2
        )

        # Surviving two executions is NOT yet generalized resilience proof.
        resilience_proven = False
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

    after = git(repo, "rev-parse", "HEAD")
    original_head_preserved = (
        after.returncode == 0
        and after.stdout.strip() == original_head
    )

    return LoadCouplingResult(
        plan_id=plan["plan_id"],
        coupling_id=authorization["coupling_id"],
        source_commit=source_commit,
        baseline_invocations=1,
        pressured_invocations=2,
        baseline_passed=baseline_passed,
        pressured_passed=pressured_passed,
        coupling_proven=coupling_proven,
        resilience_proven=resilience_proven,
        worktree_removed=worktree_removed,
        original_head_preserved=original_head_preserved,
    )


def execute_trials(plan_path, preflight_path, authorization_path, session_root):
    plans = read_csv(plan_path)
    preflights = read_csv(preflight_path)
    authorizations = read_csv(authorization_path)

    plan_by_id = {row["plan_id"]: row for row in plans}
    preflight_by_id = {row["plan_id"]: row for row in preflights}

    results = []

    for authorization in authorizations:
        if authorization.get("authorized") != "true":
            continue

        if authorization.get("attack_surface") != "load":
            continue

        plan = plan_by_id.get(authorization["plan_id"])
        preflight = preflight_by_id.get(authorization["plan_id"])

        if plan is None or preflight is None:
            raise RuntimeError(
                f"authorized coupling trial lacks plan/preflight: "
                f"{authorization['plan_id']}"
            )

        results.append(
            execute_one(plan, preflight, authorization, session_root)
        )

    return tuple(results)


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "coupling_id",
        "source_commit",
        "baseline_invocations",
        "pressured_invocations",
        "baseline_passed",
        "pressured_passed",
        "coupling_proven",
        "resilience_proven",
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
                "coupling_id": item.coupling_id,
                "source_commit": item.source_commit,
                "baseline_invocations": item.baseline_invocations,
                "pressured_invocations": item.pressured_invocations,
                "baseline_passed": str(item.baseline_passed).lower(),
                "pressured_passed": item.pressured_passed,
                "coupling_proven": str(item.coupling_proven).lower(),
                "resilience_proven": str(item.resilience_proven).lower(),
                "worktree_removed": str(item.worktree_removed).lower(),
                "original_head_preserved": str(
                    item.original_head_preserved
                ).lower(),
            })
