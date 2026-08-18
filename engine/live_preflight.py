from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import csv
import subprocess


SUPPORTED_RUNNERS = {
    "python-unittest",
    "pytest",
    "pytest-compatible",
}


@dataclass(frozen=True)
class LivePreflightResult:
    plan_id: str
    repository_root: str
    repository_path: str
    runner: str
    source_commit: str
    repository_clean: bool
    test_exists: bool
    git_repository: bool
    runner_supported: bool
    recovery_mode: str
    disposition: str
    blockers: Tuple[str, ...]


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def inspect_plan(plan: dict) -> LivePreflightResult:
    blockers = []
    repo = Path(plan["repository_root"]).resolve()
    test = repo / plan["repository_path"]

    git_repository = False
    source_commit = ""
    repository_clean = False

    if not repo.is_dir():
        blockers.append("REPOSITORY_MISSING")

    if repo.is_dir():
        probe = git(repo, "rev-parse", "--is-inside-work-tree")
        git_repository = (
            probe.returncode == 0
            and probe.stdout.strip().lower() == "true"
        )

    if not git_repository:
        blockers.append("NOT_GIT_REPOSITORY")

    if git_repository:
        head = git(repo, "rev-parse", "HEAD")

        if head.returncode == 0:
            source_commit = head.stdout.strip()

        if not source_commit:
            blockers.append("HEAD_UNRESOLVED")

        status = git(repo, "status", "--porcelain")

        if status.returncode == 0:
            repository_clean = not bool(status.stdout.strip())

    test_exists = test.is_file()

    if not test_exists:
        blockers.append("TEST_PATH_MISSING")

    runner = plan.get("runner", "").strip()
    runner_supported = runner in SUPPORTED_RUNNERS

    if not runner_supported:
        blockers.append("RUNNER_UNSUPPORTED")

    recovery = plan.get("recovery_mode", "").strip()

    if recovery not in {"DETACHED_WORKTREE", "SANDBOX"}:
        blockers.append("RECOVERY_MODE_UNSUPPORTED")

    disposition = "READY_FOR_ISOLATED_BASELINE"

    if blockers:
        disposition = "BLOCKED"

    return LivePreflightResult(
        plan_id=plan["plan_id"],
        repository_root=str(repo),
        repository_path=plan["repository_path"],
        runner=runner,
        source_commit=source_commit,
        repository_clean=repository_clean,
        test_exists=test_exists,
        git_repository=git_repository,
        runner_supported=runner_supported,
        recovery_mode=recovery,
        disposition=disposition,
        blockers=tuple(sorted(set(blockers))),
    )


def run_preflight(plan_path: Path, dry_run_path: Path):
    plans = read_csv(plan_path)
    dry_runs = read_csv(dry_run_path)

    dry_ready = {
        row["plan_id"]
        for row in dry_runs
        if row.get("dry_run_result") == "READY_FOR_LIVE_PREFLIGHT"
    }

    results = []

    for plan in plans:
        if plan.get("execution_authorized") != "true":
            continue

        if plan["plan_id"] not in dry_ready:
            raise RuntimeError(
                f"authorized plan {plan['plan_id']} lacks successful dry run"
            )

        results.append(inspect_plan(plan))

    return tuple(sorted(results, key=lambda item: item.plan_id))


def write_results(path: Path, results):
    fields = [
        "plan_id",
        "repository_root",
        "repository_path",
        "runner",
        "source_commit",
        "repository_clean",
        "test_exists",
        "git_repository",
        "runner_supported",
        "recovery_mode",
        "disposition",
        "blockers",
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
                "runner": item.runner,
                "source_commit": item.source_commit,
                "repository_clean": str(item.repository_clean).lower(),
                "test_exists": str(item.test_exists).lower(),
                "git_repository": str(item.git_repository).lower(),
                "runner_supported": str(item.runner_supported).lower(),
                "recovery_mode": item.recovery_mode,
                "disposition": item.disposition,
                "blockers": ";".join(item.blockers),
            })
