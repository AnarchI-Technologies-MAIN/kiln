from __future__ import annotations

from pathlib import Path
import csv
import os
import shutil
import subprocess
import sys


LOAD_LEVELS = {
    "1x": 1,
    "2x": 2,
    "4x": 4,
    "8x": 8,
    "16x": 16,
}


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def git(repo, *args):
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
    if Path(repository_path).is_absolute():
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


def runner_command(runner, repository_path, worktree):
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

    raise RuntimeError(f"unsupported runner: {runner}")

def run_once(command, worktree):
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


def execute_level(plan, preflight, contract, level, session_root):
    repo = Path(plan["repository_root"]).resolve()
    commit = preflight["source_commit"]
    multiplier = LOAD_LEVELS[level]

    original = git(repo, "rev-parse", "HEAD")

    if original.returncode != 0:
        raise RuntimeError("unable to resolve original HEAD")

    original_head = original.stdout.strip()

    if original_head != commit:
        raise RuntimeError("repository HEAD drifted after preflight")

    worktree = (
        session_root
        / plan["plan_id"]
        / level
    )

    worktree.parent.mkdir(parents=True, exist_ok=True)

    add = git(
        repo,
        "worktree",
        "add",
        "--detach",
        str(worktree),
        commit,
    )

    if add.returncode != 0:
        raise RuntimeError(f"worktree creation failed: {add.stderr.strip()}")

    command = runner_command(plan["runner"], plan["repository_path"], worktree)
    passed = 0
    worktree_removed = False

    logs = session_root / "logs" / plan["plan_id"] / level
    logs.mkdir(parents=True, exist_ok=True)

    try:
        for index in range(multiplier):
            run = run_once(command, worktree)

            (logs / f"run-{index + 1}.stdout.txt").write_text(
                run.stdout,
                encoding="utf-8",
            )

            (logs / f"run-{index + 1}.stderr.txt").write_text(
                run.stderr,
                encoding="utf-8",
            )

            if run.returncode == 0:
                passed += 1

            if run.returncode != 0:
                break
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

    survived = (
        passed == multiplier
        and worktree_removed
        and original_head_preserved
    )

    return {
        "plan_id": plan["plan_id"],
        "contract_id": contract["contract_id"],
        "attack_surface": "load",
        "pressure_level": level,
        "requested_runs": multiplier,
        "passed_runs": passed,
        "survived": str(survived).lower(),
        "worktree_removed": str(worktree_removed).lower(),
        "original_head_preserved": str(original_head_preserved).lower(),
    }


def execute_ladders(plan_path, preflight_path, contract_path, authorization_path, session_root):
    plans = {row["plan_id"]: row for row in read_csv(plan_path)}
    preflights = {row["plan_id"]: row for row in read_csv(preflight_path)}
    contracts = {row["contract_id"]: row for row in read_csv(contract_path)}
    authorizations = read_csv(authorization_path)

    results = []

    for auth in authorizations:
        if auth.get("authorized") != "true":
            continue

        if auth.get("attack_surface") != "load":
            continue

        plan = plans.get(auth["plan_id"])
        preflight = preflights.get(auth["plan_id"])
        contract = contracts.get(auth["contract_id"])

        if plan is None or preflight is None or contract is None:
            raise RuntimeError(f"incomplete pressure lineage for {auth['plan_id']}")

        levels = [
            item
            for item in contract["pressure_levels"].split(";")
            if item
        ]

        for level in levels:
            if level not in LOAD_LEVELS:
                raise RuntimeError(f"unsupported load level: {level}")

            result = execute_level(
                plan,
                preflight,
                contract,
                level,
                Path(session_root),
            )

            results.append(result)

            if result["survived"] != "true":
                break

    return tuple(results)


def write_results(path, results):
    fields = [
        "plan_id",
        "contract_id",
        "attack_surface",
        "pressure_level",
        "requested_runs",
        "passed_runs",
        "survived",
        "worktree_removed",
        "original_head_preserved",
    ]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
