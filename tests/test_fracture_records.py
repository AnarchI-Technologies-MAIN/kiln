import unittest

from engine.fracture_records import fracture_identity


class FractureRecordTests(unittest.TestCase):
    def test_identity_is_deterministic(self):
        one = fracture_identity("P1", "abc", "load", "4x")
        two = fracture_identity("P1", "abc", "load", "4x")
        self.assertEqual(one, two)

    def test_pressure_level_changes_identity(self):
        one = fracture_identity("P1", "abc", "load", "4x")
        two = fracture_identity("P1", "abc", "load", "8x")
        self.assertNotEqual(one, two)


if __name__ == "__main__":
    unittest.main()
