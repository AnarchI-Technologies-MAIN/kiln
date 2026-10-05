"""Bounded, specimen-only repair lineage slice.

This is deliberately one deterministic repair operator: restore the exact
source token changed by a qualified mutation candidate, then replay the same
oracle. It does not infer intent, edit upstream source, or claim hostile
containment.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import shutil
import zipfile
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
    snapshot_path: str
    snapshot_hash: str


@dataclass(frozen=True)
class RepairSpec:
    relative_path: str
    line: int
    column: int
    expected_token: str
    replacement_token: str


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _manifest(specimen: Path) -> list[dict[str, str]]:
    rows = []
    for path in sorted(Path(specimen).rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.name == ".kiln-manifest.json":
            continue
        rows.append({"path": path.relative_to(specimen).as_posix(), "sha256": file_hash(path)})
    return rows


def _snapshot(specimen: Path, archive: Path) -> tuple[str, str]:
    manifest = _manifest(specimen)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for row in manifest:
            bundle.write(Path(specimen) / row["path"], row["path"])
        bundle.writestr(".kiln-manifest.json", json.dumps(manifest, sort_keys=True))
    os.replace(temporary, archive)
    return _digest(manifest), hashlib.sha256(archive.read_bytes()).hexdigest()


def _restore_snapshot(checkpoint: Checkpoint, destination: Path) -> str:
    archive = Path(checkpoint.snapshot_path)
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != checkpoint.snapshot_hash:
        raise RuntimeError("checkpoint snapshot is missing or tampered")
    if destination.exists():
        raise RuntimeError("restore destination already exists")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    return _digest(_manifest(destination))


def _checkpoint(path: Path, specimen: Path, *, parent: str | None, source_hash: str,
                specimen_hash: str, parameters: dict, phase: str) -> Checkpoint:
    snapshot_path = path.with_suffix(".zip")
    if path.exists() or snapshot_path.exists():
        raise RuntimeError("checkpoint path already exists")
    parameters_hash = _digest(parameters)
    tree_hash, snapshot_hash = _snapshot(specimen, snapshot_path)
    specimen_hash = tree_hash
    checkpoint_id = "KILN-CHECKPOINT-" + _digest({
        "parent": parent,
        "source_hash": source_hash,
        "specimen_hash": specimen_hash,
        "parameters_hash": parameters_hash,
        "phase": phase,
    })[:24].upper()
    result = Checkpoint(checkpoint_id, parent, source_hash, specimen_hash,
                        parameters_hash, phase, str(snapshot_path), snapshot_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return result


def verify_checkpoint(path: Path, expected_parameters: dict | None = None) -> Checkpoint:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        result = Checkpoint(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("checkpoint is malformed") from exc
    expected_id = "KILN-CHECKPOINT-" + _digest({
        "parent": result.parent_checkpoint_id,
        "source_hash": result.source_hash,
        "specimen_hash": result.specimen_hash,
        "parameters_hash": result.parameters_hash,
        "phase": result.phase,
    })[:24].upper()
    if result.checkpoint_id != expected_id:
        raise RuntimeError("checkpoint identity is tampered")
    if expected_parameters is not None and result.parameters_hash != _digest(expected_parameters):
        raise RuntimeError("checkpoint parameters are stale")
    if not Path(result.snapshot_path).is_file() or hashlib.sha256(Path(result.snapshot_path).read_bytes()).hexdigest() != result.snapshot_hash:
        raise RuntimeError("checkpoint snapshot is missing or tampered")
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
    if parameters.get("repair_budget") != 1:
        raise RuntimeError("bounded repair slice requires exactly one repair budget")
    source_path = specimen / candidate.relative_path
    original_bytes = source_path.read_bytes()
    source_hash = file_hash(source_path)
    _run_oracle(specimen, oracle)
    baseline = _checkpoint(
        checkpoint_root / "baseline.json",
        specimen,
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
        specimen,
        parent=baseline.checkpoint_id,
        source_hash=source_hash,
        specimen_hash=_digest({candidate.relative_path: file_hash(path)}),
        parameters=parameters,
        phase="REPAIRED_REPLAY",
    )
    if _restore_snapshot(baseline, checkpoint_root / "baseline-restore") != baseline.specimen_hash:
        raise RuntimeError("baseline restore verification failed")
    if _restore_snapshot(repaired, checkpoint_root / "repaired-restore") != repaired.specimen_hash:
        raise RuntimeError("repaired restore verification failed")
    return baseline, repaired


def repair_under_same_oracle(
    specimen: Path,
    repair: RepairSpec,
    regression_oracle: list[str],
    adverse_oracle: list[str],
    checkpoint_root: Path,
    parameters: dict,
) -> tuple[Checkpoint, Checkpoint]:
    """Apply one explicit repair, then replay the identical adverse oracle."""
    specimen = Path(specimen).resolve()
    if parameters.get("repair_budget") != 1:
        raise RuntimeError("bounded repair slice requires exactly one repair budget")
    path = specimen / repair.relative_path
    original_bytes = path.read_bytes()
    source_hash = file_hash(path)
    _run_oracle(specimen, regression_oracle)
    try:
        _run_oracle(specimen, adverse_oracle)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("adverse oracle did not establish a failure")
    baseline = _checkpoint(
        checkpoint_root / "baseline.json",
        specimen,
        parent=None,
        source_hash=source_hash,
        specimen_hash=_digest({repair.relative_path: source_hash}),
        parameters=parameters,
        phase="BASELINE",
    )

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = repair.line - 1
    if index < 0 or index >= len(lines):
        raise RuntimeError("repair line exceeds specimen")
    line = lines[index]
    end = repair.column + len(repair.expected_token)
    if line[repair.column:end] != repair.expected_token:
        raise RuntimeError("repair token no longer matches specimen")
    lines[index] = line[:repair.column] + repair.replacement_token + line[end:]
    path.write_text("".join(lines), encoding="utf-8", newline="")
    _run_oracle(specimen, regression_oracle)
    _run_oracle(specimen, adverse_oracle)
    repaired = _checkpoint(
        checkpoint_root / "repaired.json",
        specimen,
        parent=baseline.checkpoint_id,
        source_hash=source_hash,
        specimen_hash=_digest({repair.relative_path: file_hash(path)}),
        parameters=parameters,
        phase="REPAIRED_REPLAY",
    )
    if _restore_snapshot(baseline, checkpoint_root / "baseline-restore") != baseline.specimen_hash:
        raise RuntimeError("baseline restore verification failed")
    if _restore_snapshot(repaired, checkpoint_root / "repaired-restore") != repaired.specimen_hash:
        raise RuntimeError("repaired restore verification failed")
    if not path.exists() or original_bytes == path.read_bytes():
        raise RuntimeError("repair did not produce a successor specimen state")
    return baseline, repaired

