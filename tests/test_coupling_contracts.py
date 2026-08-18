import unittest

from engine.coupling_contracts import (
    COUPLING_METHODS,
    build_contract,
    coupling_identity,
)


class CouplingContractTests(unittest.TestCase):
    def valid_pressure(self, surface="load"):
        return {
            "contract_id": "PRESSURE-1",
            "plan_id": "PLAN-1",
            "attack_surface": surface,
            "coupling_required": "true",
            "pressure_execution_authorized": "false",
        }

    def test_contract_starts_unproven(self):
        contract = build_contract(self.valid_pressure())
        self.assertFalse(contract.coupling_proven)

    def test_baseline_and_pressured_observation_required(self):
        contract = build_contract(self.valid_pressure())
        self.assertTrue(contract.requires_baseline_observation)
        self.assertTrue(contract.requires_pressured_observation)

    def test_behavioral_difference_required(self):
        contract = build_contract(self.valid_pressure())
        self.assertTrue(contract.requires_behavioral_difference)

    def test_unknown_surface_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build_contract(self.valid_pressure("invented"))

    def test_identity_is_deterministic(self):
        method = COUPLING_METHODS["load"]
        self.assertEqual(
            coupling_identity("P-1", method),
            coupling_identity("P-1", method),
        )


if __name__ == "__main__":
    unittest.main()
