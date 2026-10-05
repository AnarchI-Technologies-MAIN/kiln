"""Bounded, specimen-only repair lineage slice.

This is deliberately one deterministic repair operator: restore the exact
source token changed by a qualified mutation candidate, then replay the same
oracle. It does not infer intent, edit upstream source, or claim hostile
containment.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from engine.mutation_executor import MutationCandidate, apply_mutation, file_hash


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    parent_checkpoint_id: str | None
    source_hash: str
    specimen_hash: str
    parameters_hash: str
    phase: str


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _checkpoint(path: Path, *, parent: str | None, source_hash: str,
                specimen_hash: str, parameters: dict, phase: str) -> Checkpoint:
    parameters_hash = _digest(parameters)
    checkpoint_id = "KILN-CHECKPOINT-" + _digest({
        "parent": parent,
        "source_hash": source_hash,
        "specimen_hash": specimen_hash,
        "parameters_hash": parameters_hash,
        "phase": phase,
    })[:24].upper()
    result = Checkpoint(checkpoint_id, parent, source_hash, specimen_hash,
                        parameters_hash, phase)
    if path.exists():
        raise RuntimeError("checkpoint path already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), sort_keys=True) + "\n", encoding="utf-8")
    return result


def _run_oracle(specimen: Path, command: list[str]) -> None:
    result = subprocess.run(command, cwd=specimen, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"oracle failed: {result.returncode}")


def repair_and_replay(
    specimen: Path,
    candidate: MutationCandidate,
    oracle: list[str],
    checkpoint_root: Path,
    parameters: dict,
) -> tuple[Checkpoint, Checkpoint]:
    specimen = Path(specimen).resolve()
    source_path = specimen / candidate.relative_path
    original_bytes = source_path.read_bytes()
    source_hash = file_hash(source_path)
    _run_oracle(specimen, oracle)
    baseline = _checkpoint(
        checkpoint_root / "baseline.json",
        parent=None,
        source_hash=source_hash,
        specimen_hash=_digest({candidate.relative_path: source_hash}),
        parameters=parameters,
        phase="BASELINE",
    )

    applied = apply_mutation(specimen, candidate)
    if not applied.applied:
        raise RuntimeError("bounded mutation did not apply")
    try:
        _run_oracle(specimen, oracle)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("mutation did not fracture the fixed oracle")

    path = specimen / candidate.relative_path
    mutated_bytes = path.read_bytes()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    line_index = candidate.line - 1
    line = lines[line_index]
    start = candidate.column
    end = start + len(candidate.replacement_token)
    if file_hash(path) != applied.mutated_hash or line[start:end] != candidate.replacement_token:
        raise RuntimeError("mutated specimen drifted before repair")
    repaired_line = line[:start] + candidate.original_token + line[end:]
    repaired_text = "".join(lines[:line_index] + [repaired_line] + lines[line_index + 1:])
    normalize = lambda value: value.replace("\r\n", "\n").replace("\r", "\n")
    if normalize(repaired_text) != normalize(original_bytes.decode("utf-8")):
        raise RuntimeError("bounded repair differs from the recorded original bytes")
    path.write_bytes(original_bytes)
    if file_hash(path) != applied.original_hash:
        raise RuntimeError("repair did not restore the original candidate bytes")

    _run_oracle(specimen, oracle)
    repaired = _checkpoint(
        checkpoint_root / "repaired.json",
        parent=baseline.checkpoint_id,
        source_hash=source_hash,
        specimen_hash=_digest({candidate.relative_path: file_hash(path)}),
        parameters=parameters,
        phase="REPAIRED_REPLAY",
    )
    return baseline, repaired

