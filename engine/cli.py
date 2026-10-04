from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

from engine.environment_reconstruction import (
    ReconstructionResult,
    adjudicate_reconstruction,
    host_capabilities,
    reconstruct_api_service,
    reconstruct_javascript,
    reconstruct_powershell,
    reconstruct_python,
    reconstruct_wsl2,
)
from engine.target_intake import inspect_target
from engine.frankentest import approve_frankentest, frankentest
from engine.coal_contracts import resolve_coal_contract
from engine.coal_tongs import (
    coal_capability_matrix,
    coal_pack,
    qualify_coal_pack,
    write_coal_fixture,
)
from engine.coal_venvs import discover_coal_venvs
from engine.cycle_orchestrator import (
    finalize_cycle_result,
    run_cycle,
)
from engine.version import VERSION
from engine.cli_workflows import (
    inspect_candidates,
    inspect_surfaces,
    preflight_target,
    prove_target,
    run_target_baseline,
)
from engine.cli_advanced import (
    contract_summary,
    evidence_summary,
    fragment_summary,
    materialize_graph,
    pressure_cycle,
    promote_artifact,
    redesign_summary,
    targeted_inject,
)


def serialize(value):
    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, tuple):
        return [serialize(item) for item in value]

    if isinstance(value, list):
        return [serialize(item) for item in value]

    if isinstance(value, dict):
        return {
            key: serialize(item)
            for key, item in value.items()
        }

    return value


def emit(value, json_mode: bool):
    payload = serialize(value)

    if json_mode:
        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if isinstance(payload, dict):
        for key, item in payload.items():
            print(f"{key}={item}")
        return

    if isinstance(payload, list):
        for item in payload:
            print(item)
        return

    print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kiln",
        description=(
            "Deterministic destructive software testing "
            "and constructive redesign."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"kiln {VERSION}",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    version = commands.add_parser(
        "version",
        help="Print the installed Kiln version.",
    )
    version.add_argument(
        "--json",
        action="store_true",
    )

    inspect = commands.add_parser(
        "inspect",
        help="Identify a local or remote target.",
    )
    inspect.add_argument("target")
    inspect.add_argument(
        "--json",
        action="store_true",
    )

    capabilities = commands.add_parser(
        "capabilities",
        help="Show reconstruction backends available on this host.",
    )
    capabilities.add_argument(
        "--json",
        action="store_true",
    )

    coal = commands.add_parser(
        "coal",
        help="Validate and inspect a normalized language coal contract.",
    )
    coal.add_argument("target")
    coal.add_argument(
        "--adapter",
        required=True,
        metavar="COAL",
    )
    coal.add_argument("--json", action="store_true")

    coal_house = commands.add_parser(
        "coal-house",
        help="Report implemented, runtime-available, and production-proven coals.",
    )
    coal_house.add_argument("--evidence-root", type=Path)
    coal_house.add_argument("--json", action="store_true")

    coal_venvs = commands.add_parser(
        "coal-venvs",
        help="Report reusable specimen-local environment adapters.",
    )
    coal_venvs.add_argument("--json", action="store_true")

    coal_fixture = commands.add_parser(
        "coal-fixture",
        help="Generate one reusable adapter conformance fixture.",
    )
    coal_fixture.add_argument("destination", type=Path)
    coal_fixture.add_argument("--adapter", required=True, metavar="COAL")
    coal_fixture.add_argument("--json", action="store_true")

    coal_qualify = commands.add_parser(
        "coal-qualify",
        help="Run replayed isolated qualification for one coal pack.",
    )
    coal_qualify.add_argument("--adapter", required=True, metavar="COAL")
    coal_qualify.add_argument("--evidence-root", type=Path, required=True)
    coal_qualify.add_argument("--production-target", type=Path)
    coal_qualify.add_argument("--production-entry", default="")
    coal_qualify.add_argument("--production-passes", type=int, default=8)
    coal_qualify.add_argument("--destructive", action="store_true")
    coal_qualify.add_argument("--json", action="store_true")

    reconstruct = commands.add_parser(
        "reconstruct",
        help="Materialize and prove an isolated target specimen.",
    )
    reconstruct.add_argument("target")
    reconstruct.add_argument(
        "--adapter",
        required=True,
        metavar="COAL",
    )
    reconstruct.add_argument(
        "--entry",
        required=True,
    )
    reconstruct.add_argument(
        "--json",
        action="store_true",
    )

    operational = (
        ("baseline", "Execute a non-mutating isolated baseline."),
        ("surfaces", "Inventory target mutation surfaces."),
        ("candidates", "Inventory deterministic mutation candidates."),
        ("preflight", "Validate target readiness for a bounded cycle."),
        ("prove", "Prove target readiness without destructive mutation."),
    )

    for name, help_text in operational:
        command = commands.add_parser(
            name,
            help=help_text,
        )

        command.add_argument(
            "target"
        )

        command.add_argument(
            "--adapter",
            required=True,
            metavar="COAL",
        )

        command.add_argument(
            "--entry",
            default="tests",
        )

        command.add_argument(
            "--json",
            action="store_true",
        )

    pressure = commands.add_parser(
        "pressure",
        help="Run bounded repeated destructive mutation pressure.",
    )
    pressure.add_argument("target")
    pressure.add_argument(
        "--adapter",
        required=True,
        metavar="COAL",
    )
    pressure.add_argument("--entry", default="tests")
    pressure.add_argument("--max-passes", type=int, default=4)
    pressure.add_argument("--workers", type=int, default=1)
    pressure.add_argument("--session-root", type=Path)
    pressure.add_argument("--destructive", action="store_true")
    pressure.add_argument("--json", action="store_true")

    inject = commands.add_parser(
        "inject",
        help="Execute one explicit deterministic mutation candidate.",
    )
    inject.add_argument("target")
    inject.add_argument(
        "--adapter",
        required=True,
        metavar="COAL",
    )
    inject.add_argument("--entry", default="tests")
    inject.add_argument("--candidate-id", required=True)
    inject.add_argument("--session-root", type=Path)
    inject.add_argument("--destructive", action="store_true")
    inject.add_argument("--json", action="store_true")

    evidence = commands.add_parser(
        "evidence",
        help="Summarize persisted cycle evidence for a target.",
    )
    evidence.add_argument("target")
    evidence.add_argument("--session-root", type=Path)
    evidence.add_argument("--json", action="store_true")

    graph = commands.add_parser(
        "graph",
        help="Materialize compatibility graph edges from cycle evidence.",
    )
    graph.add_argument("target")
    graph.add_argument("--session-root", type=Path)
    graph.add_argument("--json", action="store_true")

    fragments = commands.add_parser(
        "fragments",
        help="Discover immutable Python behavioral fragments.",
    )
    fragments.add_argument("target")
    fragments.add_argument("--source", required=True)
    fragments.add_argument("--json", action="store_true")

    franken = commands.add_parser(
        "frankentest",
        help="Compose source-bound proven segments and qualify new test candidates.",
    )
    franken.add_argument("target")
    franken.add_argument("--evidence", type=Path, required=True)
    franken.add_argument("--output", type=Path, required=True)
    franken.add_argument("--adapter", default="auto")
    franken.add_argument("--max-candidates", type=int, default=8)
    franken.add_argument("--timeout", type=float, default=30)
    franken.add_argument("--destructive", action="store_true")
    franken.add_argument("--json", action="store_true")

    approval = commands.add_parser("frankentest-approve", help="Pin, requalify and explicitly approve a shared test candidate.")
    approval.add_argument("target")
    approval.add_argument("--candidate", type=Path, required=True)
    approval.add_argument("--evidence", type=Path, required=True)
    approval.add_argument("--expected-sha256", required=True)
    approval.add_argument("--authority-ref", required=True)
    approval.add_argument("--registry", type=Path, required=True)
    approval.add_argument("--timeout", type=float, default=30)
    approval.add_argument("--approve", action="store_true")
    approval.add_argument("--json", action="store_true")

    contracts = commands.add_parser(
        "contracts",
        help="Draft a synthetic contract from observed compatibility evidence.",
    )
    contracts.add_argument("target")
    contracts.add_argument("--session-root", type=Path)
    contracts.add_argument("--capability", required=True)
    contracts.add_argument("--attack-surface", required=True)
    contracts.add_argument("--environment", default="")
    contracts.add_argument("--dependency", default="")
    contracts.add_argument("--json", action="store_true")

    redesign = commands.add_parser(
        "redesign",
        help="Stage, scan, and adjudicate a redesign artifact.",
    )
    redesign.add_argument("target")
    redesign.add_argument("--artifact", required=True)
    redesign.add_argument("--staging-root", type=Path, required=True)
    redesign.add_argument("--provenance", required=True)
    redesign.add_argument("--baseline-preserved", action="store_true")
    redesign.add_argument("--fracture-mitigated", action="store_true")
    redesign.add_argument("--json", action="store_true")

    adjudicate = commands.add_parser(
        "adjudicate",
        help="Alias the Core 030 redesign adjudication boundary.",
    )
    adjudicate.add_argument("target")
    adjudicate.add_argument("--artifact", required=True)
    adjudicate.add_argument("--staging-root", type=Path, required=True)
    adjudicate.add_argument("--provenance", required=True)
    adjudicate.add_argument("--baseline-preserved", action="store_true")
    adjudicate.add_argument("--fracture-mitigated", action="store_true")
    adjudicate.add_argument("--json", action="store_true")

    promote = commands.add_parser(
        "promote",
        help="Promote an approved redesign through Core 030.",
    )
    promote.add_argument("target")
    promote.add_argument("--artifact", required=True)
    promote.add_argument("--staging-root", type=Path, required=True)
    promote.add_argument("--provenance", required=True)
    promote.add_argument("--destination", required=True)
    promote.add_argument("--expected-head", required=True)
    promote.add_argument("--remote", default="origin")
    promote.add_argument("--branch", required=True)
    promote.add_argument("--message", required=True)
    promote.add_argument("--baseline-preserved", action="store_true")
    promote.add_argument("--fracture-mitigated", action="store_true")
    promote.add_argument("--approve", action="store_true")
    promote.add_argument("--json", action="store_true")
    cycle = commands.add_parser(
        "cycle",
        help=(
            "Run bounded destructive mutation cycles "
            "inside reconstructed specimens."
        ),
    )
    cycle.add_argument("target")
    cycle.add_argument(
        "--adapter",
        metavar="COAL",
        default="python",
    )
    cycle.add_argument(
        "--entry",
        default="tests",
    )
    cycle.add_argument(
        "--destructive",
        action="store_true",
        help=(
            "Explicitly authorize destructive operations "
            "inside Kiln's isolated specimen boundary."
        ),
    )
    cycle.add_argument(
        "--max-passes",
        type=int,
        default=1,
    )
    cycle.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Run stable-cycle mutation trials in isolated parallel sandboxes."
        ),
    )
    cycle.add_argument(
        "--until",
        choices=(
            "fracture",
            "stable",
            "adjudication",
        ),
        default="adjudication",
    )
    cycle.add_argument(
        "--session-root",
        type=Path,
    )
    cycle.add_argument(
        "--promote",
        action="store_true",
        help=(
            "Permit a proven redesign to approach "
            "the promotion preflight boundary."
        ),
    )
    cycle.add_argument(
        "--approve-promotion",
        action="store_true",
        help=(
            "Explicitly approve promotion after all "
            "promotion gates succeed."
        ),
    )
    cycle.add_argument(
        "--json",
        action="store_true",
    )

    return parser


def command_version(args):
    emit(
        {
            "name": "kiln",
            "version": VERSION,
        },
        args.json,
    )
    return 0


def command_inspect(args):
    result = inspect_target(
        args.target
    )

    emit(
        result,
        args.json,
    )

    return 0


def command_capabilities(args):
    emit(
        host_capabilities(),
        args.json,
    )

    return 0


def command_coal(args):
    identity = inspect_target(args.target)
    root = Path(identity.repository_root).resolve()
    contract = resolve_coal_contract(
        args.adapter,
        root,
    )

    if contract is None:
        emit(
            {
                "adapter": args.adapter,
                "disposition": "COAL_CONTRACT_MISSING",
                "target_id": identity.target_id,
            },
            args.json,
        )
        return 11

    emit(
        {
            "adapter": args.adapter,
            "contract": serialize(contract),
            "disposition": "COAL_CONTRACT_ACCEPTED",
            "target_id": identity.target_id,
        },
        args.json,
    )
    return 0


def command_coal_house(args):
    emit(
        {
            "capabilities": coal_capability_matrix(args.evidence_root),
            "disposition": "COAL_HOUSE_CAPABILITY_MATRIX_READY",
        },
        args.json,
    )
    return 0


def command_coal_venvs(args):
    emit(
        {
            "adapters": [
                {
                    "adapter": item.adapter,
                    "directories": item.directories,
                    "environment": dict(item.environment),
                }
                for item in discover_coal_venvs()
            ],
            "disposition": "COAL_VENV_LIBRARY_READY",
        },
        args.json,
    )
    return 0


def command_coal_fixture(args):
    pack = coal_pack(args.adapter)
    root = write_coal_fixture(pack, args.destination)
    emit(
        {
            "adapter": args.adapter,
            "destination": str(root),
            "disposition": "COAL_FIXTURE_GENERATED",
        },
        args.json,
    )
    return 0


def command_coal_qualify(args):
    if not args.destructive:
        emit(
            {
                "adapter": args.adapter,
                "disposition": "DESTRUCTIVE_AUTHORIZATION_REQUIRED",
            },
            args.json,
        )
        return 12

    result = qualify_coal_pack(
        args.adapter,
        args.evidence_root,
        args.production_target,
        args.production_entry,
        args.production_passes,
    )
    emit(result, args.json)
    return 0 if result.fixture_qualified or not result.runtime_available else 1


def command_reconstruct(args):
    identity = inspect_target(
        args.target
    )

    if identity.local_or_remote != "LOCAL":
        emit(
            {
                "disposition": "REMOTE_RECONSTRUCTION_NOT_YET_WIRED",
                "target_id": identity.target_id,
            },
            args.json,
        )
        return 3

    root = Path(
        identity.repository_root
    )

    if args.adapter == "python":
        result = reconstruct_python(
            root,
            args.entry,
        )

    if args.adapter == "javascript":
        result = reconstruct_javascript(
            root,
            args.entry,
        )

    if args.adapter == "powershell":
        result = reconstruct_powershell(
            root,
            args.entry,
        )

    if args.adapter == "wsl2":
        result = reconstruct_wsl2(
            root,
            args.entry,
        )

    if args.adapter == "api-service":
        result = reconstruct_api_service(
            root,
            args.entry,
        )

    if args.adapter not in {
        "python",
        "javascript",
        "powershell",
        "wsl2",
        "api-service",
    }:
        baseline = run_target_baseline(
            args.target,
            args.adapter,
            args.entry,
        )
        result = ReconstructionResult(
            adapter=args.adapter,
            source_root=str(root.resolve()),
            specimen_root="",
            materialized=(
                baseline.disposition != "BASELINE_BLOCKED"
            ),
            baseline_passed=baseline.baseline_passed,
            exit_code=baseline.exit_code,
            teardown_proven=baseline.specimen_removed,
            original_untouched=baseline.original_head_preserved,
            disposition=(
                "RECONSTRUCTION_PROVEN"
                if (
                    baseline.baseline_passed
                    and baseline.specimen_removed
                    and baseline.original_head_preserved
                )
                else "RECONSTRUCTED_BASELINE_FAILED"
            ),
        )

    decision = adjudicate_reconstruction(
        result
    )

    emit(
        {
            "target": serialize(identity),
            "reconstruction": serialize(result),
            "adjudication": serialize(decision),
        },
        args.json,
    )

    if not decision.destructive_testing_authorized:
        return 4

    return 0


def command_cycle(args):
    if args.max_passes < 1:
        raise RuntimeError(
            "cycle max passes must be positive"
        )

    if args.workers < 1:
        raise RuntimeError(
            "cycle workers must be positive"
        )

    if args.approve_promotion and not args.promote:
        raise RuntimeError(
            "promotion approval requires --promote"
        )

    identity = inspect_target(
        args.target
    )

    if not args.destructive:
        emit(
            {
                "target": serialize(identity),
                "disposition": "DESTRUCTIVE_AUTHORIZATION_REQUIRED",
                "destructive_authorized": False,
                "max_passes": args.max_passes,
                "workers": args.workers,
                "until": args.until,
            },
            args.json,
        )
        return 5

    session_root = args.session_root

    if session_root is None:
        session_root = (
            Path.home()
            / ".kiln"
            / "sessions"
        )

    raw = run_cycle(
        args.target,
        args.adapter,
        args.entry,
        args.max_passes,
        args.until,
        session_root,
        workers=args.workers,
    )

    result = finalize_cycle_result(
        raw,
        args.target,
    )

    emit(
        result,
        args.json,
    )

    if not result.original_head_preserved:
        return 7

    if not result.baseline_passed:
        return 8

    if result.execution_failures:
        return 12

    return 0



def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "frankentest-approve":
        if not args.approve:
            emit({"disposition": "EXPLICIT_APPROVAL_REQUIRED"}, args.json)
            return 5
        try:
            result = approve_frankentest(args.target, args.candidate, args.evidence,
                                        args.expected_sha256, args.authority_ref,
                                        args.registry, args.timeout)
        except (RuntimeError, OSError, ValueError) as error:
            emit({"disposition": "HELD", "reason": str(error)}, args.json)
            return 12
        emit(result, args.json)
        return 0

    if args.command == "frankentest":
        if not args.destructive:
            emit({"disposition": "DESTRUCTIVE_AUTHORIZATION_REQUIRED"}, args.json)
            return 5
        try:
            result = frankentest(args.target, args.evidence, args.output, args.adapter,
                                 args.max_candidates, args.timeout)
        except (RuntimeError, OSError, ValueError) as error:
            emit({"disposition": "HELD", "reason": str(error)}, args.json)
            return 12
        emit(result, args.json)
        return 0 if result['disposition'] == 'QUALIFIED_APPROVAL_CANDIDATES' else 12

    if args.command == "version":
        return command_version(args)

    if args.command == "inspect":
        return command_inspect(args)

    if args.command == "capabilities":
        return command_capabilities(args)

    if args.command == "coal":
        return command_coal(args)

    if args.command == "coal-house":
        return command_coal_house(args)

    if args.command == "coal-venvs":
        return command_coal_venvs(args)

    if args.command == "coal-fixture":
        return command_coal_fixture(args)

    if args.command == "coal-qualify":
        return command_coal_qualify(args)

    if args.command == "reconstruct":
        return command_reconstruct(args)

    if args.command == "baseline":
        result = run_target_baseline(
            args.target,
            args.adapter,
            args.entry,
        )
        emit(result, args.json)
        return 0 if result.baseline_passed else 8

    if args.command == "preflight":
        result = preflight_target(
            args.target,
            args.adapter,
            args.entry,
        )
        emit(result, args.json)
        return 0 if result.disposition == "READY_FOR_KILN_PROOF" else 9

    if args.command == "candidates":
        result = inspect_candidates(
            args.target,
            args.adapter,
        )
        emit(result, args.json)
        return 0

    if args.command == "surfaces":
        result = inspect_surfaces(
            args.target,
            args.adapter,
        )
        emit(result, args.json)
        return 0

    if args.command == "prove":
        result = prove_target(
            args.target,
            args.adapter,
            args.entry,
        )
        emit(result, args.json)
        return 0 if result.disposition == "TARGET_PROVEN_FOR_BOUNDED_CYCLE" else 10

    if args.command == "pressure":
        if not args.destructive:
            emit(
                {
                    "disposition": "DESTRUCTIVE_AUTHORIZATION_REQUIRED",
                    "target": args.target,
                },
                args.json,
            )
            return 5

        result = pressure_cycle(
            args.target,
            args.adapter,
            args.entry,
            args.max_passes,
            args.session_root,
            args.workers,
        )
        emit(result, args.json)
        if not result.original_head_preserved:
            return 7
        if not result.baseline_passed:
            return 8
        return 12 if result.execution_failures else 0

    if args.command == "inject":
        if not args.destructive:
            emit(
                {
                    "disposition": "DESTRUCTIVE_AUTHORIZATION_REQUIRED",
                    "target": args.target,
                },
                args.json,
            )
            return 5

        result = targeted_inject(
            args.target,
            args.adapter,
            args.entry,
            args.candidate_id,
            args.session_root,
        )
        emit(result, args.json)
        if not result.original_head_preserved:
            return 7
        if not result.baseline_passed:
            return 8
        return 12 if result.execution_failures else 0

    if args.command == "evidence":
        emit(
            evidence_summary(
                args.target,
                args.session_root,
            ),
            args.json,
        )
        return 0

    if args.command == "graph":
        emit(
            materialize_graph(
                args.target,
                args.session_root,
            ),
            args.json,
        )
        return 0

    if args.command == "fragments":
        emit(
            fragment_summary(
                args.target,
                args.source,
            ),
            args.json,
        )
        return 0

    if args.command == "contracts":
        emit(
            contract_summary(
                args.target,
                args.session_root,
                args.capability,
                args.attack_surface,
                args.environment,
                args.dependency,
            ),
            args.json,
        )
        return 0

    if args.command in {
        "redesign",
        "adjudicate",
    }:
        emit(
            redesign_summary(
                args.artifact,
                args.staging_root,
                args.provenance,
                args.baseline_preserved,
                args.fracture_mitigated,
            ),
            args.json,
        )
        return 0

    if args.command == "promote":
        result = promote_artifact(
            args.target,
            args.artifact,
            args.staging_root,
            args.provenance,
            args.destination,
            args.expected_head,
            args.remote,
            args.branch,
            args.message,
            args.approve,
            args.baseline_preserved,
            args.fracture_mitigated,
        )
        emit(result, args.json)
        return 0 if result.remote_verified else 11

    if args.command == "cycle":
        return command_cycle(args)

    raise RuntimeError(f"unhandled CLI command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
