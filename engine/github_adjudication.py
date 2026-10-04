from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess

from engine.constructive_redesign import (
    adjudication_branch_failures,
)


@dataclass(frozen=True)
class GitHubAdjudication:
    repository: str
    branch_name: str
    base_branch: str
    commit_hash: str
    draft_pr_url: str
    draft_pr_created: bool
    cycle_reignited: bool
    disposition: str


def github_repository_from_remote(
    target_repo: Path,
    remote_name: str,
) -> str:
    remote = subprocess.run(
        [
            "git",
            "-C",
            str(Path(target_repo).resolve()),
            "remote",
            "get-url",
            remote_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if remote.returncode != 0:
        raise RuntimeError(
            "unable to resolve GitHub promotion remote"
        )

    value = remote.stdout.strip()
    match = re.match(
        r"^(?:https://github\.com/|git@github\.com:|"
        r"ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?$",
        value,
    )

    if not match:
        raise RuntimeError(
            "adjudication publication requires a GitHub remote"
        )

    return match.group(1)


def publish_github_adjudication(
    target_repo: Path,
    remote_name: str,
    branch_name: str,
    base_branch: str,
    commit_hash: str,
    title: str,
    body: str,
    repository: str = "",
) -> GitHubAdjudication:
    branch_failures = adjudication_branch_failures(
        branch_name
    )

    if branch_failures:
        raise RuntimeError(
            "draft PR head is not an adjudication branch"
        )

    base = base_branch.strip()

    if (
        not base
        or base != base_branch
        or base == branch_name
        or base.startswith("refs/")
    ):
        raise RuntimeError(
            "invalid human-adjudication base branch"
        )

    if not re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
        commit_hash,
    ):
        raise RuntimeError(
            "verified adjudication commit is required"
        )

    if not title.strip() or not body.strip():
        raise RuntimeError(
            "draft PR title and adjudication body are required"
        )

    slug = repository.strip()

    if not slug:
        slug = github_repository_from_remote(
            target_repo,
            remote_name,
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        slug,
    ):
        raise RuntimeError(
            "invalid GitHub repository identifier"
        )

    create_pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            slug,
            "--draft",
            "--base",
            base,
            "--head",
            branch_name,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=str(Path(target_repo).resolve()),
        capture_output=True,
        text=True,
        check=False,
    )

    pr_url = ""

    if create_pr.returncode == 0:
        pr_url = create_pr.stdout.strip().splitlines()[-1]
    else:
        existing_pr = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                branch_name,
                "--repo",
                slug,
                "--json",
                (
                    "url,isDraft,state,baseRefName,"
                    "headRefName,headRefOid"
                ),
            ],
            cwd=str(Path(target_repo).resolve()),
            capture_output=True,
            text=True,
            check=False,
        )

        payload = {}

        if existing_pr.returncode == 0:
            try:
                payload = json.loads(
                    existing_pr.stdout
                )
            except json.JSONDecodeError:
                payload = {}

        existing_is_exact_draft = (
            payload.get("isDraft") is True
            and payload.get("state") == "OPEN"
            and payload.get("baseRefName") == base
            and payload.get("headRefName") == branch_name
            and payload.get("headRefOid") == commit_hash
            and bool(payload.get("url"))
        )

        if not existing_is_exact_draft:
            return GitHubAdjudication(
                repository=slug,
                branch_name=branch_name,
                base_branch=base,
                commit_hash=commit_hash,
                draft_pr_url="",
                draft_pr_created=False,
                cycle_reignited=False,
                disposition="DRAFT_PR_CREATION_FAILED",
            )

        pr_url = payload["url"]

    reignite = subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{slug}/dispatches",
            "-f",
            "event_type=kiln_staged_adjudication",
            "-f",
            "client_payload[commit_sha]=" + commit_hash,
            "-f",
            "client_payload[branch]=" + branch_name,
            "--silent",
        ],
        cwd=str(Path(target_repo).resolve()),
        capture_output=True,
        text=True,
        check=False,
    )

    if reignite.returncode != 0:
        return GitHubAdjudication(
            repository=slug,
            branch_name=branch_name,
            base_branch=base,
            commit_hash=commit_hash,
            draft_pr_url=pr_url,
            draft_pr_created=True,
            cycle_reignited=False,
            disposition="RECURSIVE_CYCLE_DISPATCH_FAILED",
        )

    return GitHubAdjudication(
        repository=slug,
        branch_name=branch_name,
        base_branch=base,
        commit_hash=commit_hash,
        draft_pr_url=pr_url,
        draft_pr_created=True,
        cycle_reignited=True,
        disposition="HUMAN_ADJUDICATION_REQUIRED",
    )
