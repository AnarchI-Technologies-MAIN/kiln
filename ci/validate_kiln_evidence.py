"""Fail-closed validation for a source-bound Kiln qualification result."""

from __future__ import annotations

import argparse
import json
import re
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
        "cycle_id",
        "adapter",
        "entry",
        "baseline_sandbox_id",
        "baseline_evidence_path",
        "trials",
    }
    missing = sorted(required - result.keys())
    if missing:
        raise ValueError(f"cycle result missing fields: {', '.join(missing)}")

    if result["source_commit"] != expected_source_commit:
        raise ValueError("cycle result is bound to a different source commit")
    if not isinstance(expected_source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", expected_source_commit) is None:
        raise ValueError("source commit is not a full lowercase SHA")
    if not all(isinstance(result.get(field), str) and result[field] for field in ("cycle_id", "adapter", "entry", "baseline_sandbox_id", "baseline_evidence_path")):
        raise ValueError("cycle identity is incomplete")
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

    evidence_root = evidence_root.resolve()
    def evidence_file(raw, label):
        if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
            raise ValueError(f"{label} path is invalid")
        path = (evidence_root / raw).resolve()
        if not path.is_relative_to(evidence_root) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing or empty {label}")
        return path

    baseline_evidence = evidence_file(result["baseline_evidence_path"], "baseline evidence")
    try:
        baseline_process = json.loads(baseline_evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("baseline process evidence is not valid JSON") from exc
    if not isinstance(baseline_process, dict) or baseline_process.get("returncode") != 0:
        raise ValueError("baseline process identity is invalid")

    result_trials = result["trials"]
    if not isinstance(result_trials, list) or len(result_trials) != result["passes_executed"]:
        raise ValueError("cycle trial count does not match execution")
    trial_by_pass = {}
    for trial in result_trials:
        if not isinstance(trial, dict) or not isinstance(trial.get("pass_number"), int):
            raise ValueError("cycle result contains an invalid trial")
        if trial["pass_number"] in trial_by_pass:
            raise ValueError("cycle result contains duplicate trial identities")
        for field in ("mutation_id", "sandbox_id", "test_evidence_path", "proof_metadata_path", "canonical_source_hash"):
            if not isinstance(trial.get(field), str) or not trial[field]:
                raise ValueError("cycle trial identity is incomplete")
        evidence_file(trial["test_evidence_path"], "trial process evidence")
        evidence_file(trial["proof_metadata_path"], "trial proof metadata")
        trial_by_pass[trial["pass_number"]] = trial
    if sorted(trial_by_pass) != list(range(1, result["passes_executed"] + 1)):
        raise ValueError("cycle trial pass sequence is inconsistent")
    if len({trial["mutation_id"] for trial in result_trials}) != len(result_trials) or len({trial["sandbox_id"] for trial in result_trials}) != len(result_trials):
        raise ValueError("cycle trial identities are duplicated")

    proof_path = Path(result["proof_metadata_path"]).resolve()
    if not proof_path.is_relative_to(evidence_root):
        raise ValueError("proof metadata path escaped evidence root")
    if not proof_path.is_file() or proof_path.stat().st_size == 0:
        raise ValueError("missing or empty proof metadata")
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("proof metadata is not valid JSON") from exc
    if proof.get("schema") != "kiln.proof-metadata-aggregate.v1":
        raise ValueError("proof metadata schema is invalid")
    if proof.get("proof_evidence_version") != "KILN-PROOF-EVIDENCE-3":
        raise ValueError("proof metadata version is invalid")
    trials = proof.get("trials")
    if not isinstance(trials, list) or len(trials) != result["passes_executed"]:
        raise ValueError("proof metadata trial count does not match execution")
    pass_numbers = []
    mutation_ids = []
    for trial in trials:
        if not isinstance(trial, dict) or not trial.get("mutation_id") or not isinstance(trial.get("metadata"), dict):
            raise ValueError("proof metadata contains an invalid trial")
        if not isinstance(trial.get("pass_number"), int):
            raise ValueError("proof metadata trial lacks a pass number")
        metadata = trial["metadata"]
        if metadata.get("schema") != "kiln.proof-metadata.v2" or metadata.get("proof_metadata_version") != "KILN-PROOF-METADATA-2":
            raise ValueError("proof metadata trial uses an invalid metadata contract")
        executed = trial_by_pass.get(trial["pass_number"])
        if executed is None or executed["mutation_id"] != trial["mutation_id"]:
            raise ValueError("proof metadata trial is not bound to executed trial")
        if not metadata.get("detected_test_ids") or not metadata.get("invariant_refs") or not metadata.get("behavioral_fragment_refs") or not metadata.get("fragment_proof_links"):
            raise ValueError("proof metadata trial is empty or incomplete")
        process_path = evidence_file(executed["test_evidence_path"], "trial process evidence")
        try:
            process = json.loads(process_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("trial process evidence is not valid JSON") from exc
        if not isinstance(process, dict) or process.get("returncode") != executed.get("test_exit_code"):
            raise ValueError("trial process identity does not match executed result")
        pass_numbers.append(trial["pass_number"])
        mutation_ids.append(trial["mutation_id"])
    if pass_numbers != list(range(1, len(trials) + 1)):
        raise ValueError("proof metadata pass sequence is inconsistent")
    if len(set(mutation_ids)) != len(mutation_ids):
        raise ValueError("proof metadata mutation identities are duplicated")

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

