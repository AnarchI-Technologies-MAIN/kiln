"""Fail-closed validation for a source-bound Kiln qualification result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


COMPLETED_DISPOSITIONS = {
    "CYCLE_COMPLETE",
    "FRACTURE_EVIDENCE_PRODUCED",
    "BOUNDED_STABILITY_OBSERVED",
}


def validate(evidence_root: Path, expected_source_commit: str, requested_passes: int) -> dict:
    result_path = evidence_root / "cycle-result.json"
    if not result_path.is_file() or result_path.stat().st_size == 0:
        raise ValueError("missing or empty cycle-result.json")

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cycle-result.json is not valid JSON") from exc

    required = {
        "source_commit",
        "baseline_passed",
        "mutation_candidate_count",
        "passes_requested",
        "passes_executed",
        "execution_failures",
        "specimen_removed",
        "original_head_preserved",
        "disposition",
        "proof_metadata_path",
    }
    missing = sorted(required - result.keys())
    if missing:
        raise ValueError(f"cycle result missing fields: {', '.join(missing)}")

    if result["source_commit"] != expected_source_commit:
        raise ValueError("cycle result is bound to a different source commit")
    if result["baseline_passed"] is not True:
        raise ValueError("baseline did not pass")
    if result["mutation_candidate_count"] < 1:
        raise ValueError("no mutation candidate was executed")
    if result["passes_requested"] != requested_passes:
        raise ValueError("cycle requested-pass count does not match the gate")
    if result["passes_executed"] != requested_passes:
        raise ValueError("cycle did not execute every requested pass")
    if result["execution_failures"] != 0:
        raise ValueError("cycle reported execution failures")
    if result["specimen_removed"] is not True:
        raise ValueError("specimen cleanup was not proven")
    if result["original_head_preserved"] is not True:
        raise ValueError("source HEAD preservation was not proven")
    if result["disposition"] not in COMPLETED_DISPOSITIONS:
        raise ValueError(f"non-completed disposition: {result['disposition']}")

    proof_path = Path(result["proof_metadata_path"])
    if not proof_path.is_file() or proof_path.stat().st_size == 0:
        raise ValueError("missing or empty proof metadata")

    return {
        "qualified": True,
        "source_commit": expected_source_commit,
        "disposition": result["disposition"],
        "fractures_observed": result.get("fractures_observed", 0),
        "survivors_observed": result.get("survivors_observed", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--requested-passes", type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.evidence_root, args.expected_source_commit, args.requested_passes), sort_keys=True))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


