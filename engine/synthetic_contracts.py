from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv

from engine.compatibility_graph import CompatibilityEdge


VALID_CONTRACT_STATES = {
    "PROPOSED",
    "PARTIALLY_SUPPORTED",
    "EVIDENCE_SUFFICIENT_FOR_SYNTHESIS",
    "BLOCKED",
}


@dataclass(frozen=True)
class SyntheticContract:
    contract_id: str
    purpose: str
    required_behavior: str
    required_failure_state: str
    environment_contract: str
    dependency_contract: str
    baseline_invariants: Tuple[str, ...]
    fracture_invariants: Tuple[str, ...]
    source_edge_ids: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    proof_state: str
    synthesis_authorized: bool
    execution_authorized: bool


def contract_identity(
    purpose: str,
    required_behavior: str,
    required_failure_state: str,
    environment_contract: str,
    dependency_contract: str,
    baseline_invariants: Tuple[str, ...],
    fracture_invariants: Tuple[str, ...],
    source_edge_ids: Tuple[str, ...],
) -> str:
    material = "\0".join((
        purpose,
        required_behavior,
        required_failure_state,
        environment_contract,
        dependency_contract,
        ";".join(sorted(set(baseline_invariants))),
        ";".join(sorted(set(fracture_invariants))),
        ";".join(sorted(set(source_edge_ids))),
    ))

    return (
        "KILN-SYNTH-CONTRACT-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def draft_contract(
    purpose: str,
    required_behavior: str,
    required_failure_state: str,
    environment_contract: str,
    dependency_contract: str,
    baseline_invariants: Tuple[str, ...],
    fracture_invariants: Tuple[str, ...],
    edges: Tuple[CompatibilityEdge, ...],
) -> SyntheticContract:
    if not purpose.strip():
        raise RuntimeError(
            "synthetic contract purpose is required"
        )

    if not required_behavior.strip():
        raise RuntimeError(
            "synthetic contract behavior is required"
        )

    source_edges = tuple(
        sorted(
            set(
                edge.edge_id
                for edge in edges
            )
        )
    )

    evidence = tuple(
        sorted(
            set(
                ref
                for edge in edges
                for ref in edge.evidence_refs
            )
        )
    )

    proven_count = sum(
        edge.proof_state == "PROVEN"
        for edge in edges
    )

    observed_count = sum(
        edge.proof_state == "OBSERVED"
        for edge in edges
    )

    rejected_count = sum(
        edge.proof_state == "REJECTED"
        for edge in edges
    )

    if rejected_count:
        proof_state = "BLOCKED"

    elif not edges:
        proof_state = "PROPOSED"

    elif proven_count == len(edges):
        proof_state = "EVIDENCE_SUFFICIENT_FOR_SYNTHESIS"

    elif proven_count or observed_count:
        proof_state = "PARTIALLY_SUPPORTED"

    else:
        proof_state = "PROPOSED"

    contract_id = contract_identity(
        purpose,
        required_behavior,
        required_failure_state,
        environment_contract,
        dependency_contract,
        baseline_invariants,
        fracture_invariants,
        source_edges,
    )

    return SyntheticContract(
        contract_id=contract_id,
        purpose=purpose,
        required_behavior=required_behavior,
        required_failure_state=required_failure_state,
        environment_contract=environment_contract,
        dependency_contract=dependency_contract,
        baseline_invariants=tuple(
            sorted(set(baseline_invariants))
        ),
        fracture_invariants=tuple(
            sorted(set(fracture_invariants))
        ),
        source_edge_ids=source_edges,
        evidence_refs=evidence,
        proof_state=proof_state,
        synthesis_authorized=False,
        execution_authorized=False,
    )


def write_contracts(
    path: Path,
    contracts: Tuple[SyntheticContract, ...],
):
    fields = [
        "contract_id",
        "purpose",
        "required_behavior",
        "required_failure_state",
        "environment_contract",
        "dependency_contract",
        "baseline_invariants",
        "fracture_invariants",
        "source_edge_ids",
        "evidence_refs",
        "proof_state",
        "synthesis_authorized",
        "execution_authorized",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
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

        for contract in sorted(
            contracts,
            key=lambda item: item.contract_id,
        ):
            writer.writerow({
                "contract_id": contract.contract_id,
                "purpose": contract.purpose,
                "required_behavior": contract.required_behavior,
                "required_failure_state": contract.required_failure_state,
                "environment_contract": contract.environment_contract,
                "dependency_contract": contract.dependency_contract,
                "baseline_invariants": ";".join(contract.baseline_invariants),
                "fracture_invariants": ";".join(contract.fracture_invariants),
                "source_edge_ids": ";".join(contract.source_edge_ids),
                "evidence_refs": ";".join(contract.evidence_refs),
                "proof_state": contract.proof_state,
                "synthesis_authorized": str(contract.synthesis_authorized).lower(),
                "execution_authorized": str(contract.execution_authorized).lower(),
            })


@dataclass(frozen=True)
class CapabilityGap:
    gap_id: str
    required_capability: str
    attack_surface: str
    environment_contract: str
    dependency_contract: str
    satisfied: bool
    supporting_edge_ids: Tuple[str, ...]
    missing_dimensions: Tuple[str, ...]
    disposition: str


def gap_identity(
    required_capability: str,
    attack_surface: str,
    environment_contract: str,
    dependency_contract: str,
) -> str:
    material = "\0".join((
        required_capability,
        attack_surface,
        environment_contract,
        dependency_contract,
    ))

    return (
        "KILN-GAP-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def identify_capability_gap(
    required_capability: str,
    attack_surface: str,
    environment_contract: str,
    dependency_contract: str,
    edges: Tuple[CompatibilityEdge, ...],
) -> CapabilityGap:
    if not required_capability.strip():
        raise RuntimeError(
            "required capability is missing"
        )

    relevant = tuple(
        edge
        for edge in edges
        if (
            not attack_surface
            or edge.attack_surface == attack_surface
        )
    )

    proven = tuple(
        edge
        for edge in relevant
        if edge.proof_state == "PROVEN"
    )

    supporting = tuple(
        sorted(
            edge.edge_id
            for edge in relevant
            if edge.proof_state in {
                "PROVEN",
                "OBSERVED",
                "INFERRED",
            }
        )
    )

    missing = []

    if not proven:
        missing.append(
            "PROVEN_BEHAVIOR"
        )

    if environment_contract:
        environment_match = any(
            edge.environment == environment_contract
            for edge in proven
        )

        if not environment_match:
            missing.append(
                "ENVIRONMENT_COMPATIBILITY"
            )

    if dependency_contract:
        dependency_match = any(
            edge.dependency_shape == dependency_contract
            for edge in proven
        )

        if not dependency_match:
            missing.append(
                "DEPENDENCY_COMPATIBILITY"
            )

    satisfied = len(missing) == 0

    disposition = "CAPABILITY_SATISFIED"

    if not satisfied and supporting:
        disposition = "SYNTHETIC_CONTRACT_CANDIDATE"

    if not satisfied and not supporting:
        disposition = "CAPABILITY_GAP_UNSUPPORTED"

    return CapabilityGap(
        gap_id=gap_identity(
            required_capability,
            attack_surface,
            environment_contract,
            dependency_contract,
        ),
        required_capability=required_capability,
        attack_surface=attack_surface,
        environment_contract=environment_contract,
        dependency_contract=dependency_contract,
        satisfied=satisfied,
        supporting_edge_ids=supporting,
        missing_dimensions=tuple(
            sorted(set(missing))
        ),
        disposition=disposition,
    )


def draft_contract_from_gap(
    gap: CapabilityGap,
    edges: Tuple[CompatibilityEdge, ...],
    baseline_invariants: Tuple[str, ...],
    fracture_invariants: Tuple[str, ...],
) -> SyntheticContract:
    if gap.satisfied:
        raise RuntimeError(
            "satisfied capability does not require synthetic contract"
        )

    supporting = tuple(
        edge
        for edge in edges
        if edge.edge_id in gap.supporting_edge_ids
    )

    return draft_contract(
        purpose=(
            "close capability gap: "
            + gap.required_capability
        ),
        required_behavior=gap.required_capability,
        required_failure_state=gap.attack_surface,
        environment_contract=gap.environment_contract,
        dependency_contract=gap.dependency_contract,
        baseline_invariants=baseline_invariants,
        fracture_invariants=fracture_invariants,
        edges=supporting,
    )

def write_capability_gaps(
    path: Path,
    gaps: Tuple[CapabilityGap, ...],
):
    fields = [
        "gap_id",
        "required_capability",
        "attack_surface",
        "environment_contract",
        "dependency_contract",
        "satisfied",
        "supporting_edge_ids",
        "missing_dimensions",
        "disposition",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ordered = sorted(
        gaps,
        key=lambda gap: gap.gap_id,
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

        for gap in ordered:
            writer.writerow({
                "gap_id": gap.gap_id,
                "required_capability": gap.required_capability,
                "attack_surface": gap.attack_surface,
                "environment_contract": gap.environment_contract,
                "dependency_contract": gap.dependency_contract,
                "satisfied": str(gap.satisfied).lower(),
                "supporting_edge_ids": ";".join(
                    gap.supporting_edge_ids
                ),
                "missing_dimensions": ";".join(
                    gap.missing_dimensions
                ),
                "disposition": gap.disposition,
            })