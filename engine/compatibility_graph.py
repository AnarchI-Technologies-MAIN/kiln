from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv


VALID_PROOF_STATES = {
    "OBSERVED",
    "PROVEN",
    "INFERRED",
    "CANDIDATE",
    "REJECTED",
}


@dataclass(frozen=True)
class CompatibilityEdge:
    edge_id: str
    source_id: str
    target_id: str
    relationship: str
    proof_state: str
    language: str
    runtime: str
    environment: str
    dependency_shape: str
    test_shape: str
    attack_surface: str
    failure_semantics: str
    functional_continuity: str
    evidence_refs: Tuple[str, ...]


def edge_identity(
    source_id: str,
    target_id: str,
    relationship: str,
    proof_state: str,
    evidence_refs: Tuple[str, ...],
) -> str:
    evidence = "\0".join(
        sorted(set(evidence_refs))
    )

    material = (
        source_id
        + "\0"
        + target_id
        + "\0"
        + relationship
        + "\0"
        + proof_state
        + "\0"
        + evidence
    )

    return (
        "KILN-EDGE-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def make_edge(
    source_id: str,
    target_id: str,
    relationship: str,
    proof_state: str,
    evidence_refs: Tuple[str, ...],
    language: str = "",
    runtime: str = "",
    environment: str = "",
    dependency_shape: str = "",
    test_shape: str = "",
    attack_surface: str = "",
    failure_semantics: str = "",
    functional_continuity: str = "",
) -> CompatibilityEdge:
    if not source_id.strip():
        raise RuntimeError(
            "compatibility source is required"
        )

    if not target_id.strip():
        raise RuntimeError(
            "compatibility target is required"
        )

    if not relationship.strip():
        raise RuntimeError(
            "compatibility relationship is required"
        )

    if proof_state not in VALID_PROOF_STATES:
        raise RuntimeError(
            "unsupported compatibility proof state"
        )

    refs = tuple(
        sorted(
            set(
                ref.strip()
                for ref in evidence_refs
                if ref.strip()
            )
        )
    )

    if proof_state in {
        "OBSERVED",
        "PROVEN",
        "REJECTED",
    } and not refs:
        raise RuntimeError(
            "evidence-backed proof state requires evidence"
        )

    return CompatibilityEdge(
        edge_id=edge_identity(
            source_id,
            target_id,
            relationship,
            proof_state,
            refs,
        ),
        source_id=source_id,
        target_id=target_id,
        relationship=relationship,
        proof_state=proof_state,
        language=language,
        runtime=runtime,
        environment=environment,
        dependency_shape=dependency_shape,
        test_shape=test_shape,
        attack_surface=attack_surface,
        failure_semantics=failure_semantics,
        functional_continuity=functional_continuity,
        evidence_refs=refs,
    )


def write_graph(
    path: Path,
    edges: Tuple[CompatibilityEdge, ...],
):
    fields = [
        "edge_id",
        "source_id",
        "target_id",
        "relationship",
        "proof_state",
        "language",
        "runtime",
        "environment",
        "dependency_shape",
        "test_shape",
        "attack_surface",
        "failure_semantics",
        "functional_continuity",
        "evidence_refs",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ordered = sorted(
        edges,
        key=lambda edge: edge.edge_id,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for edge in ordered:
            writer.writerow({
                "edge_id": edge.edge_id,
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relationship": edge.relationship,
                "proof_state": edge.proof_state,
                "language": edge.language,
                "runtime": edge.runtime,
                "environment": edge.environment,
                "dependency_shape": edge.dependency_shape,
                "test_shape": edge.test_shape,
                "attack_surface": edge.attack_surface,
                "failure_semantics": edge.failure_semantics,
                "functional_continuity": edge.functional_continuity,
                "evidence_refs": ";".join(
                    edge.evidence_refs
                ),
            })


def edges_from_redesign_route(
    candidate_id: str,
    parent_id: str,
    route: str,
    reasons: Tuple[str, ...],
    evidence_ref: str,
) -> Tuple[CompatibilityEdge, ...]:
    if not evidence_ref.strip():
        raise RuntimeError(
            "redesign route evidence is required"
        )

    relationship_by_route = {
        "MUTATE_AGAIN": "FRACTURE_SURVIVED_MUTATION",
        "RETURN_TO_FIRE": "ADDITIONAL_PRESSURE_REQUIRED",
        "SOFT_ROLLBACK": "SOFT_ROLLBACK_CAUSED",
        "HARD_ROLLBACK": "HARD_ROLLBACK_CAUSED",
        "STAGE_FOR_ADJUDICATION": "ADJUDICATION_REACHED",
    }

    if route not in relationship_by_route:
        raise RuntimeError(
            "unsupported redesign route"
        )

    failure_semantics = ";".join(
        sorted(set(reasons))
    )

    edge = make_edge(
        source_id=parent_id,
        target_id=candidate_id,
        relationship=relationship_by_route[route],
        proof_state="OBSERVED",
        evidence_refs=(evidence_ref,),
        failure_semantics=failure_semantics,
    )

    return (edge,)


def edge_from_verified_promotion(
    candidate_id: str,
    commit_hash: str,
    evidence_ref: str,
) -> CompatibilityEdge:
    if not commit_hash.strip():
        raise RuntimeError(
            "verified promotion commit is required"
        )

    if not evidence_ref.strip():
        raise RuntimeError(
            "verified promotion evidence is required"
        )

    return make_edge(
        source_id=candidate_id,
        target_id=commit_hash,
        relationship="PROMOTED_AS",
        proof_state="PROVEN",
        evidence_refs=(evidence_ref,),
        functional_continuity="PROMOTION_VERIFIED",
    )

@dataclass(frozen=True)
class CompatibilityQuery:
    node_id: str
    language: str = ""
    runtime: str = ""
    environment: str = ""
    dependency_shape: str = ""
    test_shape: str = ""
    attack_surface: str = ""
    failure_semantics: str = ""
    functional_continuity: str = ""
    proof_states: Tuple[str, ...] = ()


def query_compatibility(
    edges: Tuple[CompatibilityEdge, ...],
    query: CompatibilityQuery,
) -> Tuple[CompatibilityEdge, ...]:
    if not query.node_id.strip():
        raise RuntimeError(
            "compatibility query node is required"
        )

    requested_states = tuple(
        sorted(set(query.proof_states))
    )

    for state in requested_states:
        if state not in VALID_PROOF_STATES:
            raise RuntimeError(
                "unsupported compatibility query proof state"
            )

    dimensions = (
        ("language", query.language),
        ("runtime", query.runtime),
        ("environment", query.environment),
        ("dependency_shape", query.dependency_shape),
        ("test_shape", query.test_shape),
        ("attack_surface", query.attack_surface),
        ("failure_semantics", query.failure_semantics),
        ("functional_continuity", query.functional_continuity),
    )

    matches = []

    for edge in edges:
        if (
            edge.source_id != query.node_id
            and edge.target_id != query.node_id
        ):
            continue

        if (
            requested_states
            and edge.proof_state not in requested_states
        ):
            continue

        rejected = False

        for field, expected in dimensions:
            if not expected:
                continue

            if getattr(edge, field) != expected:
                rejected = True
                break

        if rejected:
            continue

        matches.append(edge)

    return tuple(
        sorted(
            matches,
            key=lambda edge: edge.edge_id,
        )
    )


def proven_neighbors(
    edges: Tuple[CompatibilityEdge, ...],
    node_id: str,
) -> Tuple[str, ...]:
    matches = query_compatibility(
        edges,
        CompatibilityQuery(
            node_id=node_id,
            proof_states=("PROVEN",),
        ),
    )

    neighbors = set()

    for edge in matches:
        if edge.source_id == node_id:
            neighbors.add(edge.target_id)

        if edge.target_id == node_id:
            neighbors.add(edge.source_id)

    return tuple(
        sorted(neighbors)
    )