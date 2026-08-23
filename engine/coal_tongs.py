from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping, Tuple
import json
import os
import shutil
import subprocess
import csv

from coal_house import coal_house_root
from engine.coal_contracts import (
    COAL_CONTRACT_FILENAME,
    CoalContract,
    coal_house_contracts,
    validate_coal_contract_payload,
)
from engine.environment_reconstruction import executable_path
from engine.coal_venvs import coal_venv_adapter, materialize_coal_venv
from engine.coal_schemas import validate_schema_payload


COAL_PACK_SCHEMA = "kiln.coal-pack.v1"
COAL_FIXTURE_SCHEMA = "kiln.coal-fixture.v1"
COAL_SPECIMEN_SCHEMA = "kiln.coal-specimen.v1"
COAL_CAPABILITY_SCHEMA = "kiln.coal-capability.v1"
COAL_QUALIFICATION_SCHEMA = "kiln.coal-qualification.v1"
COAL_CAPABILITY_MATRIX_SCHEMA = "kiln.coal-capability-matrix.v1"
COAL_SURVIVORS_SCHEMA = "kiln.coal-survivors.v1"
COAL_EVIDENCE_MANIFEST_SCHEMA = "kiln.coal-evidence-manifest.v1"
COAL_SPECIMEN_MARKER = ".kiln-coal-specimen.json"
COAL_ADJUDICATION_INBOX_ENVIRONMENT = "KILN_ADJUDICATION_INBOX"
COAL_ADJUDICATION_FILENAME = "kiln-adjudication-candidates.json"
DEFAULT_COAL_ADJUDICATION_DIRECTORY = Path(
    r"C:\Users\alexg\Desktop\AnarchI-Adjudication\To-Adjudicate"
)


@dataclass(frozen=True)
class CoalPack:
    adapter: str
    root: Path
    contract: CoalContract
    contract_hash: str
    build_systems: Tuple[str, ...]
    test_runners: Tuple[str, ...]
    environment: str
    venv_adapter: str
    runtime_probes: Tuple[Tuple[str, ...], ...]
    production_markers: Tuple[str, ...]
    fixture_path: Path


@dataclass(frozen=True)
class CoalFixture:
    adapter: str
    entry: str
    files: Tuple[tuple[str, str], ...]
    failure_output: str


@dataclass(frozen=True)
class CoalCapability:
    schema: str
    adapter: str
    languages: Tuple[str, ...]
    build_systems: Tuple[str, ...]
    test_runners: Tuple[str, ...]
    environment: str
    venv_adapter: str
    implemented: bool
    runtime_available: bool
    production_proven: bool
    metal_earned: bool
    contract_hash: str
    missing_commands: Tuple[str, ...]
    runtime_versions: Tuple[tuple[str, str], ...]
    disposition: str


@dataclass(frozen=True)
class CoalQualification:
    schema: str
    adapter: str
    contract_hash: str
    runtime_available: bool
    fixture_qualified: bool
    deterministic_replay: bool
    production_proven: bool
    metal_earned: bool
    baseline_passed: bool
    destructive_trial_passed: bool
    truthful_proof: bool
    restoration_complete: bool
    cleanup_complete: bool
    source_preserved: bool
    replay_hashes: Tuple[tuple[str, str], ...]
    mutation_candidate_count: int
    fractures_observed: int
    survivors: Tuple[str, ...]
    production_target_id: str
    production_commit: str
    production_fractures: int
    production_survivors: Tuple[str, ...]
    blockers: Tuple[str, ...]
    disposition: str


def _exact_keys(value: dict, expected: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError(
            "coal-house fields are incomplete or unknown: " + field
        )


def _canonical_strings(value, field: str, allow_empty: bool = False) -> Tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item or "\0" in item for item in value)
        or value != sorted(set(value))
        or (not value and not allow_empty)
    ):
        raise RuntimeError("coal-house field must be a canonical string list: " + field)

    return tuple(value)


def _tokenized_commands(value, field: str) -> Tuple[Tuple[str, ...], ...]:
    if not isinstance(value, list) or not value:
        raise RuntimeError("coal-house runtime probes must be a non-empty array: " + field)

    commands = []

    for command in value:
        if (
            not isinstance(command, list)
            or not command
            or any(
                not isinstance(token, str)
                or not token
                or any(character in token for character in ("\0", "\r", "\n"))
                for token in command
            )
        ):
            raise RuntimeError("coal-house runtime probe must be tokenized: " + field)

        commands.append(tuple(command))

    if commands != sorted(set(commands)):
        raise RuntimeError("coal-house runtime probes are not canonical: " + field)

    return tuple(commands)


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(label + " is unreadable: " + str(path)) from error

    if not isinstance(value, dict):
        raise RuntimeError(label + " must be an object: " + str(path))

    return value


def canonical_json_hash(value: Mapping) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _pack_from_root(pack_root: Path) -> CoalPack:
    manifest_path = pack_root / "pack.json"
    contract_path = pack_root / COAL_CONTRACT_FILENAME
    manifest = _read_json(manifest_path, "coal-house pack manifest")
    _exact_keys(
        manifest,
        {
            "adapter",
            "buildSystems",
            "environment",
            "fixture",
            "productionMarkers",
            "runtimeProbes",
            "schema",
            "testRunners",
            "venvAdapter",
        },
        "pack",
    )

    if manifest.get("schema") != COAL_PACK_SCHEMA:
        raise RuntimeError("coal-house pack uses an unsupported schema")

    adapter = manifest.get("adapter")

    if not isinstance(adapter, str) or adapter != pack_root.name:
        raise RuntimeError("coal-house pack adapter does not match its directory")

    payload = _read_json(contract_path, "coal-house contract")
    contract = validate_coal_contract_payload(
        payload,
        origin="coal-house:" + adapter,
        external=True,
    )

    if contract.adapter != adapter:
        raise RuntimeError("coal-house manifest and contract adapters differ")

    environment = manifest.get("environment")

    if environment != "specimen-local":
        raise RuntimeError("coal-house packs must declare a specimen-local environment")

    venv_name = manifest.get("venvAdapter")

    if not isinstance(venv_name, str) or not venv_name:
        raise RuntimeError("coal-house pack venv adapter reference is invalid")

    venv = coal_venv_adapter(venv_name)

    if venv.environment != contract.execution.environment:
        raise RuntimeError("coal-house contract and venv environments differ")

    fixture_name = manifest.get("fixture")

    if (
        not isinstance(fixture_name, str)
        or not fixture_name
        or Path(fixture_name).name != fixture_name
        or not fixture_name.endswith(".json")
    ):
        raise RuntimeError("coal-house fixture reference is invalid")

    fixture_path = pack_root / fixture_name

    if not fixture_path.is_file():
        raise RuntimeError("coal-house fixture is missing: " + adapter)

    validate_schema_payload(
        "kiln.coal-pack.v1.schema.json",
        manifest,
        "coal-house pack",
    )

    return CoalPack(
        adapter=adapter,
        root=pack_root,
        contract=contract,
        contract_hash=canonical_json_hash(payload),
        build_systems=_canonical_strings(manifest.get("buildSystems"), "buildSystems"),
        test_runners=_canonical_strings(manifest.get("testRunners"), "testRunners"),
        environment=environment,
        venv_adapter=venv_name,
        runtime_probes=_tokenized_commands(manifest.get("runtimeProbes"), "runtimeProbes"),
        production_markers=_canonical_strings(
            manifest.get("productionMarkers"),
            "productionMarkers",
        ),
        fixture_path=fixture_path,
    )


def discover_coal_packs(root: Path | None = None) -> Tuple[CoalPack, ...]:
    packs_root = (
        Path(root).resolve()
        if root is not None
        else coal_house_root() / "packs"
    )

    if not packs_root.is_dir():
        return ()

    packs = tuple(
        _pack_from_root(path)
        for path in sorted(
            (item for item in packs_root.iterdir() if item.is_dir()),
            key=lambda item: (item.name.casefold(), item.name),
        )
    )

    if len({pack.adapter for pack in packs}) != len(packs):
        raise RuntimeError("coal-house contains duplicate adapters")

    if root is None and set(pack.adapter for pack in packs) != set(coal_house_contracts()):
        raise RuntimeError("coal-house pack and contract discovery disagree")

    return packs


def coal_pack(adapter: str, root: Path | None = None) -> CoalPack:
    matches = tuple(pack for pack in discover_coal_packs(root) if pack.adapter == adapter)

    if len(matches) != 1:
        raise RuntimeError("coal-house pack not found: " + adapter)

    return matches[0]


def load_coal_fixture(pack: CoalPack) -> CoalFixture:
    payload = _read_json(pack.fixture_path, "coal-house fixture")
    _exact_keys(
        payload,
        {"adapter", "entry", "failureOutput", "files", "schema"},
        "fixture",
    )

    if payload.get("schema") != COAL_FIXTURE_SCHEMA or payload.get("adapter") != pack.adapter:
        raise RuntimeError("coal-house fixture identity is invalid")

    entry = payload.get("entry")
    files = payload.get("files")
    failure_output = payload.get("failureOutput")

    if not isinstance(entry, str) or not isinstance(failure_output, str) or not failure_output:
        raise RuntimeError("coal-house fixture entry or proof output is invalid")

    if not isinstance(files, dict) or not files:
        raise RuntimeError("coal-house fixture files are invalid")

    normalized = []

    for relative, content in files.items():
        path = Path(relative)

        if (
            not isinstance(relative, str)
            or not relative
            or not isinstance(content, str)
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != relative
        ):
            raise RuntimeError("coal-house fixture file escaped its root")

        normalized.append((relative, content))

    if normalized != sorted(normalized):
        raise RuntimeError("coal-house fixture files are not canonical")

    validate_schema_payload(
        "kiln.coal-fixture.v1.schema.json",
        payload,
        "coal-house fixture",
    )

    return CoalFixture(
        adapter=pack.adapter,
        entry=entry,
        files=tuple(normalized),
        failure_output=failure_output,
    )


def _empty_or_missing_directory(root: Path) -> None:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise RuntimeError("coal fixture destination must be absent or empty")


def write_coal_fixture(pack: CoalPack, root: Path) -> Path:
    """Generate a reusable source fixture without granting it pack authority."""
    root = Path(root).resolve()
    _empty_or_missing_directory(root)
    root.mkdir(parents=True, exist_ok=True)
    fixture = load_coal_fixture(pack)

    for relative, content in fixture.files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    return root


def initialize_coal_fixture_repository(pack: CoalPack, root: Path) -> Path:
    repository = write_coal_fixture(pack, root)
    commands = (
        ("git", "init", "-q", str(repository)),
        ("git", "-C", str(repository), "config", "user.email", "kiln@example.invalid"),
        ("git", "-C", str(repository), "config", "user.name", "Kiln Coal Fixture"),
        ("git", "-C", str(repository), "add", "."),
        ("git", "-C", str(repository), "commit", "-q", "-m", "deterministic coal fixture"),
    )
    environment = dict(os.environ)
    environment.update({
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    })

    for command in commands:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        if result.returncode != 0:
            raise RuntimeError("unable to initialize coal fixture repository: " + result.stderr.strip())

    return repository


def mark_coal_specimen(boundary: Path, repository: Path) -> Path:
    boundary = Path(boundary).resolve()
    repository = Path(repository).resolve()

    try:
        relative = repository.relative_to(boundary)
    except ValueError as error:
        raise RuntimeError("coal specimen repository escaped its boundary") from error

    if repository == boundary or not repository.is_dir():
        raise RuntimeError("coal specimen needs a nested repository directory")

    marker = boundary / COAL_SPECIMEN_MARKER
    marker.write_text(
        json.dumps(
            {"repository": relative.as_posix(), "schema": COAL_SPECIMEN_SCHEMA},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return marker


def _validated_specimen(boundary: Path, repository: Path) -> None:
    boundary = Path(boundary).resolve()
    repository = Path(repository).resolve()
    marker = _read_json(boundary / COAL_SPECIMEN_MARKER, "coal specimen marker")
    _exact_keys(marker, {"repository", "schema"}, "specimen marker")

    if marker.get("schema") != COAL_SPECIMEN_SCHEMA:
        raise RuntimeError("coal specimen marker uses an unsupported schema")

    expected = (boundary / str(marker.get("repository"))).resolve()

    if expected != repository or not repository.is_dir():
        raise RuntimeError("coal specimen marker does not authorize this repository")


def move_coal_pack_to_specimen(adapter: str, repository: Path, boundary: Path) -> Path:
    """Copy a library contract only into an explicitly marked disposable specimen."""
    repository = Path(repository).resolve()
    boundary = Path(boundary).resolve()
    _validated_specimen(boundary, repository)
    pack = coal_pack(adapter)
    destination = repository / COAL_CONTRACT_FILENAME
    source = pack.root / COAL_CONTRACT_FILENAME

    if destination.exists():
        if file_sha256(destination) != file_sha256(source):
            raise RuntimeError("coal specimen already contains a different contract")
        materialize_coal_venv(coal_venv_adapter(pack.venv_adapter), repository)
        return destination

    shutil.copyfile(source, destination)
    validate_coal_contract_payload(
        _read_json(destination, "moved coal contract"),
        origin=COAL_CONTRACT_FILENAME,
        external=True,
    )
    materialize_coal_venv(coal_venv_adapter(pack.venv_adapter), repository)
    return destination


def _qualification_payload(root: Path, adapter: str) -> dict | None:
    path = Path(root).resolve() / adapter / "qualification.json"

    if not path.is_file():
        return None

    payload = _read_json(path, "coal qualification evidence")

    if payload.get("schema") != COAL_QUALIFICATION_SCHEMA or payload.get("adapter") != adapter:
        raise RuntimeError("coal qualification evidence identity is invalid")

    return payload


def probe_coal_capability(
    pack: CoalPack,
    evidence_root: Path | None = None,
    timeout_seconds: float = 10.0,
) -> CoalCapability:
    if timeout_seconds <= 0:
        raise ValueError("coal capability timeout must be positive")

    missing = []
    versions = []

    for probe in pack.runtime_probes:
        executable = executable_path(probe[0])

        if not executable:
            missing.append(probe[0])
            continue

        args = [executable, *probe[1:]]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            missing.append(probe[0])
            continue

        if result.returncode != 0:
            missing.append(probe[0])
            continue

        output = (result.stdout or result.stderr or "").strip().splitlines()
        versions.append((probe[0], output[0][:240] if output else "available"))

    missing_commands = tuple(sorted(set(missing)))
    runtime_available = not missing_commands
    qualification_root = (
        Path(evidence_root).resolve()
        if evidence_root is not None
        else coal_house_root() / "evidence"
    )
    evidence = _qualification_payload(qualification_root, pack.adapter)
    production_proven = bool(
        evidence
        and evidence.get("contract_hash") == pack.contract_hash
        and evidence.get("production_proven") is True
        and evidence.get("fixture_qualified") is True
        and evidence.get("deterministic_replay") is True
    )
    metal_earned = runtime_available and production_proven
    disposition = (
        "COAL_PRODUCTION_PROVEN"
        if production_proven and runtime_available
        else "COAL_PRODUCTION_PROVEN_RUNTIME_UNAVAILABLE"
        if production_proven
        else "COAL_RUNTIME_AVAILABLE"
        if runtime_available
        else "COAL_RUNTIME_UNAVAILABLE"
    )

    return CoalCapability(
        schema=COAL_CAPABILITY_SCHEMA,
        adapter=pack.adapter,
        languages=pack.contract.languages,
        build_systems=pack.build_systems,
        test_runners=pack.test_runners,
        environment=pack.environment,
        venv_adapter=pack.venv_adapter,
        implemented=True,
        runtime_available=runtime_available,
        production_proven=production_proven,
        metal_earned=metal_earned,
        contract_hash=pack.contract_hash,
        missing_commands=missing_commands,
        runtime_versions=tuple(sorted(versions)),
        disposition=disposition,
    )


def coal_capability_matrix(evidence_root: Path | None = None) -> Tuple[CoalCapability, ...]:
    return tuple(
        probe_coal_capability(pack, evidence_root)
        for pack in discover_coal_packs()
    )


def write_capability_matrix(path: Path, capabilities: Tuple[CoalCapability, ...]) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "capabilities": [asdict(item) for item in capabilities],
        "schema": COAL_CAPABILITY_MATRIX_SCHEMA,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_capability_matrix_markdown(
    path: Path,
    capabilities: Tuple[CoalCapability, ...],
) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Kiln coal-house capability matrix",
        "",
        "Generated from validated pack contracts, live runtime probes, and qualification evidence whose contract hash matches the current pack.",
        "",
        "| Adapter | Languages | Build systems | Test runners | Venv adapter | Implemented | Runtime available | Production proven | Metal earned |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in capabilities:
        lines.append(
            "| "
            + " | ".join((
                item.adapter,
                ", ".join(item.languages),
                ", ".join(item.build_systems),
                ", ".join(item.test_runners),
                item.venv_adapter,
                "yes" if item.implemented else "no",
                "yes" if item.runtime_available else "no",
                "yes" if item.production_proven else "no",
                "yes" if item.metal_earned else "no",
            ))
            + " |"
        )

    lines.extend((
        "",
        "Unavailable runtimes are implemented contracts and fixtures only; they are not passing qualifications.",
    ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def coal_adjudication_inbox(path: Path | None = None) -> Path:
    configured = (
        Path(path)
        if path is not None
        else Path(
            os.environ.get(
                COAL_ADJUDICATION_INBOX_ENVIRONMENT,
                str(DEFAULT_COAL_ADJUDICATION_DIRECTORY),
            )
        )
    ).resolve()

    if configured.is_dir() or configured.suffix == "":
        return configured / COAL_ADJUDICATION_FILENAME

    return configured


def write_survivors(evidence_root: Path, path: Path | None = None) -> Path:
    evidence_root = Path(evidence_root).resolve()
    survivors = []

    for pack in discover_coal_packs():
        qualification_path = evidence_root / pack.adapter / "qualification.json"

        if not qualification_path.is_file():
            continue

        qualification = read_coal_qualification(pack.adapter, evidence_root)

        for campaign, mutation_ids in (
            ("fixture", qualification.survivors),
            ("production", qualification.production_survivors),
        ):
            survivors.extend({
                "adapter": pack.adapter,
                "campaign": campaign,
                "disposition": "REQUIRES_ADJUDICATION",
                "mutation_id": mutation_id,
            } for mutation_id in mutation_ids)

    survivors.sort(key=lambda item: (item["adapter"], item["campaign"], item["mutation_id"]))
    destination = coal_adjudication_inbox(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {"schema": COAL_SURVIVORS_SCHEMA, "survivors": survivors},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return destination


def write_coal_evidence_manifest(
    evidence_root: Path,
    path: Path | None = None,
) -> Path:
    """Bind every evidence bundle to its contract, pack, and venv bytes."""
    evidence_root = Path(evidence_root).resolve()
    destination = (
        Path(path).resolve()
        if path is not None
        else evidence_root / "evidence-manifest.json"
    )
    adapters = []

    for pack in discover_coal_packs():
        bundle = evidence_root / pack.adapter
        venv = coal_venv_adapter(pack.venv_adapter)
        files = {
            item.name: file_sha256(item)
            for item in sorted(
                (candidate for candidate in bundle.iterdir() if candidate.is_file()),
                key=lambda candidate: (candidate.name.casefold(), candidate.name),
            )
        } if bundle.is_dir() else {}
        adapters.append({
            "adapter": pack.adapter,
            "contractHash": pack.contract_hash,
            "files": files,
            "packManifestHash": file_sha256(pack.root / "pack.json"),
            "venvAdapter": venv.adapter,
            "venvHash": file_sha256(venv.root),
        })

    top_level_names = (
        "CAPABILITY-MATRIX.md",
        "capability-matrix.json",
        "survivors-requiring-adjudication.json",
    )
    top_level = {
        name: file_sha256(evidence_root / name)
        for name in top_level_names
        if (evidence_root / name).is_file()
    }
    payload = {
        "adapters": adapters,
        "schema": COAL_EVIDENCE_MANIFEST_SCHEMA,
        "topLevel": top_level,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def pack_matches_target(pack: CoalPack, target: Path) -> bool:
    """Report target applicability from declared markers, independent of runtime."""
    root = Path(target).resolve()

    if not root.is_dir():
        return False

    for marker in pack.production_markers:
        matches = (
            path
            for path in root.rglob(marker)
            if path.is_file() and ".git" not in path.parts
        )

        if next(matches, None) is not None:
            return True

    return False


def validate_fixture_proof(pack: CoalPack, repository: Path):
    from engine.proof_metadata import build_proof_metadata

    fixture = load_coal_fixture(pack)
    metadata = build_proof_metadata(
        repository,
        pack.adapter,
        fixture.failure_output,
        "",
        "KILN-FIXTURE-MUTATION",
        fixture.entry,
    )

    if (
        not metadata.detected_test_ids
        or not metadata.invariant_refs
        or not metadata.assertion_refs
        or not metadata.behavioral_fragment_refs
    ):
        raise RuntimeError("coal fixture proof output is malformed or incomplete")

    return metadata


def matching_replay_hashes(first: Mapping[str, str], second: Mapping[str, str]) -> bool:
    required = {"mutation-trials.csv", "proof-metadata.json"}
    return set(first) == required and set(second) == required and dict(first) == dict(second)


def _cycle_hashes(result) -> dict[str, str]:
    return {
        "mutation-trials.csv": file_sha256(Path(result.evidence_path)),
        "proof-metadata.json": file_sha256(Path(result.proof_metadata_path)),
    }


def cycle_qualifies(
    result,
    require_fracture: bool,
) -> bool:
    trials = result.trials
    truthful = all(
        not trial.fracture_observed
        or (
            trial.detected_test_ids
            and trial.invariant_refs
            and trial.assertion_refs
            and trial.behavioral_fragment_refs
        )
        for trial in trials
    )
    return bool(
        result.baseline_passed
        and result.passes_executed
        and (not require_fracture or result.fractures_observed)
        and result.execution_failures == 0
        and result.specimen_removed
        and result.original_head_preserved
        and all(trial.restored and trial.sandbox_removed for trial in trials)
        and truthful
    )


def _run_qualified_cycle(
    target: Path,
    adapter: str,
    entry: str,
    session_root: Path,
    max_passes: int,
):
    from engine.cycle_orchestrator import finalize_cycle_result, run_cycle

    return finalize_cycle_result(
        run_cycle(
            str(target),
            adapter,
            entry,
            max_passes,
            "stable",
            session_root,
        ),
        str(target),
    )


def qualification_work_parent() -> Path | None:
    """Use a short machine-local prefix where Windows linker paths require it."""
    if os.name != "nt":
        return None

    anchor = Path.cwd().anchor or os.environ.get("SystemDrive", "C:") + "\\"
    root = Path(anchor) / "kiln-tongs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def read_coal_qualification(adapter: str, evidence_root: Path) -> CoalQualification:
    payload = _qualification_payload(Path(evidence_root), adapter)

    if payload is None:
        raise RuntimeError("coal qualification evidence is missing: " + adapter)

    expected = {field.name for field in fields(CoalQualification)}
    _exact_keys(payload, expected, "qualification")

    for name in ("blockers", "production_survivors", "replay_hashes", "survivors"):
        value = payload.get(name)

        if not isinstance(value, list):
            raise RuntimeError("coal qualification list is malformed: " + name)

        payload[name] = tuple(
            tuple(item) if name == "replay_hashes" else item
            for item in value
        )

    return CoalQualification(**payload)


def reconcile_production_evidence(
    adapter: str,
    evidence_root: Path,
    production_target: Path,
) -> CoalQualification:
    """Revalidate a persisted production bundle after policy-only changes."""
    from engine.proof_metadata import validate_proof_metadata_payload
    from engine.target_intake import inspect_target

    pack = coal_pack(adapter)
    root = Path(evidence_root).resolve()
    bundle = root / adapter
    qualification = read_coal_qualification(adapter, root)

    if qualification.contract_hash != pack.contract_hash or not (
        qualification.fixture_qualified and qualification.deterministic_replay
    ):
        raise RuntimeError("coal fixture evidence is stale or unqualified")

    trials_path = bundle / "production-mutation-trials.csv"
    proof_path = bundle / "production-proof-metadata.json"

    try:
        with trials_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("coal production evidence is missing or malformed") from error

    if not rows or not isinstance(proof, dict) or not isinstance(proof.get("trials"), list):
        raise RuntimeError("coal production evidence has no trials")

    proof_by_mutation = {}

    for item in proof["trials"]:
        if not isinstance(item, dict):
            raise RuntimeError("coal production proof trial is malformed")

        mutation_id = item.get("mutation_id")
        metadata = item.get("metadata")
        validate_proof_metadata_payload(metadata, mutation_id)
        proof_by_mutation[mutation_id] = metadata

    survivors = []
    fractures = 0

    for row in rows:
        mutation_id = row.get("mutation_id", "")
        metadata = proof_by_mutation.get(mutation_id)

        if (
            metadata is None
            or row.get("restored") != "true"
            or row.get("sandbox_removed") != "true"
            or row.get("execution_error")
        ):
            raise RuntimeError("coal production trial lacks restoration or proof")

        fracture = row.get("fracture_observed") == "true"
        survived = row.get("survived") == "true"

        if fracture == survived:
            raise RuntimeError("coal production trial classification is contradictory")

        if fracture:
            fractures += 1

            if not (
                metadata.get("detected_test_ids")
                and metadata.get("invariant_refs")
                and metadata.get("assertion_refs")
                and metadata.get("behavioral_fragment_refs")
            ):
                raise RuntimeError("coal production fracture proof is incomplete")
        else:
            survivors.append(mutation_id)

    if set(proof_by_mutation) != {row.get("mutation_id") for row in rows}:
        raise RuntimeError("coal production proof and trial populations differ")

    identity = inspect_target(Path(production_target).resolve())

    if (
        not identity.git_repository
        or not identity.repository_clean
        or identity.source_commit != qualification.production_commit
        or identity.target_id != qualification.production_target_id
    ):
        raise RuntimeError("coal production source repository changed after campaign")

    worktrees = subprocess.run(
        ["git", "-C", identity.repository_root, "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )

    if worktrees.returncode != 0 or sum(
        line.startswith("worktree ") for line in worktrees.stdout.splitlines()
    ) != 1:
        raise RuntimeError("coal production worktree cleanup is incomplete")

    reconciled = replace(
        qualification,
        production_proven=True,
        metal_earned=True,
        production_fractures=fractures,
        production_survivors=tuple(survivors),
        blockers=tuple(
            blocker
            for blocker in qualification.blockers
            if not blocker.startswith("production-shaped repository proof")
        ),
        disposition="COAL_METAL_EARNED",
    )
    (bundle / "qualification.json").write_text(
        json.dumps(asdict(reconciled), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_survivors(root)
    return reconciled


def qualify_coal_pack(
    adapter: str,
    evidence_root: Path,
    production_target: Path | None = None,
    production_entry: str = "",
    production_passes: int = 8,
) -> CoalQualification:
    """Exercise one pack twice, persist evidence, and optionally prove a real target."""
    pack = coal_pack(adapter)
    capability = probe_coal_capability(pack, evidence_root)
    evidence_root = Path(evidence_root).resolve()
    bundle = evidence_root / adapter
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "capability.json").write_text(
        json.dumps(asdict(capability), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    blockers = []

    if not capability.runtime_available:
        blockers.append("runtime unavailable: " + ", ".join(capability.missing_commands))
        qualification = CoalQualification(
            schema=COAL_QUALIFICATION_SCHEMA,
            adapter=adapter,
            contract_hash=pack.contract_hash,
            runtime_available=False,
            fixture_qualified=False,
            deterministic_replay=False,
            production_proven=False,
            metal_earned=False,
            baseline_passed=False,
            destructive_trial_passed=False,
            truthful_proof=False,
            restoration_complete=False,
            cleanup_complete=False,
            source_preserved=False,
            replay_hashes=(),
            mutation_candidate_count=0,
            fractures_observed=0,
            survivors=(),
            production_target_id="",
            production_commit="",
            production_fractures=0,
            production_survivors=(),
            blockers=tuple(blockers),
            disposition="COAL_QUALIFICATION_BLOCKED_RUNTIME_UNAVAILABLE",
        )
        (bundle / "qualification.json").write_text(
            json.dumps(asdict(qualification), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_survivors(evidence_root)
        return qualification

    fixture = load_coal_fixture(pack)

    with TemporaryDirectory(
        prefix="kq-",
        dir=qualification_work_parent(),
    ) as temp:
        work = Path(temp)
        source = initialize_coal_fixture_repository(pack, work / "source")
        validate_fixture_proof(pack, source)
        first = _run_qualified_cycle(source, adapter, fixture.entry, work / "replay-1", 1)
        second = _run_qualified_cycle(source, adapter, fixture.entry, work / "replay-2", 1)
        first_hashes = _cycle_hashes(first)
        second_hashes = _cycle_hashes(second)
        deterministic = matching_replay_hashes(first_hashes, second_hashes)
        fixture_qualified = cycle_qualifies(first, require_fracture=True) and cycle_qualifies(
            second,
            require_fracture=True,
        ) and deterministic
        shutil.copyfile(first.evidence_path, bundle / "mutation-trials.csv")
        shutil.copyfile(first.proof_metadata_path, bundle / "proof-metadata.json")

        production = None

        if production_target is not None and not pack_matches_target(
            pack,
            Path(production_target),
        ):
            blockers.append("production target does not match declared pack markers")
        elif production_target is not None:
            production = _run_qualified_cycle(
                Path(production_target).resolve(),
                adapter,
                production_entry,
                work / "production",
                production_passes,
            )
            shutil.copyfile(production.evidence_path, bundle / "production-mutation-trials.csv")
            shutil.copyfile(production.proof_metadata_path, bundle / "production-proof-metadata.json")

        production_proven = bool(
            production
            and cycle_qualifies(
                production,
                require_fracture=False,
            )
        )

        if not fixture_qualified:
            blockers.append("fixture conformance or deterministic replay failed")

        if not production_proven:
            blockers.append("production-shaped repository proof is absent or failed")

        replay_hashes = tuple(sorted(first_hashes.items())) if deterministic else ()
        production_survivors = tuple(
            trial.mutation_id for trial in production.trials if trial.survived
        ) if production else ()
        qualification = CoalQualification(
            schema=COAL_QUALIFICATION_SCHEMA,
            adapter=adapter,
            contract_hash=pack.contract_hash,
            runtime_available=True,
            fixture_qualified=fixture_qualified,
            deterministic_replay=deterministic,
            production_proven=production_proven,
            metal_earned=fixture_qualified and production_proven,
            baseline_passed=first.baseline_passed and second.baseline_passed,
            destructive_trial_passed=first.passes_executed == 1 and second.passes_executed == 1,
            truthful_proof=all(
                trial.detected_test_ids
                and trial.invariant_refs
                and trial.assertion_refs
                and trial.behavioral_fragment_refs
                for result in (first, second)
                for trial in result.trials
                if trial.fracture_observed
            ),
            restoration_complete=all(
                trial.restored for result in (first, second) for trial in result.trials
            ),
            cleanup_complete=first.specimen_removed and second.specimen_removed,
            source_preserved=first.original_head_preserved and second.original_head_preserved,
            replay_hashes=replay_hashes,
            mutation_candidate_count=first.mutation_candidate_count,
            fractures_observed=first.fractures_observed,
            survivors=tuple(trial.mutation_id for trial in first.trials if trial.survived),
            production_target_id=production.target_id if production else "",
            production_commit=production.source_commit if production else "",
            production_fractures=production.fractures_observed if production else 0,
            production_survivors=production_survivors,
            blockers=tuple(blockers),
            disposition=(
                "COAL_METAL_EARNED"
                if fixture_qualified and production_proven
                else "COAL_FIXTURE_QUALIFIED_PRODUCTION_PENDING"
                if fixture_qualified
                else "COAL_QUALIFICATION_FAILED"
            ),
        )

    (bundle / "qualification.json").write_text(
        json.dumps(asdict(qualification), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_survivors(evidence_root)
    return qualification
