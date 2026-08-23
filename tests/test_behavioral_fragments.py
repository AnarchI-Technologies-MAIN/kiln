import tempfile
import unittest
from pathlib import Path

from engine.behavioral_fragments import (
    hash_text,
    virtual_fragment,
    write_fragments,
)


class BehavioralFragmentTests(unittest.TestCase):

    def test_virtual_fragment_does_not_modify_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"test_example.py"

            content=(
                "def test_example():\n"
                "    value = 40\n"
                "    result = value + 2\n"
                "    assert result == 42\n"
            )

            source.write_text(
                content,
                encoding="utf-8",
            )

            before=source.read_bytes()

            fragment=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                3,
                1,
                2,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            after=source.read_bytes()

            self.assertEqual(
                before,
                after,
            )

            self.assertEqual(
                fragment.source_text,
                "    value = 40\n"
                "    result = value + 2\n",
            )

    def test_fragment_identity_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_example.py"

            source.write_text(
                "def test_example():\n"
                "    value = 42\n"
                "    assert value == 42\n",
                encoding="utf-8",
            )

            first=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                2,
                1,
                2,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            second=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                2,
                1,
                2,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            self.assertEqual(
                first.fragment_id,
                second.fragment_id,
            )

    def test_parent_change_changes_fragment_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_example.py"

            source.write_text(
                "def test_example():\n"
                "    value = 41\n",
                encoding="utf-8",
            )

            first=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            source.write_text(
                "def test_example():\n"
                "    value = 42\n",
                encoding="utf-8",
            )

            second=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            self.assertNotEqual(
                first.fragment_id,
                second.fragment_id,
            )

            self.assertNotEqual(
                first.parent_source_hash,
                second.parent_source_hash,
            )

    def test_fragment_registry_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"test_example.py"
            registry=root/"fragments.csv"

            source.write_text(
                "def test_example():\n"
                "    value = 42\n"
                "    assert value == 42\n",
                encoding="utf-8",
            )

            action=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                2,
                2,
                1,
                2,
                "ACTION",
                "test:TEST-EXAMPLE",
            )

            assertion=virtual_fragment(
                "TEST-EXAMPLE",
                source,
                3,
                3,
                2,
                2,
                "ASSERTION",
                "test:TEST-EXAMPLE",
            )

            write_fragments(
                registry,
                (assertion,action),
            )

            before=registry.read_bytes()

            write_fragments(
                registry,
                (action,assertion),
            )

            self.assertEqual(
                before,
                registry.read_bytes(),
            )


    def test_python_discovery_virtualizes_test_sequence(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import discover_python_test_fragments

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_sequence.py"

            source.write_text(
                "def test_sequence():\n"
                "    value = 40\n"
                "    result = value + 2\n"
                "    assert result == 42\n",
                encoding="utf-8",
            )

            before=source.read_bytes()

            fragments=discover_python_test_fragments(
                source,
                "static-ast:test_sequence",
            )

            self.assertEqual(
                len(fragments),
                3,
            )

            self.assertEqual(
                tuple(
                    item.sequence_position
                    for item in fragments
                ),
                (1,2,3),
            )

            self.assertEqual(
                tuple(
                    item.role
                    for item in fragments
                ),
                (
                    "SETUP",
                    "SETUP",
                    "ASSERTION",
                ),
            )

            self.assertEqual(
                before,
                source.read_bytes(),
            )

    def test_python_discovery_preserves_unknown_classification(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import discover_python_test_fragments

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_unknown.py"

            source.write_text(
                "def test_unknown():\n"
                "    if True:\n"
                "        value = 42\n"
                "    assert value == 42\n",
                encoding="utf-8",
            )

            fragments=discover_python_test_fragments(
                source,
                "static-ast:test_unknown",
            )

            self.assertEqual(
                fragments[0].role,
                "UNKNOWN",
            )

            self.assertEqual(
                fragments[1].role,
                "ASSERTION",
            )

    def test_python_discovery_handles_assert_raises_as_assertion(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import discover_python_test_fragments

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_failure.py"

            source.write_text(
                "def test_failure(self):\n"
                "    with self.assertRaises(RuntimeError):\n"
                "        explode()\n",
                encoding="utf-8",
            )

            fragments=discover_python_test_fragments(
                source,
                "static-ast:test_failure",
            )

            self.assertEqual(
                len(fragments),
                1,
            )

            self.assertEqual(
                fragments[0].role,
                "ASSERTION",
            )

    def test_python_discovery_classifies_unittest_assertion_call(self):
        from engine.behavioral_fragments import discover_python_test_fragments

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_assertion.py"
            source.write_text(
                "def test_assertion(self):\n"
                "    self.assertTrue(value)\n",
                encoding="utf-8",
            )

            fragments=discover_python_test_fragments(
                source,
                "static:test_assertion",
            )

            self.assertEqual(
                fragments[0].role,
                "ASSERTION",
            )

    def test_python_fragment_identity_changes_with_sequence_role(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import virtual_fragment

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_identity.py"

            source.write_text(
                "def test_identity():\n"
                "    operation()\n",
                encoding="utf-8",
            )

            action=virtual_fragment(
                "TEST-IDENTITY",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "static:test",
            )

            observation=virtual_fragment(
                "TEST-IDENTITY",
                source,
                2,
                2,
                1,
                1,
                "OBSERVATION",
                "static:test",
            )

            self.assertNotEqual(
                action.fragment_id,
                observation.fragment_id,
            )

    def test_runtime_observation_does_not_rewrite_static_role(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import (
            observe_fragment,
            virtual_fragment,
        )

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_role.py"

            source.write_text(
                "def test_role():\n"
                "    result = operation()\n",
                encoding="utf-8",
            )

            fragment=virtual_fragment(
                "TEST-ROLE",
                source,
                2,
                2,
                1,
                1,
                "SETUP",
                "static:test",
            )

            observation=observe_fragment(
                fragment,
                "EXEC-1",
                True,
                True,
                False,
                False,
                True,
                "",
                "ACTION",
                "runtime:EXEC-1",
            )

            self.assertEqual(
                fragment.role,
                "SETUP",
            )

            self.assertEqual(
                observation.observed_role,
                "ACTION",
            )

    def test_fragment_history_accumulates_runtime_evidence(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import (
            observe_fragment,
            summarize_fragment_history,
            virtual_fragment,
        )

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_history.py"

            source.write_text(
                "def test_history():\n"
                "    operation()\n",
                encoding="utf-8",
            )

            fragment=virtual_fragment(
                "TEST-HISTORY",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "static:test",
            )

            first=observe_fragment(
                fragment,
                "EXEC-1",
                True,
                True,
                False,
                False,
                True,
                "",
                "ACTION",
                "runtime:1",
            )

            second=observe_fragment(
                fragment,
                "EXEC-2",
                True,
                False,
                True,
                True,
                False,
                "SOFT_ROLLBACK",
                "ACTION",
                "runtime:2",
            )

            history=summarize_fragment_history(
                fragment.fragment_id,
                (second,first),
            )

            self.assertEqual(
                history.execution_count,
                2,
            )

            self.assertEqual(
                history.reached_count,
                2,
            )

            self.assertEqual(
                history.pass_count,
                1,
            )

            self.assertEqual(
                history.failure_count,
                1,
            )

            self.assertEqual(
                history.downstream_failure_count,
                1,
            )

            self.assertEqual(
                history.mutation_survival_count,
                1,
            )

            self.assertEqual(
                history.soft_rollback_count,
                1,
            )

    def test_unreached_fragment_cannot_claim_direct_success(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import (
            observe_fragment,
            virtual_fragment,
        )

        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"test_unreached.py"

            source.write_text(
                "def test_unreached():\n"
                "    operation()\n",
                encoding="utf-8",
            )

            fragment=virtual_fragment(
                "TEST-UNREACHED",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "static:test",
            )

            with self.assertRaises(RuntimeError):
                observe_fragment(
                    fragment,
                    "EXEC-1",
                    False,
                    True,
                    False,
                    False,
                    False,
                    "",
                    "",
                    "runtime:1",
                )

    def test_fragment_history_materialization_is_deterministic(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import (
            observe_fragment,
            summarize_fragment_history,
            virtual_fragment,
            write_fragment_history,
        )

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"test_registry.py"
            registry=root/"history.csv"

            source.write_text(
                "def test_registry():\n"
                "    operation()\n",
                encoding="utf-8",
            )

            fragment=virtual_fragment(
                "TEST-REGISTRY",
                source,
                2,
                2,
                1,
                1,
                "ACTION",
                "static:test",
            )

            observation=observe_fragment(
                fragment,
                "EXEC-1",
                True,
                True,
                False,
                False,
                True,
                "",
                "ACTION",
                "runtime:1",
            )

            history=summarize_fragment_history(
                fragment.fragment_id,
                (observation,),
            )

            write_fragment_history(
                registry,
                (history,),
            )

            before=registry.read_bytes()

            write_fragment_history(
                registry,
                (history,),
            )

            self.assertEqual(
                before,
                registry.read_bytes(),
            )

    def test_effectiveness_preserves_dimensions_instead_of_magic_score(self):
        from engine.behavioral_fragments import (
            FragmentHistory,
            fragment_effectiveness,
        )

        history=FragmentHistory(
            fragment_id="FRAGMENT-A",
            execution_count=10,
            reached_count=8,
            pass_count=6,
            failure_count=2,
            downstream_failure_count=3,
            mutation_survival_count=7,
            soft_rollback_count=1,
            hard_rollback_count=1,
            observed_roles=("ACTION",),
            evidence_refs=("proof:1",),
        )

        record=fragment_effectiveness(
            history
        )

        self.assertEqual(
            record.reach_rate,
            0.8,
        )

        self.assertEqual(
            record.pass_rate_when_reached,
            0.75,
        )

        self.assertEqual(
            record.direct_failure_rate_when_reached,
            0.25,
        )

        self.assertEqual(
            record.downstream_failure_rate,
            0.3,
        )

        self.assertEqual(
            record.mutation_survival_rate,
            0.7,
        )

        self.assertEqual(
            record.rollback_rate,
            0.2,
        )

        self.assertEqual(
            record.disposition,
            "BEHAVIORALLY_CONTESTED",
        )

    def test_no_runtime_evidence_is_explicit(self):
        from engine.behavioral_fragments import (
            FragmentHistory,
            fragment_effectiveness,
        )

        history=FragmentHistory(
            fragment_id="FRAGMENT-EMPTY",
            execution_count=0,
            reached_count=0,
            pass_count=0,
            failure_count=0,
            downstream_failure_count=0,
            mutation_survival_count=0,
            soft_rollback_count=0,
            hard_rollback_count=0,
            observed_roles=(),
            evidence_refs=(),
        )

        record=fragment_effectiveness(
            history
        )

        self.assertEqual(
            record.disposition,
            "NO_RUNTIME_EVIDENCE",
        )

    def test_effectiveness_ranking_is_deterministic(self):
        from engine.behavioral_fragments import (
            FragmentHistory,
            rank_fragment_effectiveness,
        )

        stronger=FragmentHistory(
            fragment_id="STRONGER",
            execution_count=10,
            reached_count=10,
            pass_count=10,
            failure_count=0,
            downstream_failure_count=0,
            mutation_survival_count=9,
            soft_rollback_count=0,
            hard_rollback_count=0,
            observed_roles=("ASSERTION",),
            evidence_refs=("proof:1",),
        )

        weaker=FragmentHistory(
            fragment_id="WEAKER",
            execution_count=10,
            reached_count=10,
            pass_count=8,
            failure_count=2,
            downstream_failure_count=1,
            mutation_survival_count=4,
            soft_rollback_count=1,
            hard_rollback_count=0,
            observed_roles=("ASSERTION",),
            evidence_refs=("proof:2",),
        )

        first=rank_fragment_effectiveness(
            (weaker,stronger)
        )

        second=rank_fragment_effectiveness(
            (stronger,weaker)
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            first[0].fragment_id,
            "STRONGER",
        )

    def test_effectiveness_registry_is_deterministic(self):
        import tempfile
        from pathlib import Path

        from engine.behavioral_fragments import (
            FragmentHistory,
            fragment_effectiveness,
            write_fragment_effectiveness,
        )

        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"effectiveness.csv"

            history=FragmentHistory(
                fragment_id="FRAGMENT-A",
                execution_count=4,
                reached_count=4,
                pass_count=4,
                failure_count=0,
                downstream_failure_count=0,
                mutation_survival_count=3,
                soft_rollback_count=0,
                hard_rollback_count=0,
                observed_roles=("ACTION",),
                evidence_refs=("proof:1",),
            )

            record=fragment_effectiveness(
                history
            )

            write_fragment_effectiveness(
                path,
                (record,),
            )

            before=path.read_bytes()

            write_fragment_effectiveness(
                path,
                (record,),
            )

            self.assertEqual(
                before,
                path.read_bytes(),
            )

if __name__ == "__main__":
    unittest.main()
