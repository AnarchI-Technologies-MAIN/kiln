import unittest

from engine.coupling_adjudication import adjudicate


class CouplingAdjudicationTests(unittest.TestCase):
    def row(self):
        return {
            "plan_id": "PLAN-1",
            "coupling_id": "COUPLING-1",
            "coupling_proven": "true",
            "worktree_removed": "true",
            "original_head_preserved": "true",
        }

    def test_proven_coupling_becomes_pressure_eligible(self):
        result = adjudicate(self.row())
        self.assertEqual(result.disposition, "PROVEN_COUPLING")
        self.assertTrue(result.pressure_eligible)

    def test_unproven_coupling_blocks_pressure(self):
        row = self.row()
        row["coupling_proven"] = "false"
        result = adjudicate(row)
        self.assertEqual(result.disposition, "UNPROVEN_COUPLING")
        self.assertFalse(result.pressure_eligible)

    def test_recovery_failure_becomes_trial_fracture(self):
        row = self.row()
        row["worktree_removed"] = "false"
        result = adjudicate(row)
        self.assertEqual(result.disposition, "COUPLING_TRIAL_FRACTURE")
        self.assertFalse(result.pressure_eligible)

    def test_repair_never_auto_authorizes(self):
        result = adjudicate(self.row())
        self.assertFalse(result.repair_authorized)


if __name__ == "__main__":
    unittest.main()
