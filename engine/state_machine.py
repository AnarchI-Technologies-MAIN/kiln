from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Tuple


class KilnState(str, Enum):
    DISCOVERED = "DISCOVERED"
    UNADJUDICATED = "UNADJUDICATED"
    PLAUSIBLE = "PLAUSIBLE"
    PROOF_REQUIRED = "PROOF_REQUIRED"
    PROVEN = "PROVEN"
    PRESSURE_AUTHORIZED = "PRESSURE_AUTHORIZED"
    FRACTURED = "FRACTURED"
    ADJUDICATED = "ADJUDICATED"
    REPAIR_TRIAL = "REPAIR_TRIAL"
    CHECKPOINTED = "CHECKPOINTED"
    PROMOTED = "PROMOTED"
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"
    CONTRADICTED = "CONTRADICTED"
    RECONCILED = "RECONCILED"
    SUPERSEDED = "SUPERSEDED"


class InvalidKilnTransition(RuntimeError):
    pass


ALLOWED_TRANSITIONS: Dict[KilnState, FrozenSet[KilnState]] = {
    KilnState.DISCOVERED: frozenset({
        KilnState.UNADJUDICATED,
        KilnState.BLOCKED,
    }),

    KilnState.UNADJUDICATED: frozenset({
        KilnState.PLAUSIBLE,
        KilnState.PROVEN,
        KilnState.BLOCKED,
    }),

    KilnState.PLAUSIBLE: frozenset({
        KilnState.PROOF_REQUIRED,
        KilnState.CONTRADICTED,
        KilnState.BLOCKED,
    }),

    KilnState.PROOF_REQUIRED: frozenset({
        KilnState.PROVEN,
        KilnState.CONTRADICTED,
        KilnState.BLOCKED,
    }),

    KilnState.PROVEN: frozenset({
        KilnState.PRESSURE_AUTHORIZED,
        KilnState.FRACTURED,
        KilnState.EXHAUSTED,
        KilnState.CONTRADICTED,
        KilnState.SUPERSEDED,
    }),

    KilnState.PRESSURE_AUTHORIZED: frozenset({
        KilnState.FRACTURED,
        KilnState.EXHAUSTED,
        KilnState.CONTRADICTED,
        KilnState.BLOCKED,
    }),

    KilnState.FRACTURED: frozenset({
        KilnState.ADJUDICATED,
        KilnState.BLOCKED,
    }),

    KilnState.ADJUDICATED: frozenset({
        KilnState.REPAIR_TRIAL,
        KilnState.PROVEN,
        KilnState.EXHAUSTED,
        KilnState.BLOCKED,
    }),

    KilnState.REPAIR_TRIAL: frozenset({
        KilnState.CHECKPOINTED,
        KilnState.BLOCKED,
        KilnState.CONTRADICTED,
    }),

    KilnState.CHECKPOINTED: frozenset({
        KilnState.PROMOTED,
        KilnState.REPAIR_TRIAL,
        KilnState.BLOCKED,
    }),

    KilnState.PROMOTED: frozenset({
        KilnState.PROVEN,
        KilnState.EXHAUSTED,
        KilnState.CONTRADICTED,
    }),

    KilnState.CONTRADICTED: frozenset({
        KilnState.RECONCILED,
        KilnState.SUPERSEDED,
        KilnState.BLOCKED,
    }),

    KilnState.RECONCILED: frozenset({
        KilnState.PLAUSIBLE,
        KilnState.PROOF_REQUIRED,
        KilnState.PROVEN,
        KilnState.SUPERSEDED,
    }),

    KilnState.BLOCKED: frozenset({
        KilnState.RECONCILED,
        KilnState.SUPERSEDED,
    }),

    KilnState.EXHAUSTED: frozenset({
        KilnState.SUPERSEDED,
    }),

    KilnState.SUPERSEDED: frozenset(),
}


@dataclass(frozen=True)
class KilnTransition:
    sequence: int
    prior: KilnState
    current: KilnState
    evidence_id: str
    reason: str


class KilnStateMachine:
    """Deterministic refinement-state machine.

    State changes require an explicit allowed edge and evidence identifier.
    """

    def __init__(self, initial: KilnState = KilnState.DISCOVERED) -> None:
        self._state = initial
        self._history: list[KilnTransition] = []

    @property
    def state(self) -> KilnState:
        return self._state

    @property
    def history(self) -> Tuple[KilnTransition, ...]:
        return tuple(self._history)

    def can_transition(self, target: KilnState) -> bool:
        return target in ALLOWED_TRANSITIONS[self._state]

    def transition(
        self,
        target: KilnState,
        *,
        evidence_id: str,
        reason: str,
    ) -> KilnTransition:
        if not evidence_id.strip():
            raise ValueError("Kiln transitions require evidence_id")

        if not reason.strip():
            raise ValueError("Kiln transitions require reason")

        if not self.can_transition(target):
            raise InvalidKilnTransition(
                f"invalid Kiln transition: {self._state.value} -> {target.value}"
            )

        prior = self._state

        event = KilnTransition(
            sequence=len(self._history) + 1,
            prior=prior,
            current=target,
            evidence_id=evidence_id.strip(),
            reason=reason.strip(),
        )

        self._history.append(event)
        self._state = target
        return event
