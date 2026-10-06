"""Build a durable, path-free receipt from a completed bounded campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RECEIPT_SCHEMA = "kiln.sanitized-campaign-receipt.v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a full lowercase commit SHA")
    return value


def build_receipt(result: dict, source_repository: str, source_head_sha: str, source_base_sha: str, kiln_runtime_sha: str) -> dict:
    required = ("cycle_id", "source_commit", "adapter", "entry", "passes_requested", "passes_executed", "trials")
    if not isinstance(result, dict) or any(field not in result for field in required):
        raise ValueError("cycle result is incomplete")
    source_head_sha = _commit(source_head_sha, "source head")
    source_base_sha = _commit(source_base_sha, "source base")
    kiln_runtime_sha = _commit(kiln_runtime_sha, "Kiln runtime")
    if result["source_commit"] != source_head_sha:
        raise ValueError("cycle source does not match requested head")
    trials = []
    for trial in result["trials"]:
        if not isinstance(trial, dict):
            raise ValueError("trial is not an object")
        selected = {
            key: trial.get(key)
            for key in ("pass_number", "mutation_id", "sandbox_id", "canonical_source_hash", "test_exit_code", "survived", "fracture_observed", "restored", "sandbox_removed", "disposition")
        }
        if not selected["mutation_id"] or not selected["sandbox_id"]:
            raise ValueError("trial identity is incomplete")
        selected["trial_identity_hash"] = _sha(selected)
        trials.append(selected)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "receipt_version": 1,
        "qualification_status": "pending_final_controller_gates",
        "source_repository": source_repository,
        "source_head_sha": source_head_sha,
        "source_base_sha": source_base_sha,
        "kiln_runtime_sha": kiln_runtime_sha,
        "cycle_id": result["cycle_id"],
        "adapter": result["adapter"],
        "entry": result["entry"],
        "until": result.get("until", "unknown"),
        "baseline_passed": result.get("baseline_passed"),
        "mutation_candidate_count": result.get("mutation_candidate_count"),
        "passes_requested": result["passes_requested"],
        "passes_executed": result["passes_executed"],
        "fractures_observed": result.get("fractures_observed"),
        "survivors_observed": result.get("survivors_observed"),
        "execution_failures": result.get("execution_failures"),
        "specimen_removed": result.get("specimen_removed"),
        "original_head_preserved": result.get("original_head_preserved"),
        "disposition": result.get("disposition"),
        "trial_count": len(trials),
        "trials": trials,
        "checkpoint_hashes": [],
        "checkpoint_receipt_status": "not_applicable_to_campaign",
    }
    return receipt


def write_receipt(result_path: Path, output_path: Path, **identity: str) -> dict:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    receipt = build_receipt(result, **identity)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--source-base-sha", required=True)
    parser.add_argument("--kiln-runtime-sha", required=True)
    args = parser.parse_args()
    write_receipt(
        args.result,
        args.output,
        source_repository=args.source_repository,
        source_head_sha=args.source_head_sha,
        source_base_sha=args.source_base_sha,
        kiln_runtime_sha=args.kiln_runtime_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
