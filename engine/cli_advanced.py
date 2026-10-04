from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Tuple
import csv
import json

from engine.behavioral_fragments import (
    BehavioralFragment,
    discover_python_test_fragments,
)
from engine.compatibility_graph import (
    CompatibilityEdge,
    make_edge,
    write_graph,
)
from engine.constructive_redesign import (
    adjudicate_redesign,
    execute_promotion,
    preflight_promotion,
    scan_staged_artifact,
    stage_artifact,
)
from engine.cycle_orchestrator import (
    CycleResult,
    finalize_cycle_result,
    run_cycle,
)
from engine.github_adjudication import (
    publish_github_adjudication,
)
from engine.synthetic_contracts import (
    CapabilityGap,
    SyntheticContract,
    draft_contract_from_gap,
    identify_capability_gap,
)
from engine.target_intake import inspect_target


@dataclass(frozen=True)
class EvidenceSummary:
    target_id: str
    cycle_count: int
    trial_count: int
    fracture_count: int
    survivor_count: int
    result_paths: Tuple[str, ...]
    disposition: str


@dataclass(frozen=True)
class GraphSummary:
    target_id: str
    edge_count: int
    graph_path: str
    disposition: str


@dataclass(frozen=True)
class FragmentSummary:
    target_id: str
    source_path: str
    fragment_count: int
    fragments: Tuple[BehavioralFragment, ...]
    disposition: str


@dataclass(frozen=True)
class ContractSummary:
    target_id: str
    gap: CapabilityGap
    contract: SyntheticContract
    disposition: str


@dataclass(frozen=True)
class RedesignSummary:
    candidate_id: str
    staged_path: str
    contamination_clean: bool
    promotion_eligible: bool
    disposition: str


@dataclass(frozen=True)
class PromotionSummary:
    candidate_id: str
    promotion_authorized: bool
    branch_name: str
    pushed: bool
    remote_verified: bool
    human_adjudication_required: bool
    draft_pr_url: str
    draft_pr_created: bool
    cycle_reignited: bool
    commit_hash: str
    remote_commit: str
    disposition: str


def session_root_path(
    session_root: Path | None,
) -> Path:
    if session_root is not None:
        return Path(
            session_root
        ).resolve()

    return (
        Path.home()
        / ".kiln"
        / "sessions"
    ).resolve()


def cycle_result_records(
    target: str,
    session_root: Path | None,
):
    identity = inspect_target(
        target
    )

    root = session_root_path(
        session_root
    )

    records = []

    if not root.exists():
        return identity, tuple()

    for path in sorted(
        root.rglob(
            "cycle-result.json"
        )
    ):
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            continue

        if payload.get(
            "target_id"
        ) != identity.target_id:
            continue

        records.append(
            (
                path,
                payload,
            )
        )

    return identity, tuple(
        records
    )


def evidence_summary(
    target: str,
    session_root: Path | None,
) -> EvidenceSummary:
    identity, records = cycle_result_records(
        target,
        session_root,
    )

    trial_count = sum(
        len(
            payload.get(
                "trials",
                [],
            )
        )
        for _, payload in records
    )

    fractures = sum(
        int(
            payload.get(
                "fractures_observed",
                0,
            )
        )
        for _, payload in records
    )

    survivors = sum(
        int(
            payload.get(
                "survivors_observed",
                0,
            )
        )
        for _, payload in records
    )

    return EvidenceSummary(
        target_id=identity.target_id,
        cycle_count=len(
            records
        ),
        trial_count=trial_count,
        fracture_count=fractures,
        survivor_count=survivors,
        result_paths=tuple(
            str(path)
            for path, _ in records
        ),
        disposition="EVIDENCE_READY",
    )


def graph_edges_from_evidence(
    target: str,
    session_root: Path | None,
) -> Tuple[CompatibilityEdge, ...]:
    identity, records = cycle_result_records(
        target,
        session_root,
    )

    edges = []

    for path, payload in records:
        for trial in payload.get(
            "trials",
            [],
        ):
            relationship = (
                "MUTATION_SURVIVED"
            )

            if trial.get(
                "fracture_observed"
            ):
                relationship = (
                    "FRACTURE_OBSERVED"
                )

            edges.append(
                make_edge(
                    source_id=trial[
                        "mutation_id"
                    ],
                    target_id=trial[
                        "relative_path"
                    ],
                    relationship=relationship,
                    proof_state="OBSERVED",
                    evidence_refs=(
                        str(path),
                    ),
                    language=payload.get(
                        "adapter",
                        "",
                    ),
                    attack_surface="mutation",
                    failure_semantics=trial.get(
                        "disposition",
                        "",
                    ),
                )
            )

    return tuple(
        sorted(
            edges,
            key=lambda item: item.edge_id,
        )
    )


def materialize_graph(
    target: str,
    session_root: Path | None,
) -> GraphSummary:
    identity = inspect_target(
        target
    )

    root = session_root_path(
        session_root
    )

    edges = graph_edges_from_evidence(
        target,
        session_root,
    )

    output = (
        root
        / "summaries"
        / identity.target_id
        / "compatibility-graph.csv"
    )

    write_graph(
        output,
        edges,
    )

    return GraphSummary(
        target_id=identity.target_id,
        edge_count=len(
            edges
        ),
        graph_path=str(
            output
        ),
        disposition="GRAPH_MATERIALIZED",
    )


def fragment_summary(
    target: str,
    source: str,
) -> FragmentSummary:
    identity = inspect_target(
        target
    )

    root = Path(
        identity.repository_root
    ).resolve()

    path = (
        root
        / source
    ).resolve()

    try:
        path.relative_to(
            root
        )
    except ValueError:
        raise RuntimeError(
            "fragment source escaped target"
        )

    fragments = discover_python_test_fragments(
        path,
        "cli-fragments:"
        + identity.target_id,
    )

    return FragmentSummary(
        target_id=identity.target_id,
        source_path=str(
            path
        ),
        fragment_count=len(
            fragments
        ),
        fragments=fragments,
        disposition="FRAGMENTS_READY",
    )


def contract_summary(
    target: str,
    session_root: Path | None,
    capability: str,
    attack_surface: str,
    environment: str,
    dependency: str,
) -> ContractSummary:
    identity = inspect_target(
        target
    )

    edges = graph_edges_from_evidence(
        target,
        session_root,
    )

    gap = identify_capability_gap(
        required_capability=capability,
        attack_surface=attack_surface,
        environment_contract=environment,
        dependency_contract=dependency,
        edges=edges,
    )

    contract = draft_contract_from_gap(
        gap,
        edges,
        (
            "SOURCE_PRESERVED",
            "BASELINE_PROVEN",
        ),
        (
            "FRACTURE_OBSERVED",
        ),
    )

    return ContractSummary(
        target_id=identity.target_id,
        gap=gap,
        contract=contract,
        disposition="SYNTHETIC_CONTRACT_READY",
    )


def targeted_inject(
    target: str,
    adapter: str,
    entry: str,
    candidate_id: str,
    session_root: Path | None,
) -> CycleResult:
    root = session_root_path(
        session_root
    )

    raw = run_cycle(
        target,
        adapter,
        entry,
        1,
        "adjudication",
        root,
        candidate_id=candidate_id,
    )

    return finalize_cycle_result(
        raw,
        target,
    )


def pressure_cycle(
    target: str,
    adapter: str,
    entry: str,
    max_passes: int,
    session_root: Path | None,
    workers: int = 1,
) -> CycleResult:
    root = session_root_path(
        session_root
    )

    raw = run_cycle(
        target,
        adapter,
        entry,
        max_passes,
        "stable",
        root,
        workers=workers,
    )

    return finalize_cycle_result(
        raw,
        target,
    )


def redesign_summary(
    artifact_path: str,
    staging_root: Path,
    provenance_ref: str,
    baseline_preserved: bool,
    fracture_mitigated: bool,
) -> RedesignSummary:
    artifact = stage_artifact(
        Path(
            artifact_path
        ),
        Path(
            staging_root
        ),
        provenance_ref,
    )

    contamination = scan_staged_artifact(
        artifact
    )

    adjudication = adjudicate_redesign(
        artifact,
        baseline_preserved,
        fracture_mitigated,
    )

    return RedesignSummary(
        candidate_id=artifact.candidate_id,
        staged_path=artifact.staged_path,
        contamination_clean=contamination.clean,
        promotion_eligible=adjudication.promotion_eligible,
        disposition=adjudication.disposition,
    )


def promote_artifact(
    target: str,
    artifact_path: str,
    staging_root: Path,
    provenance_ref: str,
    destination_path: str,
    expected_head: str,
    remote_name: str,
    branch_name: str,
    commit_message: str,
    approved: bool,
    baseline_preserved: bool,
    fracture_mitigated: bool,
    base_branch: str,
    repository: str,
) -> PromotionSummary:
    identity = inspect_target(
        target
    )

    if not identity.git_repository:
        raise RuntimeError(
            "promotion requires Git target"
        )

    target_repo = Path(
        identity.repository_root
    ).resolve()

    artifact = stage_artifact(
        Path(
            artifact_path
        ),
        Path(
            staging_root
        ),
        provenance_ref,
    )

    contamination = scan_staged_artifact(
        artifact
    )

    adjudication = adjudicate_redesign(
        artifact,
        baseline_preserved,
        fracture_mitigated,
    )

    preflight = preflight_promotion(
        artifact,
        adjudication,
        contamination,
        target_repo,
        destination_path,
        expected_head,
        approved,
        branch_name,
    )

    if not preflight.promotion_authorized:
        return PromotionSummary(
            candidate_id=artifact.candidate_id,
            promotion_authorized=False,
            branch_name=branch_name,
            pushed=False,
            remote_verified=False,
            human_adjudication_required=True,
            draft_pr_url="",
            draft_pr_created=False,
            cycle_reignited=False,
            commit_hash="",
            remote_commit="",
            disposition=preflight.disposition,
        )

    result = execute_promotion(
        artifact,
        preflight,
        target_repo,
        remote_name,
        branch_name,
        commit_message,
    )

    publication = None

    if result.remote_verified:
        publication = publish_github_adjudication(
            target_repo=target_repo,
            remote_name=remote_name,
            branch_name=result.branch_name,
            base_branch=base_branch,
            commit_hash=result.commit_hash,
            title=commit_message,
            body=(
                "Kiln staged a proven improvement for human "
                "adjudication.\n\n"
                f"Candidate: `{result.candidate_id}`\n\n"
                f"Provenance: `{provenance_ref}`\n\n"
                "This draft cannot be merged until a human marks "
                "it ready and adjudicates the proposed source mutation."
            ),
            repository=repository,
        )

    disposition = result.disposition

    if publication is not None:
        disposition = publication.disposition

    return PromotionSummary(
        candidate_id=result.candidate_id,
        promotion_authorized=True,
        branch_name=result.branch_name,
        pushed=result.pushed,
        remote_verified=result.remote_verified,
        human_adjudication_required=(
            result.human_adjudication_required
        ),
        draft_pr_url=(
            publication.draft_pr_url
            if publication is not None
            else ""
        ),
        draft_pr_created=(
            publication.draft_pr_created
            if publication is not None
            else False
        ),
        cycle_reignited=(
            publication.cycle_reignited
            if publication is not None
            else False
        ),
        commit_hash=result.commit_hash,
        remote_commit=result.remote_commit,
        disposition=disposition,
    )
