import unittest

from engine.campaign_closure import CampaignClosure


class CampaignClosureTests(unittest.TestCase):
    def test_claim_is_bounded_to_load_envelope(self):
        closure = CampaignClosure(
            plan_id="PLAN-1",
            attack_surface="load",
            disposition="LOAD_PRESSURE_ENVELOPE_PROVEN",
            highest_proven_level="16x",
            baseline_proven=True,
            coupling_proven=True,
            fracture_count=0,
            repair_authorized=False,
        )

        self.assertEqual(
            closure.disposition,
            "LOAD_PRESSURE_ENVELOPE_PROVEN",
        )
        self.assertNotEqual(closure.disposition, "UNIVERSALLY_RESILIENT")

    def test_survival_does_not_authorize_repair(self):
        closure = CampaignClosure(
            plan_id="PLAN-1",
            attack_surface="load",
            disposition="LOAD_PRESSURE_ENVELOPE_PROVEN",
            highest_proven_level="16x",
            baseline_proven=True,
            coupling_proven=True,
            fracture_count=0,
            repair_authorized=False,
        )

        self.assertFalse(closure.repair_authorized)


if __name__ == "__main__":
    unittest.main()
