import unittest

from engine.execution_planning import (
    execution_mode,
    plan_identity,
)


class ExecutionPlanningTests(unittest.TestCase):
    def test_plan_identity_is_deterministic(self):
        one = plan_identity("CANDIDATE-1", "load")
        two = plan_identity("CANDIDATE-1", "load")
        self.assertEqual(one, two)

    def test_different_surfaces_get_different_plans(self):
        load = plan_identity("CANDIDATE-1", "load")
        auth = plan_identity("CANDIDATE-1", "authority-conflict")
        self.assertNotEqual(load, auth)

    def test_detached_worktree_mode(self):
        self.assertEqual(
            execution_mode("DETACHED_WORKTREE"),
            "DETACHED_WORKTREE_TEST_EXECUTION",
        )

    def test_sandbox_mode(self):
        self.assertEqual(
            execution_mode("SANDBOX"),
            "SANDBOXED_TEST_EXECUTION",
        )

    def test_unknown_recovery_mode_fails_closed(self):
        with self.assertRaises(RuntimeError):
            execution_mode("INVENTED_MODE")


if __name__ == "__main__":
    unittest.main()
