import unittest

from engine.candidate_selection import (
    candidate_identity,
    split_values,
    RECOVERY_MODE,
)


class CandidateSelectionTests(unittest.TestCase):
    def test_split_values_is_sorted_and_deduplicated(self):
        observed = split_values("load;authority-conflict;load")
        self.assertEqual(
            observed,
            ("authority-conflict", "load"),
        )

    def test_candidate_identity_is_deterministic(self):
        one = candidate_identity(
            "OCC-1",
            "CONTENT-1",
            ("load",),
        )
        two = candidate_identity(
            "OCC-1",
            "CONTENT-1",
            ("load",),
        )
        self.assertEqual(one, two)

    def test_isolation_mapping_fails_conservatively(self):
        self.assertEqual(
            RECOVERY_MODE["REQUIRES_ISOLATION"],
            "DETACHED_WORKTREE",
        )

    def test_sandbox_mapping_remains_stricter(self):
        self.assertEqual(
            RECOVERY_MODE["REQUIRES_SANDBOX"],
            "SANDBOX",
        )


if __name__ == "__main__":
    unittest.main()
