import unittest

from engine.pressure_authorization import PressureAuthorization


class PressureAuthorizationTests(unittest.TestCase):
    def test_authorization_object_is_bounded(self):
        item = PressureAuthorization(
            plan_id="PLAN-1",
            contract_id="PRESSURE-1",
            attack_surface="load",
            authorized=True,
            disposition="PRESSURE_AUTHORIZED",
            max_levels=5,
        )
        self.assertEqual(item.max_levels, 5)

    def test_authorized_state_is_explicit(self):
        item = PressureAuthorization(
            plan_id="PLAN-1",
            contract_id="PRESSURE-1",
            attack_surface="load",
            authorized=False,
            disposition="PRESSURE_BLOCKED",
            max_levels=0,
        )
        self.assertFalse(item.authorized)


if __name__ == "__main__":
    unittest.main()
