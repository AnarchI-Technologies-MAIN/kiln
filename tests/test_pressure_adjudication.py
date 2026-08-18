import unittest

from engine.pressure_adjudication import adjudicate_plan


class PressureAdjudicationTests(unittest.TestCase):
    def row(self, level, survived="true"):
        return {
            "plan_id": "PLAN-1",
            "contract_id": "PRESSURE-1",
            "pressure_level": level,
            "survived": survived,
            "worktree_removed": "true",
            "original_head_preserved": "true",
        }

    def test_complete_envelope_survival(self):
        rows = [
            self.row("1x"),
            self.row("2x"),
            self.row("4x"),
            self.row("8x"),
            self.row("16x"),
        ]

        result = adjudicate_plan(rows)
        self.assertEqual(
            result.disposition,
            "PRESSURE_ENVELOPE_SURVIVED",
        )
        self.assertEqual(result.highest_survived_level, "16x")

    def test_first_failure_becomes_fracture(self):
        rows = [
            self.row("1x"),
            self.row("2x"),
            self.row("4x", "false"),
        ]

        result = adjudicate_plan(rows)
        self.assertEqual(result.disposition, "PRESSURE_FRACTURE")
        self.assertEqual(result.highest_survived_level, "2x")
        self.assertEqual(result.fracture_level, "4x")
        self.assertFalse(result.repair_authorized)

    def test_incomplete_nonfractured_envelope_fails_closed(self):
        rows = [
            self.row("1x"),
            self.row("2x"),
        ]

        with self.assertRaises(RuntimeError):
            adjudicate_plan(rows)


if __name__ == "__main__":
    unittest.main()
