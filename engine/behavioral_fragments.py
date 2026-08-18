from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import csv


VALID_FRAGMENT_ROLES = {
    "SETUP",
    "FIXTURE",
    "ACTION",
    "INJECTION",
    "ASSERTION",
    "OBSERVATION",
    "CLEANUP",
    "UNKNOWN",
}


@dataclass(frozen=True)
class BehavioralFragment:
    fragment_id: str
    parent_test_id: str
    parent_source_path: str
    parent_source_hash: str
    start_line: int
    end_line: int
    sequence_position: int
    sequence_total: int
    role: str
    source_hash: str
    source_text: str
    provenance_ref: str
    proof_state: str


def hash_text(text: str) -> str:
    return sha256(
        text.encode("utf-8")
    ).hexdigest()


def fragment_identity(
    parent_test_id: str,
    parent_source_hash: str,
    start_line: int,
    end_line: int,
    sequence_position: int,
    role: str,
    source_hash: str,
) -> str:
    material = "\0".join((
        parent_test_id,
        parent_source_hash,
        str(start_line),
        str(end_line),
        str(sequence_position),
        role,
        source_hash,
    ))

    return (
        "KILN-FRAGMENT-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def virtual_fragment(
    parent_test_id: str,
    source_path: Path,
    start_line: int,
    end_line: int,
    sequence_position: int,
    sequence_total: int,
    role: str,
    provenance_ref: str,
) -> BehavioralFragment:
    path = Path(source_path).resolve()

    if not path.exists():
        raise RuntimeError(
            "parent test source is missing"
        )

    if role not in VALID_FRAGMENT_ROLES:
        raise RuntimeError(
            "unsupported fragment role"
        )

    if start_line < 1:
        raise RuntimeError(
            "fragment start line must be positive"
        )

    if end_line < start_line:
        raise RuntimeError(
            "fragment end precedes start"
        )

    if sequence_position < 1:
        raise RuntimeError(
            "fragment sequence position must be positive"
        )

    if sequence_total < sequence_position:
        raise RuntimeError(
            "fragment sequence total is invalid"
        )

    if not provenance_ref.strip():
        raise RuntimeError(
            "fragment provenance is required"
        )

    parent_text = path.read_text(
        encoding="utf-8"
    )

    parent_hash = hash_text(
        parent_text
    )

    lines = parent_text.splitlines(
        keepends=True
    )

    if end_line > len(lines):
        raise RuntimeError(
            "fragment range exceeds parent source"
        )

    source_text = "".join(
        lines[start_line - 1:end_line]
    )

    source_hash = hash_text(
        source_text
    )

    fragment_id = fragment_identity(
        parent_test_id,
        parent_hash,
        start_line,
        end_line,
        sequence_position,
        role,
        source_hash,
    )

    return BehavioralFragment(
        fragment_id=fragment_id,
        parent_test_id=parent_test_id,
        parent_source_path=str(path),
        parent_source_hash=parent_hash,
        start_line=start_line,
        end_line=end_line,
        sequence_position=sequence_position,
        sequence_total=sequence_total,
        role=role,
        source_hash=source_hash,
        source_text=source_text,
        provenance_ref=provenance_ref,
        proof_state="CANDIDATE",
    )


def write_fragments(
    path: Path,
    fragments: Tuple[BehavioralFragment, ...],
):
    fields = [
        "fragment_id",
        "parent_test_id",
        "parent_source_path",
        "parent_source_hash",
        "start_line",
        "end_line",
        "sequence_position",
        "sequence_total",
        "role",
        "source_hash",
        "provenance_ref",
        "proof_state",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ordered = sorted(
        fragments,
        key=lambda item: (
            item.parent_test_id,
            item.sequence_position,
            item.fragment_id,
        ),
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

        for fragment in ordered:
            writer.writerow({
                "fragment_id": fragment.fragment_id,
                "parent_test_id": fragment.parent_test_id,
                "parent_source_path": fragment.parent_source_path,
                "parent_source_hash": fragment.parent_source_hash,
                "start_line": fragment.start_line,
                "end_line": fragment.end_line,
                "sequence_position": fragment.sequence_position,
                "sequence_total": fragment.sequence_total,
                "role": fragment.role,
                "source_hash": fragment.source_hash,
                "provenance_ref": fragment.provenance_ref,
                "proof_state": fragment.proof_state,
            })


def classify_python_statement(node) -> str:
    import ast

    if isinstance(node, ast.Assert):
        return "ASSERTION"

    if isinstance(node, ast.With):
        for item in node.items:
            expression = item.context_expr

            if (
                isinstance(expression, ast.Call)
                and isinstance(expression.func, ast.Attribute)
                and expression.func.attr in {
                    "assertRaises",
                    "assertRaisesRegex",
                    "raises",
                }
            ):
                return "ASSERTION"

        return "UNKNOWN"

    if isinstance(node, ast.Try):
        return "UNKNOWN"

    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return "SETUP"

    if isinstance(node, ast.AugAssign):
        return "ACTION"

    if isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Call):
            return "ACTION"

        return "OBSERVATION"

    if isinstance(node, ast.Return):
        return "OBSERVATION"

    return "UNKNOWN"


def discover_python_test_fragments(
    source_path: Path,
    provenance_ref: str,
) -> Tuple[BehavioralFragment, ...]:
    import ast

    path = Path(source_path).resolve()

    if not path.exists():
        raise RuntimeError(
            "Python test source is missing"
        )

    if not provenance_ref.strip():
        raise RuntimeError(
            "Python fragment provenance is required"
        )

    source = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        source,
        filename=str(path),
    )

    discovered = []

    test_nodes = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name.startswith("test")
    )

    ordered_tests = sorted(
        test_nodes,
        key=lambda node: (
            node.lineno,
            node.name,
        ),
    )

    for test_node in ordered_tests:
        statements = tuple(
            statement
            for statement in test_node.body
            if hasattr(statement, "lineno")
            and hasattr(statement, "end_lineno")
        )

        total = len(statements)

        if not total:
            continue

        parent_test_id = (
            f"{path.as_posix()}::{test_node.name}"
        )

        for position, statement in enumerate(
            statements,
            start=1,
        ):
            role = classify_python_statement(
                statement
            )

            fragment = virtual_fragment(
                parent_test_id=parent_test_id,
                source_path=path,
                start_line=statement.lineno,
                end_line=statement.end_lineno,
                sequence_position=position,
                sequence_total=total,
                role=role,
                provenance_ref=provenance_ref,
            )

            discovered.append(
                fragment
            )

    return tuple(
        discovered
    )

@dataclass(frozen=True)
class FragmentObservation:
    observation_id: str
    fragment_id: str
    execution_id: str
    reached: bool
    passed: bool
    failure_observed: bool
    downstream_failure: bool
    mutation_survived: bool
    rollback_kind: str
    observed_role: str
    evidence_ref: str


@dataclass(frozen=True)
class FragmentHistory:
    fragment_id: str
    execution_count: int
    reached_count: int
    pass_count: int
    failure_count: int
    downstream_failure_count: int
    mutation_survival_count: int
    soft_rollback_count: int
    hard_rollback_count: int
    observed_roles: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]


def observation_identity(
    fragment_id: str,
    execution_id: str,
    reached: bool,
    passed: bool,
    failure_observed: bool,
    downstream_failure: bool,
    mutation_survived: bool,
    rollback_kind: str,
    observed_role: str,
    evidence_ref: str,
) -> str:
    material = "\0".join((
        fragment_id,
        execution_id,
        str(reached),
        str(passed),
        str(failure_observed),
        str(downstream_failure),
        str(mutation_survived),
        rollback_kind,
        observed_role,
        evidence_ref,
    ))

    return (
        "KILN-FRAGMENT-OBS-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def observe_fragment(
    fragment: BehavioralFragment,
    execution_id: str,
    reached: bool,
    passed: bool,
    failure_observed: bool,
    downstream_failure: bool,
    mutation_survived: bool,
    rollback_kind: str,
    observed_role: str,
    evidence_ref: str,
) -> FragmentObservation:
    if not execution_id.strip():
        raise RuntimeError(
            "fragment execution identity is required"
        )

    if not evidence_ref.strip():
        raise RuntimeError(
            "fragment observation evidence is required"
        )

    if observed_role and observed_role not in VALID_FRAGMENT_ROLES:
        raise RuntimeError(
            "unsupported observed fragment role"
        )

    if rollback_kind not in {
        "",
        "SOFT_ROLLBACK",
        "HARD_ROLLBACK",
    }:
        raise RuntimeError(
            "unsupported fragment rollback kind"
        )

    if passed and not reached:
        raise RuntimeError(
            "unreached fragment cannot pass"
        )

    if failure_observed and not reached:
        raise RuntimeError(
            "unreached fragment cannot directly fail"
        )

    observation_id = observation_identity(
        fragment.fragment_id,
        execution_id,
        reached,
        passed,
        failure_observed,
        downstream_failure,
        mutation_survived,
        rollback_kind,
        observed_role,
        evidence_ref,
    )

    return FragmentObservation(
        observation_id=observation_id,
        fragment_id=fragment.fragment_id,
        execution_id=execution_id,
        reached=reached,
        passed=passed,
        failure_observed=failure_observed,
        downstream_failure=downstream_failure,
        mutation_survived=mutation_survived,
        rollback_kind=rollback_kind,
        observed_role=observed_role,
        evidence_ref=evidence_ref,
    )


def summarize_fragment_history(
    fragment_id: str,
    observations: Tuple[FragmentObservation, ...],
) -> FragmentHistory:
    relevant = tuple(
        item
        for item in observations
        if item.fragment_id == fragment_id
    )

    roles = tuple(
        sorted(
            set(
                item.observed_role
                for item in relevant
                if item.observed_role
            )
        )
    )

    evidence = tuple(
        sorted(
            set(
                item.evidence_ref
                for item in relevant
            )
        )
    )

    return FragmentHistory(
        fragment_id=fragment_id,
        execution_count=len(relevant),
        reached_count=sum(
            item.reached
            for item in relevant
        ),
        pass_count=sum(
            item.passed
            for item in relevant
        ),
        failure_count=sum(
            item.failure_observed
            for item in relevant
        ),
        downstream_failure_count=sum(
            item.downstream_failure
            for item in relevant
        ),
        mutation_survival_count=sum(
            item.mutation_survived
            for item in relevant
        ),
        soft_rollback_count=sum(
            item.rollback_kind == "SOFT_ROLLBACK"
            for item in relevant
        ),
        hard_rollback_count=sum(
            item.rollback_kind == "HARD_ROLLBACK"
            for item in relevant
        ),
        observed_roles=roles,
        evidence_refs=evidence,
    )


def write_fragment_history(
    path: Path,
    histories: Tuple[FragmentHistory, ...],
):
    fields = [
        "fragment_id",
        "execution_count",
        "reached_count",
        "pass_count",
        "failure_count",
        "downstream_failure_count",
        "mutation_survival_count",
        "soft_rollback_count",
        "hard_rollback_count",
        "observed_roles",
        "evidence_refs",
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

        for history in sorted(
            histories,
            key=lambda item: item.fragment_id,
        ):
            writer.writerow({
                "fragment_id": history.fragment_id,
                "execution_count": history.execution_count,
                "reached_count": history.reached_count,
                "pass_count": history.pass_count,
                "failure_count": history.failure_count,
                "downstream_failure_count": history.downstream_failure_count,
                "mutation_survival_count": history.mutation_survival_count,
                "soft_rollback_count": history.soft_rollback_count,
                "hard_rollback_count": history.hard_rollback_count,
                "observed_roles": ";".join(history.observed_roles),
                "evidence_refs": ";".join(history.evidence_refs),
            })

@dataclass(frozen=True)
class FragmentEffectiveness:
    fragment_id: str
    execution_count: int
    reach_rate: float
    pass_rate_when_reached: float
    direct_failure_rate_when_reached: float
    downstream_failure_rate: float
    mutation_survival_rate: float
    rollback_rate: float
    disposition: str


def fragment_effectiveness(
    history: FragmentHistory,
) -> FragmentEffectiveness:
    executions = history.execution_count
    reached = history.reached_count

    reach_rate = (
        history.reached_count / executions
        if executions
        else 0.0
    )

    pass_rate = (
        history.pass_count / reached
        if reached
        else 0.0
    )

    direct_failure_rate = (
        history.failure_count / reached
        if reached
        else 0.0
    )

    downstream_failure_rate = (
        history.downstream_failure_count / executions
        if executions
        else 0.0
    )

    mutation_survival_rate = (
        history.mutation_survival_count / executions
        if executions
        else 0.0
    )

    rollback_count = (
        history.soft_rollback_count
        + history.hard_rollback_count
    )

    rollback_rate = (
        rollback_count / executions
        if executions
        else 0.0
    )

    if executions == 0:
        disposition = "NO_RUNTIME_EVIDENCE"

    elif history.failure_count or rollback_count:
        disposition = "BEHAVIORALLY_CONTESTED"

    elif (
        history.reached_count == executions
        and history.pass_count == reached
    ):
        disposition = "CONSISTENTLY_SURVIVED"

    else:
        disposition = "PARTIALLY_OBSERVED"

    return FragmentEffectiveness(
        fragment_id=history.fragment_id,
        execution_count=executions,
        reach_rate=reach_rate,
        pass_rate_when_reached=pass_rate,
        direct_failure_rate_when_reached=direct_failure_rate,
        downstream_failure_rate=downstream_failure_rate,
        mutation_survival_rate=mutation_survival_rate,
        rollback_rate=rollback_rate,
        disposition=disposition,
    )


def rank_fragment_effectiveness(
    histories: Tuple[FragmentHistory, ...],
) -> Tuple[FragmentEffectiveness, ...]:
    records = tuple(
        fragment_effectiveness(history)
        for history in histories
    )

    return tuple(
        sorted(
            records,
            key=lambda item: (
                -item.mutation_survival_rate,
                item.rollback_rate,
                item.direct_failure_rate_when_reached,
                item.downstream_failure_rate,
                -item.pass_rate_when_reached,
                -item.execution_count,
                item.fragment_id,
            ),
        )
    )


def write_fragment_effectiveness(
    path: Path,
    records: Tuple[FragmentEffectiveness, ...],
):
    fields = [
        "fragment_id",
        "execution_count",
        "reach_rate",
        "pass_rate_when_reached",
        "direct_failure_rate_when_reached",
        "downstream_failure_rate",
        "mutation_survival_rate",
        "rollback_rate",
        "disposition",
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

        for item in sorted(
            records,
            key=lambda record: record.fragment_id,
        ):
            writer.writerow({
                "fragment_id": item.fragment_id,
                "execution_count": item.execution_count,
                "reach_rate": f"{item.reach_rate:.6f}",
                "pass_rate_when_reached": f"{item.pass_rate_when_reached:.6f}",
                "direct_failure_rate_when_reached": f"{item.direct_failure_rate_when_reached:.6f}",
                "downstream_failure_rate": f"{item.downstream_failure_rate:.6f}",
                "mutation_survival_rate": f"{item.mutation_survival_rate:.6f}",
                "rollback_rate": f"{item.rollback_rate:.6f}",
                "disposition": item.disposition,
            })