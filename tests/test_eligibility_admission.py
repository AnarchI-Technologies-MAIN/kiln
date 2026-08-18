import tempfile
import unittest
from pathlib import Path

from engine.eligibility_admission import DISPOSITION_MAP, RESTRICTIVENESS


class EligibilityAdmissionTests(unittest.TestCase):
    def test_all_known_preflight_dispositions_have_mapping(self):
        expected = {
            "READY_FOR_BASELINE_EXECUTION_PLANNING",
            "READY_BUT_DIRTY_REPOSITORY",
            "ISOLATION_TOPOLOGY_REQUIRED",
            "SANDBOX_TOPOLOGY_REQUIRED",
            "RUNNER_RECONCILIATION_REQUIRED",
            "SUPPORT_ARTIFACT_ONLY",
            "BLOCKED",
        }
        self.assertEqual(set(DISPOSITION_MAP), expected)

    def test_blocked_is_more_restrictive_than_eligible(self):
        self.assertGreater(
            RESTRICTIVENESS["BLOCKED"],
            RESTRICTIVENESS["ELIGIBLE"],
        )

    def test_runner_blocked_is_not_treated_as_eligible(self):
        self.assertEqual(
            DISPOSITION_MAP["RUNNER_RECONCILIATION_REQUIRED"],
            "RUNNER_BLOCKED",
        )


if __name__ == "__main__":
    unittest.main()
