import unittest

from engine.attack_surface_admission import first


class AttackSurfaceAdmissionTests(unittest.TestCase):
    def test_first_uses_first_nonempty_alias(self):
        row = {"surface": "", "attack_surface": "authority-conflict"}
        self.assertEqual(
            first(row, ("surface", "attack_surface")),
            "authority-conflict",
        )

    def test_missing_value_returns_empty_string(self):
        self.assertEqual(first({}, ("x", "y")), "")


if __name__ == "__main__":
    unittest.main()
