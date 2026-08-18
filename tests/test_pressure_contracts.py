import unittest

from engine.pressure_contracts import (
    PRESSURE_LADDERS,
    build_contract,
    contract_identity,
)


class PressureContractTests(unittest.TestCase):
    def valid_plan(self, surface="load"):
        return {
            "plan_id": "PLAN-1",
            "attack_surface": surface,
            "execution_authorized": "true",
        }

    def test_load_ladder_is_bounded(self):
        self.assertEqual(
            PRESSURE_LADDERS["load"],
            ("1x", "2x", "4x", "8x", "16x"),
        )

    def test_contract_requires_coupling(self):
        contract = build_contract(self.valid_plan())
        self.assertTrue(contract.coupling_required)

    def test_contract_does_not_auto_authorize_pressure(self):
        contract = build_contract(self.valid_plan())
        self.assertFalse(contract.execution_authorized)

    def test_unknown_surface_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build_contract(self.valid_plan("invented-surface"))

    def test_unauthorized_plan_fails_closed(self):
        row = self.valid_plan()
        row["execution_authorized"] = "false"
        with self.assertRaises(RuntimeError):
            build_contract(row)

    def test_contract_identity_is_deterministic(self):
        self.assertEqual(
            contract_identity("PLAN-1", "load"),
            contract_identity("PLAN-1", "load"),
        )


if __name__ == "__main__":
    unittest.main()
