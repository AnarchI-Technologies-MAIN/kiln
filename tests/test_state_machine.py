import unittest

from engine.state_machine import (
    InvalidKilnTransition,
    KilnState,
    KilnStateMachine,
)


class KilnStateMachineTests(unittest.TestCase):
    def test_valid_refinement_path(self):
        machine = KilnStateMachine()

        machine.transition(
            KilnState.UNADJUDICATED,
            evidence_id="E-001",
            reason="candidate requires adjudication",
        )

        machine.transition(
            KilnState.PLAUSIBLE,
            evidence_id="E-002",
            reason="static evidence supports candidate",
        )

        machine.transition(
            KilnState.PROOF_REQUIRED,
            evidence_id="E-003",
            reason="dynamic proof required",
        )

        machine.transition(
            KilnState.PROVEN,
            evidence_id="E-004",
            reason="dynamic coupling proven",
        )

        self.assertEqual(machine.state, KilnState.PROVEN)
        self.assertEqual(len(machine.history), 4)

    def test_invalid_jump_is_refused(self):
        machine = KilnStateMachine()

        with self.assertRaises(InvalidKilnTransition):
            machine.transition(
                KilnState.PROMOTED,
                evidence_id="E-BAD",
                reason="attempted illegal jump",
            )

        self.assertEqual(machine.state, KilnState.DISCOVERED)
        self.assertEqual(len(machine.history), 0)

    def test_evidence_is_required(self):
        machine = KilnStateMachine()

        with self.assertRaises(ValueError):
            machine.transition(
                KilnState.UNADJUDICATED,
                evidence_id="",
                reason="missing evidence identifier",
            )

    def test_contradicted_evidence_can_be_reconciled(self):
        machine = KilnStateMachine(KilnState.PROVEN)

        machine.transition(
            KilnState.CONTRADICTED,
            evidence_id="E-C1",
            reason="later evidence invalidated prior proof",
        )

        machine.transition(
            KilnState.RECONCILED,
            evidence_id="E-C2",
            reason="contradiction resolved",
        )

        self.assertEqual(machine.state, KilnState.RECONCILED)

    def test_superseded_is_terminal(self):
        machine = KilnStateMachine(KilnState.EXHAUSTED)

        machine.transition(
            KilnState.SUPERSEDED,
            evidence_id="E-S1",
            reason="new evidence supersedes old result",
        )

        self.assertFalse(machine.can_transition(KilnState.PROVEN))


if __name__ == "__main__":
    unittest.main()
