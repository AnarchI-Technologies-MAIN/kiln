from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import csv


ALLOWED_EXECUTION_MODES = {
    "DETACHED_WORKTREE_TEST_EXECUTION",
    "SANDBOXED_TEST_EXECUTION",
}

ALLOWED_RECOVERY_MODES = {
    "DETACHED_WORKTREE",
    "SANDBOX",
}


@dataclass(frozen=True)
class AuthorizationDecision:
    plan_id: str
    authorized: bool
    disposition: str
    failed_gates: Tuple[str, ...]


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def evaluate_plan(row: dict) -> AuthorizationDecision:
    failures = []

    if not row.get("plan_id", "").strip():
        failures.append("MISSING_PLAN_ID")

    if not row.get("occurrence_id", "").strip():
        failures.append("MISSING_OCCURRENCE_ID")

    if not row.get("content_id", "").strip():
        failures.append("MISSING_CONTENT_ID")

    if not row.get("repository_root", "").strip():
        failures.append("MISSING_REPOSITORY_ROOT")

    if not row.get("repository_path", "").strip():
        failures.append("MISSING_REPOSITORY_PATH")

    if not row.get("runner", "").strip():
        failures.append("MISSING_RUNNER")

    if not row.get("attack_surface", "").strip():
        failures.append("MISSING_ATTACK_SURFACE")

    if not row.get("evidence_refs", "").strip():
        failures.append("MISSING_EVIDENCE")

    recovery = row.get("recovery_mode", "").strip()
    execution = row.get("execution_mode", "").strip()

    if recovery not in ALLOWED_RECOVERY_MODES:
        failures.append("UNSUPPORTED_RECOVERY_MODE")

    if execution not in ALLOWED_EXECUTION_MODES:
        failures.append("UNSUPPORTED_EXECUTION_MODE")

    if recovery == "SANDBOX" and execution != "SANDBOXED_TEST_EXECUTION":
        failures.append("RECOVERY_EXECUTION_MISMATCH")

    if recovery == "DETACHED_WORKTREE" and execution != "DETACHED_WORKTREE_TEST_EXECUTION":
        failures.append("RECOVERY_EXECUTION_MISMATCH")

    authorized = len(failures) == 0

    disposition = "AUTHORIZED"
    if not authorized:
        disposition = "BLOCKED"

    return AuthorizationDecision(
        plan_id=row.get("plan_id", ""),
        authorized=authorized,
        disposition=disposition,
        failed_gates=tuple(sorted(set(failures))),
    )


def authorize(input_path: Path, output_path: Path, ledger_path: Path):
    rows = read_csv(input_path)
    decisions = []

    for row in rows:
        decision = evaluate_plan(row)
        decisions.append(decision)
        row["execution_authorized"] = (
            "true" if decision.authorized else "false"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    fields = [
        "plan_id",
        "authorized",
        "disposition",
        "failed_gates",
    ]

    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for decision in decisions:
            writer.writerow({
                "plan_id": decision.plan_id,
                "authorized": str(decision.authorized).lower(),
                "disposition": decision.disposition,
                "failed_gates": ";".join(decision.failed_gates),
            })

    return tuple(decisions)
