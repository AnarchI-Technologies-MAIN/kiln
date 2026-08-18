import tempfile
import unittest
from pathlib import Path

from engine.compatibility_graph import make_edge
from engine.synthetic_contracts import (
    draft_contract,
    write_contracts,
)


class SyntheticContractTests(unittest.TestCase):

    def test_contract_identity_is_deterministic(self):
        edge = make_edge(
            "A",
            "B",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:1",),
        )

        first = draft_contract(
            "detect stale state",
            "observe stale state before mutation",
            "STATE_STALENESS",
            "python",
            "none",
            ("baseline passes",),
            ("staleness detected",),
            (edge,),
        )

        second = draft_contract(
            "detect stale state",
            "observe stale state before mutation",
            "STATE_STALENESS",
            "python",
            "none",
            ("baseline passes",),
            ("staleness detected",),
            (edge,),
        )

        self.assertEqual(
            first.contract_id,
            second.contract_id,
        )

    def test_all_proven_evidence_can_reach_synthesis_readiness(self):
        first = make_edge(
            "A",
            "B",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:1",),
        )

        second = make_edge(
            "B",
            "C",
            "PROMOTED_AS",
            "PROVEN",
            ("proof:2",),
        )

        contract = draft_contract(
            "exercise recovery",
            "prove recovery continuity",
            "RECOVERY_FAILURE",
            "python",
            "filesystem",
            ("baseline preserved",),
            ("recovery proven",),
            (first,second),
        )

        self.assertEqual(
            contract.proof_state,
            "EVIDENCE_SUFFICIENT_FOR_SYNTHESIS",
        )

        self.assertFalse(
            contract.synthesis_authorized
        )

        self.assertFalse(
            contract.execution_authorized
        )

    def test_rejected_evidence_blocks_contract(self):
        rejected = make_edge(
            "A",
            "B",
            "INCOMPATIBLE_WITH",
            "REJECTED",
            ("proof:reject",),
        )

        contract = draft_contract(
            "compose incompatible fragments",
            "should never execute",
            "INCOMPATIBILITY",
            "python",
            "none",
            (),
            (),
            (rejected,),
        )

        self.assertEqual(
            contract.proof_state,
            "BLOCKED",
        )

    def test_contract_materialization_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "contracts.csv"

            edge = make_edge(
                "A",
                "B",
                "SURVIVED_WITH",
                "PROVEN",
                ("proof:1",),
            )

            contract = draft_contract(
                "exercise recovery",
                "prove recovery continuity",
                "RECOVERY_FAILURE",
                "python",
                "filesystem",
                ("baseline preserved",),
                ("recovery proven",),
                (edge,),
            )

            write_contracts(
                path,
                (contract,),
            )

            before = path.read_bytes()

            write_contracts(
                path,
                (contract,),
            )

            self.assertEqual(
                before,
                path.read_bytes(),
            )


    def test_partial_graph_evidence_identifies_synthetic_candidate(self):
        from engine.compatibility_graph import make_edge
        from engine.synthetic_contracts import identify_capability_gap

        observed = make_edge(
            "TEST-A",
            "MUTATION-A",
            "ADDITIONAL_PRESSURE_REQUIRED",
            "OBSERVED",
            ("proof:1",),
            environment="wsl2",
            dependency_shape="filesystem",
            attack_surface="state-staleness",
        )

        gap = identify_capability_gap(
            required_capability="detect stale filesystem state",
            attack_surface="state-staleness",
            environment_contract="wsl2",
            dependency_contract="filesystem",
            edges=(observed,),
        )

        self.assertFalse(
            gap.satisfied
        )

        self.assertEqual(
            gap.disposition,
            "SYNTHETIC_CONTRACT_CANDIDATE",
        )

        self.assertIn(
            "PROVEN_BEHAVIOR",
            gap.missing_dimensions,
        )

    def test_no_supporting_evidence_marks_gap_unsupported(self):
        from engine.synthetic_contracts import identify_capability_gap

        gap = identify_capability_gap(
            required_capability="detect unknown failure",
            attack_surface="unknown-surface",
            environment_contract="wsl2",
            dependency_contract="filesystem",
            edges=(),
        )

        self.assertEqual(
            gap.disposition,
            "CAPABILITY_GAP_UNSUPPORTED",
        )

    def test_gap_can_draft_non_executable_contract(self):
        from engine.compatibility_graph import make_edge
        from engine.synthetic_contracts import (
            draft_contract_from_gap,
            identify_capability_gap,
        )

        observed = make_edge(
            "TEST-A",
            "MUTATION-A",
            "ADDITIONAL_PRESSURE_REQUIRED",
            "OBSERVED",
            ("proof:1",),
            environment="wsl2",
            dependency_shape="filesystem",
            attack_surface="state-staleness",
        )

        gap = identify_capability_gap(
            required_capability="detect stale filesystem state",
            attack_surface="state-staleness",
            environment_contract="wsl2",
            dependency_contract="filesystem",
            edges=(observed,),
        )

        contract = draft_contract_from_gap(
            gap,
            (observed,),
            ("baseline preserved",),
            ("staleness detected",),
        )

        self.assertEqual(
            contract.proof_state,
            "PARTIALLY_SUPPORTED",
        )

        self.assertFalse(
            contract.synthesis_authorized
        )

        self.assertFalse(
            contract.execution_authorized
        )

    def test_satisfied_capability_is_retained_as_gap_evidence(self):
        from engine.compatibility_graph import make_edge
        from engine.synthetic_contracts import identify_capability_gap

        proven = make_edge(
            "TEST-A",
            "CAPABILITY-A",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:1",),
            environment="wsl2",
            dependency_shape="filesystem",
            attack_surface="state-staleness",
        )

        gap = identify_capability_gap(
            required_capability="detect stale filesystem state",
            attack_surface="state-staleness",
            environment_contract="wsl2",
            dependency_contract="filesystem",
            edges=(proven,),
        )

        self.assertTrue(
            gap.satisfied
        )

        self.assertEqual(
            gap.disposition,
            "CAPABILITY_SATISFIED",
        )

    def test_gap_registry_materialization_is_deterministic(self):
        import tempfile
        from pathlib import Path

        from engine.compatibility_graph import make_edge
        from engine.synthetic_contracts import (
            identify_capability_gap,
            write_capability_gaps,
        )

        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"gaps.csv"

            observed=make_edge(
                "TEST-A",
                "MUTATION-A",
                "ADDITIONAL_PRESSURE_REQUIRED",
                "OBSERVED",
                ("proof:1",),
                environment="wsl2",
                dependency_shape="filesystem",
                attack_surface="state-staleness",
            )

            first=identify_capability_gap(
                "detect stale state",
                "state-staleness",
                "wsl2",
                "filesystem",
                (observed,),
            )

            second=identify_capability_gap(
                "detect load failure",
                "load",
                "wsl2",
                "process",
                (),
            )

            write_capability_gaps(
                path,
                (second,first),
            )

            before=path.read_bytes()

            write_capability_gaps(
                path,
                (first,second),
            )

            self.assertEqual(
                before,
                path.read_bytes(),
            )

if __name__ == "__main__":
    unittest.main()
