import tempfile
import unittest
from pathlib import Path

from engine.compatibility_graph import (
    make_edge,
    write_graph,
)


class CompatibilityGraphTests(unittest.TestCase):

    def test_edge_identity_is_deterministic(self):
        first = make_edge(
            "TEST-A",
            "MUTATION-B",
            "REGRESSION_INTRODUCED",
            "OBSERVED",
            ("evidence:2","evidence:1"),
        )

        second = make_edge(
            "TEST-A",
            "MUTATION-B",
            "REGRESSION_INTRODUCED",
            "OBSERVED",
            ("evidence:1","evidence:2"),
        )

        self.assertEqual(
            first.edge_id,
            second.edge_id,
        )

    def test_proven_edge_requires_evidence(self):
        with self.assertRaises(RuntimeError):
            make_edge(
                "FRAGMENT-A",
                "FRAGMENT-B",
                "COMPATIBLE_WITH",
                "PROVEN",
                (),
            )

    def test_inferred_edge_remains_explicitly_inferred(self):
        edge = make_edge(
            "FRAGMENT-A",
            "FRAGMENT-B",
            "SHAPE_COMPATIBLE",
            "INFERRED",
            (),
            language="python",
            test_shape="assertion",
        )

        self.assertEqual(
            edge.proof_state,
            "INFERRED",
        )

        self.assertNotEqual(
            edge.proof_state,
            "PROVEN",
        )

    def test_graph_materialization_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.csv"

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
                "REGRESSION_INTRODUCED",
                "OBSERVED",
                ("proof:2",),
            )

            write_graph(
                path,
                (second,first),
            )

            before = path.read_bytes()

            write_graph(
                path,
                (first,second),
            )

            after = path.read_bytes()

            self.assertEqual(
                before,
                after,
            )


    def test_soft_rollback_becomes_observed_causal_edge(self):
        from engine.compatibility_graph import edges_from_redesign_route

        edges = edges_from_redesign_route(
            candidate_id="GENERATION-2",
            parent_id="GENERATION-1",
            route="SOFT_ROLLBACK",
            reasons=(
                "BASELINE_REGRESSION",
                "NEW_REGRESSION_OBSERVED",
            ),
            evidence_ref="rollback:evidence-1",
        )

        self.assertEqual(
            len(edges),
            1,
        )

        edge = edges[0]

        self.assertEqual(
            edge.relationship,
            "SOFT_ROLLBACK_CAUSED",
        )

        self.assertEqual(
            edge.proof_state,
            "OBSERVED",
        )

        self.assertIn(
            "BASELINE_REGRESSION",
            edge.failure_semantics,
        )

    def test_return_to_fire_does_not_become_proven_compatibility(self):
        from engine.compatibility_graph import edges_from_redesign_route

        edge = edges_from_redesign_route(
            candidate_id="GENERATION-3",
            parent_id="GENERATION-2",
            route="RETURN_TO_FIRE",
            reasons=(
                "MORE_BREAKAGE_EVIDENCE_REQUIRED",
            ),
            evidence_ref="route:evidence-2",
        )[0]

        self.assertEqual(
            edge.relationship,
            "ADDITIONAL_PRESSURE_REQUIRED",
        )

        self.assertEqual(
            edge.proof_state,
            "OBSERVED",
        )

        self.assertNotEqual(
            edge.proof_state,
            "PROVEN",
        )

    def test_verified_promotion_creates_proven_edge(self):
        from engine.compatibility_graph import edge_from_verified_promotion

        edge = edge_from_verified_promotion(
            candidate_id="KILN-REDESIGN-TEST",
            commit_hash="abc123def456",
            evidence_ref="promotion:evidence-3",
        )

        self.assertEqual(
            edge.relationship,
            "PROMOTED_AS",
        )

        self.assertEqual(
            edge.proof_state,
            "PROVEN",
        )

        self.assertEqual(
            edge.target_id,
            "abc123def456",
        )

        self.assertEqual(
            edge.functional_continuity,
            "PROMOTION_VERIFIED",
        )

    def test_query_filters_by_node_dimensions_and_proof(self):
        from engine.compatibility_graph import (
            CompatibilityQuery,
            make_edge,
            query_compatibility,
        )

        proven = make_edge(
            "FRAGMENT-A",
            "FRAGMENT-B",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:1",),
            language="python",
            environment="wsl2",
            test_shape="assertion",
        )

        inferred = make_edge(
            "FRAGMENT-A",
            "FRAGMENT-C",
            "SHAPE_COMPATIBLE",
            "INFERRED",
            (),
            language="python",
            environment="wsl2",
            test_shape="assertion",
        )

        wrong_environment = make_edge(
            "FRAGMENT-A",
            "FRAGMENT-D",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:2",),
            language="python",
            environment="windows",
            test_shape="assertion",
        )

        matches = query_compatibility(
            (
                wrong_environment,
                inferred,
                proven,
            ),
            CompatibilityQuery(
                node_id="FRAGMENT-A",
                language="python",
                environment="wsl2",
                test_shape="assertion",
                proof_states=("PROVEN",),
            ),
        )

        self.assertEqual(
            matches,
            (proven,),
        )

    def test_query_without_proof_filter_preserves_epistemic_states(self):
        from engine.compatibility_graph import (
            CompatibilityQuery,
            make_edge,
            query_compatibility,
        )

        observed = make_edge(
            "A",
            "B",
            "REGRESSION_INTRODUCED",
            "OBSERVED",
            ("proof:1",),
        )

        inferred = make_edge(
            "A",
            "C",
            "SHAPE_COMPATIBLE",
            "INFERRED",
            (),
        )

        matches = query_compatibility(
            (inferred,observed),
            CompatibilityQuery(
                node_id="A",
            ),
        )

        self.assertEqual(
            {edge.proof_state for edge in matches},
            {"OBSERVED","INFERRED"},
        )

    def test_proven_neighbors_excludes_inferred_relationships(self):
        from engine.compatibility_graph import (
            make_edge,
            proven_neighbors,
        )

        proven = make_edge(
            "A",
            "B",
            "SURVIVED_WITH",
            "PROVEN",
            ("proof:1",),
        )

        inferred = make_edge(
            "A",
            "C",
            "SHAPE_COMPATIBLE",
            "INFERRED",
            (),
        )

        neighbors = proven_neighbors(
            (inferred,proven),
            "A",
        )

        self.assertEqual(
            neighbors,
            ("B",),
        )

if __name__ == "__main__":
    unittest.main()
