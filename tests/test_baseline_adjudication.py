import unittest

from engine.baseline_adjudication import adjudicate


class BaselineAdjudicationTests(unittest.TestCase):
    def row(self, result):
        return {
            "plan_id": "PLAN-1",
            "result": result,
            "worktree_removed": "true",
            "original_head_preserved": "true",
        }

    def test_pass_proves_baseline(self):
        result = adjudicate(self.row("PASS"))
        self.assertEqual(result.disposition, "PROVEN_BASELINE")
        self.assertTrue(result.pressure_eligible)

    def test_failure_is_not_automatically_repairable(self):
        result = adjudicate(self.row("FAIL"))
        self.assertEqual(result.disposition, "BASELINE_FRACTURE")
        self.assertFalse(result.pressure_eligible)
        self.assertFalse(result.repair_authorized)

    def test_recovery_failure_blocks_adjudication(self):
        row = self.row("PASS")
        row["worktree_removed"] = "false"

        with self.assertRaises(RuntimeError):
            adjudicate(row)


if __name__ == "__main__":
    unittest.main()
