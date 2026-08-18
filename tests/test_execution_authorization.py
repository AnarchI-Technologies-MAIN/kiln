import unittest

from engine.execution_authorization import evaluate_plan


class ExecutionAuthorizationTests(unittest.TestCase):
    def valid_plan(self):
        return {
            "plan_id": "PLAN-1",
            "occurrence_id": "OCC-1",
            "content_id": "CONTENT-1",
            "repository_root": "C:/repo",
            "repository_path": "tests/test_one.py",
            "runner": "pytest",
            "attack_surface": "load",
            "recovery_mode": "DETACHED_WORKTREE",
            "execution_mode": "DETACHED_WORKTREE_TEST_EXECUTION",
            "evidence_refs": "E-1",
        }

    def test_valid_plan_authorizes(self):
        decision = evaluate_plan(self.valid_plan())
        self.assertTrue(decision.authorized)
        self.assertEqual(decision.failed_gates, tuple())

    def test_missing_evidence_blocks(self):
        row = self.valid_plan()
        row["evidence_refs"] = ""
        decision = evaluate_plan(row)
        self.assertFalse(decision.authorized)
        self.assertIn("MISSING_EVIDENCE", decision.failed_gates)

    def test_recovery_execution_mismatch_blocks(self):
        row = self.valid_plan()
        row["execution_mode"] = "SANDBOXED_TEST_EXECUTION"
        decision = evaluate_plan(row)
        self.assertFalse(decision.authorized)
        self.assertIn("RECOVERY_EXECUTION_MISMATCH", decision.failed_gates)


if __name__ == "__main__":
    unittest.main()
