import tempfile
import unittest
from pathlib import Path
import csv

from engine.capability_negotiation import negotiate


class CapabilityNegotiationTests(unittest.TestCase):

    def write(self, path, rows):
        with Path(path).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=rows[0].keys(),
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_authorized_injector_surface_is_proven(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            execution = root / "execution.csv"
            plans = root / "plans.csv"
            surfaces = root / "surfaces.csv"
            injectors = root / "injectors.csv"

            self.write(execution, [{
                "plan_id": "PLAN-1",
                "authorized": "true",
                "disposition": "AUTHORIZED",
                "failed_gates": "",
            }])

            self.write(plans, [{
                "plan_id": "PLAN-1",
                "attack_surface": "filesystem-state",
            }])

            self.write(surfaces, [{
                "attack_surface": "filesystem-state",
                "readiness": "CONTRACT_ONLY",
            }])

            self.write(injectors, [{
                "attack_surface": "filesystem-state",
                "authorized": "true",
                "max_trials": "1",
            }])

            result = negotiate(
                execution,
                plans,
                surfaces,
                injectors,
            )[0]

            self.assertTrue(
                result.injector_authorized
            )
            self.assertEqual(
                result.max_injector_trials,
                1,
            )
            self.assertEqual(
                result.disposition,
                "CAPABILITY_PROVEN",
            )

    def test_surface_does_not_borrow_unrelated_execution_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            execution = root / "execution.csv"
            plans = root / "plans.csv"
            surfaces = root / "surfaces.csv"
            injectors = root / "injectors.csv"

            self.write(execution, [{
                "plan_id": "LOAD-PLAN",
                "attack_surface": "load",
                "authorized": "true",
                "disposition": "AUTHORIZED",
                "failed_gates": "",
            }])

            self.write(plans, [{
                "plan_id": "LOAD-PLAN",
                "attack_surface": "load",
            }])

            self.write(surfaces, [{
                "attack_surface": "filesystem-state",
                "readiness": "CONTRACT_ONLY",
            }])

            self.write(injectors, [{
                "attack_surface": "filesystem-state",
                "authorized": "true",
                "max_trials": "1",
            }])

            result = negotiate(
                execution,
                plans,
                surfaces,
                injectors,
            )[0]

            self.assertFalse(
                result.execution_authorized
            )
    def test_contract_only_without_injector_blocks_trial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            execution = root / "execution.csv"
            plans = root / "plans.csv"
            surfaces = root / "surfaces.csv"
            injectors = root / "injectors.csv"

            self.write(execution, [{
                "plan_id": "PLAN-1",
                "authorized": "true",
                "disposition": "AUTHORIZED",
                "failed_gates": "",
            }])

            self.write(plans, [{
                "plan_id": "PLAN-1",
                "attack_surface": "filesystem-state",
            }])

            self.write(surfaces, [{
                "attack_surface": "state-staleness",
                "readiness": "CONTRACT_ONLY",
            }])

            self.write(injectors, [{
                "attack_surface": "filesystem-state",
                "authorized": "true",
                "max_trials": "1",
            }])

            result = negotiate(
                execution,
                plans,
                surfaces,
                injectors,
            )[0]

            self.assertFalse(
                result.injector_authorized
            )
            self.assertEqual(
                result.disposition,
                "CAPABILITY_BLOCKED",
            )


if __name__ == "__main__":
    unittest.main()
