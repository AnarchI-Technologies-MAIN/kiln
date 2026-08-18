from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import csv
import hashlib


@dataclass(frozen=True)
class KilnExecutionPlan:
    plan_id: str
    candidate_id: str
    occurrence_id: str
    content_id: str
    repository_root: str
    repository_path: str
    runner: str
    attack_surface: str
    recovery_mode: str
    execution_mode: str
    evidence_refs: Tuple[str, ...]


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> Tuple[str, ...]:
    return tuple(
        sorted({item.strip() for item in str(value).split(";") if item.strip()})
    )


def plan_identity(candidate_id: str, attack_surface: str) -> str:
    material = f"{candidate_id}|{attack_surface}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"KILN-PLAN-{digest}"


def execution_mode(recovery_mode: str) -> str:
    if recovery_mode == "SANDBOX":
        return "SANDBOXED_TEST_EXECUTION"

    if recovery_mode == "DETACHED_WORKTREE":
        return "DETACHED_WORKTREE_TEST_EXECUTION"

    raise RuntimeError(
        f"unsupported recovery mode: {recovery_mode}"
    )


def build_plans(queue_path: Path) -> Tuple[KilnExecutionPlan, ...]:
    rows = read_csv(queue_path)
    plans = []

    for row in rows:
        surfaces = split_values(row.get("attack_surfaces", ""))

        if not surfaces:
            raise RuntimeError(
                f"candidate {row.get('candidate_id')} has no attack surface"
            )

        evidence = split_values(row.get("evidence_refs", ""))

        if not evidence:
            raise RuntimeError(
                f"candidate {row.get('candidate_id')} has no evidence"
            )

        mode = execution_mode(row["recovery_mode"])

        for surface in surfaces:
            plans.append(
                KilnExecutionPlan(
                    plan_id=plan_identity(row["candidate_id"], surface),
                    candidate_id=row["candidate_id"],
                    occurrence_id=row["occurrence_id"],
                    content_id=row["content_id"],
                    repository_root=row["repository_root"],
                    repository_path=row["repository_path"],
                    runner=row["runner"],
                    attack_surface=surface,
                    recovery_mode=row["recovery_mode"],
                    execution_mode=mode,
                    evidence_refs=evidence,
                )
            )

    return tuple(
        sorted(
            plans,
            key=lambda item: (
                item.occurrence_id,
                item.attack_surface,
                item.plan_id,
            ),
        )
    )


def write_plans(path: Path, plans: Tuple[KilnExecutionPlan, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "plan_id",
        "candidate_id",
        "occurrence_id",
        "content_id",
        "repository_root",
        "repository_path",
        "runner",
        "attack_surface",
        "recovery_mode",
        "execution_mode",
        "evidence_refs",
        "execution_authorized",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for item in plans:
            writer.writerow({
                "plan_id": item.plan_id,
                "candidate_id": item.candidate_id,
                "occurrence_id": item.occurrence_id,
                "content_id": item.content_id,
                "repository_root": item.repository_root,
                "repository_path": item.repository_path,
                "runner": item.runner,
                "attack_surface": item.attack_surface,
                "recovery_mode": item.recovery_mode,
                "execution_mode": item.execution_mode,
                "evidence_refs": ";".join(item.evidence_refs),
                "execution_authorized": "false",
            })
