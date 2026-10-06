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
        if ".git" in path.parts or path.name == ".kiln-manifest.json":
            continue
        if path.is_symlink():
            raise RuntimeError("bounded specimen rejects symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError("bounded specimen permits regular files only")
        rows.append({"path": path.relative_to(specimen).as_posix(), "sha256": file_hash(path)})
    return rows


def _fsync_directory(directory: Path) -> None:
    """Fsync a directory where the platform exposes directory descriptors."""
    try:
        directory_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        # Windows does not expose fsync-able directory handles. File fsync and
        # atomic replace still apply there; Linux runners get the directory
        # durability barrier required for crash-safe publication.
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _snapshot(specimen: Path, archive: Path, *, fault_inject: bool = False) -> tuple[str, str]:
    manifest = _manifest(specimen)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for row in manifest:
            bundle.write(Path(specimen) / row["path"], row["path"])
        bundle.writestr(".kiln-manifest.json", json.dumps(manifest, sort_keys=True))
    # The archive bytes must reach stable storage before the directory entry is
    # published.  A directory fsync alone does not make a newly-created ZIP
    # durable across an interrupted publication.
    archive_fd = os.open(temporary, os.O_RDWR)
    try:
        os.fsync(archive_fd)
    finally:
        os.close(archive_fd)
    if fault_inject:
        raise RuntimeError("fault injected during snapshot publication")
    os.replace(temporary, archive)
    _fsync_directory(archive.parent)
    return _digest(manifest), hashlib.sha256(archive.read_bytes()).hexdigest()


def _restore_snapshot(checkpoint: Checkpoint, destination: Path) -> str:
    archive = Path(checkpoint.snapshot_path)
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != checkpoint.snapshot_hash:
        raise RuntimeError("checkpoint snapshot is missing or tampered")
    if destination.exists():
        raise RuntimeError("restore destination already exists")
    temporary = destination.with_name(destination.name + ".restore-tmp")
    if temporary.exists():
        raise RuntimeError("stale restore staging directory exists")
    temporary.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = [member.filename for member in bundle.infolist()]
            if len(names) != len(set(names)):
                raise RuntimeError("checkpoint archive contains duplicate members")
            for member in bundle.infolist():
                member_path = Path(member.filename)
                if member.filename.startswith("/") or ".." in member_path.parts:
                    raise RuntimeError("checkpoint archive contains an escaped member")
                if member.filename.endswith("/") and member.filename != ".kiln-manifest.json":
                    raise RuntimeError("checkpoint archive contains an unsupported directory")
                if member.filename != ".kiln-manifest.json" and (member.external_attr >> 16) & 0o170000 != 0o100000:
                    raise RuntimeError("checkpoint archive contains a non-regular member")
            bundle.extractall(temporary)
        manifest_path = temporary / ".kiln-manifest.json"
        try:
            embedded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("checkpoint manifest is malformed") from exc
        if embedded_manifest != sorted(embedded_manifest, key=lambda row: row.get("path", "")):
            raise RuntimeError("checkpoint manifest is not canonical")
        manifest_names = [row.get("path") for row in embedded_manifest]
        if any(not isinstance(name, str) for name in manifest_names) or len(manifest_names) != len(set(manifest_names)):
            raise RuntimeError("checkpoint manifest contains duplicate or invalid paths")
        archive_file_names = sorted(
            name for name in names if name != ".kiln-manifest.json"
        )
        if archive_file_names != sorted(manifest_names):
            raise RuntimeError("checkpoint archive members do not match manifest")
        if _digest(embedded_manifest) != checkpoint.specimen_hash:
            raise RuntimeError("checkpoint manifest does not match identity")
        if _manifest(temporary) != embedded_manifest:
            raise RuntimeError("checkpoint extracted files do not match manifest")
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _digest(_manifest(destination))


def _checkpoint(path: Path, specimen: Path, *, parent: str | None, source_hash: str,
                specimen_hash: str, parameters: dict, phase: str) -> Checkpoint:
    snapshot_path = path.with_suffix(".zip")
    if path.exists():
        raise RuntimeError("checkpoint path already exists")
    if snapshot_path.exists():
        snapshot_path.unlink()
    parameters_hash = _digest(parameters)
    tree_hash, snapshot_hash = _snapshot(
        specimen,
        snapshot_path,
        fault_inject=parameters.get("fault_inject") == "after_archive_fsync",
    )
    if parameters.get("fault_inject") == "after_archive_publish":
        raise RuntimeError("fault injected after archive publication")
    specimen_hash = tree_hash
    checkpoint_id = "KILN-CHECKPOINT-" + _digest({
        "parent": parent,
        "source_hash": source_hash,
        "specimen_hash": specimen_hash,
        "parameters_hash": parameters_hash,
        "phase": phase,
        "snapshot_path": str(snapshot_path),
        "snapshot_hash": snapshot_hash,
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
    _fsync_directory(path.parent)
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
        "snapshot_path": result.snapshot_path,
        "snapshot_hash": result.snapshot_hash,
    })[:24].upper()
    if result.checkpoint_id != expected_id:
        raise RuntimeError("checkpoint identity is tampered")
    if expected_parameters is not None and result.parameters_hash != _digest(expected_parameters):
        raise RuntimeError("checkpoint parameters are stale")
    if not Path(result.snapshot_path).is_file() or hashlib.sha256(Path(result.snapshot_path).read_bytes()).hexdigest() != result.snapshot_hash:
        raise RuntimeError("checkpoint snapshot is missing or tampered")
    return result


def _safe_target(specimen: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError("repair target must be a relative path without parent traversal")
    target = (specimen / candidate).resolve()
    if not target.is_relative_to(specimen):
        raise RuntimeError("repair target escaped specimen")
    if target.is_symlink():
        raise RuntimeError("repair target may not be a symlink")
    return target


def _run_oracle(specimen: Path, command: list[str], *, allow_failure: bool = False):
    try:
        result = subprocess.run(command, cwd=specimen, capture_output=True, text=True, timeout=30)
        if result.returncode and not allow_failure:
            raise RuntimeError(f"oracle failed: {result.returncode}")
        return result
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("oracle timeout") from exc
    except OSError as exc:
        raise RuntimeError("oracle launch failure") from exc


def _oracle_hashes(specimen: Path, oracle_files: tuple[str, ...]) -> dict[str, str]:
    hashes = {}
    for relative in oracle_files:
        path = _safe_target(specimen, relative)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("oracle file must be a regular file")
        hashes[relative] = file_hash(path)
    return hashes


def _assert_oracle_unchanged(specimen: Path, frozen: dict[str, str]) -> None:
    if _oracle_hashes(specimen, tuple(frozen)) != frozen:
        raise RuntimeError("oracle file changed during repair")


def run_bounded_repair_lineage(
    specimen: Path,
    repair: RepairSpec,
    regression_oracle: list[str],
    adverse_oracle: list[str],
    checkpoint_root: Path,
    parameters: dict,
    oracle_files: tuple[str, ...] = (),
) -> tuple[Checkpoint, Checkpoint]:
    """Operational one-repair lineage: restore, repair, replay, and verify."""
    if parameters.get("repair_budget") != 1:
        raise RuntimeError("bounded repair slice requires exactly one repair budget")
    specimen = Path(specimen).resolve()
    baseline = _checkpoint(
        Path(checkpoint_root) / "baseline.json",
        specimen,
        parent=None,
        source_hash=file_hash(_safe_target(specimen, repair.relative_path)),
        specimen_hash="",
        parameters={
            **parameters,
            "regression_oracle": list(regression_oracle),
            "adverse_oracle": list(adverse_oracle),
            "repair": asdict(repair),
            "oracle_files": list(oracle_files),
        },
        phase="BASELINE",
    )
    repair_root = Path(checkpoint_root) / "repair-input"
    if _restore_snapshot(baseline, repair_root) != baseline.specimen_hash:
        raise RuntimeError("baseline restore before repair failed")
    frozen_oracles = _oracle_hashes(repair_root, oracle_files)
    regression = _run_oracle(repair_root, regression_oracle)
    _assert_oracle_unchanged(repair_root, frozen_oracles)
    adverse = _run_oracle(repair_root, adverse_oracle, allow_failure=True)
    _assert_oracle_unchanged(repair_root, frozen_oracles)
    expected_exit = parameters.get("expected_adverse_exit_code", 1)
    expected_marker = parameters.get("expected_adverse_marker")
    if regression.returncode != 0:
        raise RuntimeError("regression oracle infrastructure or baseline failure")
    if adverse.returncode != expected_exit or (
        expected_marker is not None
        and expected_marker not in (adverse.stdout or "") + (adverse.stderr or "")
    ):
        raise RuntimeError("adverse oracle did not establish an expected assertion failure")
    target = _safe_target(repair_root, repair.relative_path)
    if repair.relative_path in oracle_files:
        raise RuntimeError("repair target is an oracle file")
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    index = repair.line - 1
    if index < 0 or index >= len(lines):
        raise RuntimeError("repair line exceeds specimen")
    line = lines[index]
    end = repair.column + len(repair.expected_token)
    if line[repair.column:end] != repair.expected_token:
        raise RuntimeError("repair token no longer matches specimen")
    lines[index] = line[:repair.column] + repair.replacement_token + line[end:]
    target.write_text("".join(lines), encoding="utf-8", newline="")
    _assert_oracle_unchanged(repair_root, frozen_oracles)
    if _run_oracle(repair_root, regression_oracle).returncode != 0:
        raise RuntimeError("repaired regression oracle failed")
    _assert_oracle_unchanged(repair_root, frozen_oracles)
    if _run_oracle(repair_root, adverse_oracle).returncode != 0:
        raise RuntimeError("repaired adverse oracle failed")
    _assert_oracle_unchanged(repair_root, frozen_oracles)
    successor = _checkpoint(
        Path(checkpoint_root) / "successor.json",
        repair_root,
        parent=baseline.checkpoint_id,
        source_hash=file_hash(target),
        specimen_hash="",
        parameters={
            **parameters,
            "regression_oracle": list(regression_oracle),
            "adverse_oracle": list(adverse_oracle),
            "repair": asdict(repair),
            "oracle_files": list(oracle_files),
        },
        phase="REPAIRED_REPLAY",
    )
    if _restore_snapshot(successor, Path(checkpoint_root) / "successor-restore") != successor.specimen_hash:
        raise RuntimeError("successor restore verification failed")
    if _restore_snapshot(baseline, Path(checkpoint_root) / "baseline-restore") != baseline.specimen_hash:
        raise RuntimeError("baseline restore verification failed")
    return baseline, successor


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
    source_path = _safe_target(specimen, candidate.relative_path)
    original_bytes = source_path.read_bytes()
    source_hash = file_hash(source_path)
    _run_oracle(specimen, oracle)
    bound_parameters = dict(parameters)
    bound_parameters.update({"oracle": list(oracle), "candidate": asdict(candidate)})
    baseline = _checkpoint(
        checkpoint_root / "baseline.json",
        specimen,
        parent=None,
        source_hash=source_hash,
        specimen_hash=_digest({candidate.relative_path: source_hash}),
        parameters=bound_parameters,
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

    path = _safe_target(specimen, candidate.relative_path)
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
        parameters=bound_parameters,
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
    path = _safe_target(specimen, repair.relative_path)
    original_bytes = path.read_bytes()
    source_hash = file_hash(path)
    _run_oracle(specimen, regression_oracle)
    try:
        _run_oracle(specimen, adverse_oracle)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("adverse oracle did not establish a failure")
    bound_parameters = dict(parameters)
    bound_parameters.update({
        "regression_oracle": list(regression_oracle),
        "adverse_oracle": list(adverse_oracle),
        "repair": asdict(repair),
    })
    baseline = _checkpoint(
        checkpoint_root / "baseline.json",
        specimen,
        parent=None,
        source_hash=source_hash,
        specimen_hash=_digest({repair.relative_path: source_hash}),
        parameters=bound_parameters,
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
        parameters=bound_parameters,
        phase="REPAIRED_REPLAY",
    )
    if _restore_snapshot(baseline, checkpoint_root / "baseline-restore") != baseline.specimen_hash:
        raise RuntimeError("baseline restore verification failed")
    if _restore_snapshot(repaired, checkpoint_root / "repaired-restore") != repaired.specimen_hash:
        raise RuntimeError("repaired restore verification failed")
    if not path.exists() or original_bytes == path.read_bytes():
        raise RuntimeError("repair did not produce a successor specimen state")
    return baseline, repaired

