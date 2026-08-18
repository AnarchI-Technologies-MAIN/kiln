import csv
import tempfile
import unittest
from pathlib import Path

from engine.coupling_authorization import authorize_trials


class CouplingAuthorizationTests(unittest.TestCase):
    def write(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_only_proven_baseline_authorizes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline.csv"
            pressure = root / "pressure.csv"
            coupling = root / "coupling.csv"

            self.write(baseline, [{
                "plan_id": "PLAN-1",
                "disposition": "PROVEN_BASELINE",
                "pressure_eligible": "true",
            }])

            self.write(pressure, [{
                "plan_id": "PLAN-1",
                "contract_id": "PRESSURE-1",
                "attack_surface": "load",
                "pressure_execution_authorized": "false",
            }])

            self.write(coupling, [{
                "pressure_contract_id": "PRESSURE-1",
                "coupling_id": "COUPLING-1",
                "coupling_proven": "false",
            }])

            results = authorize_trials(baseline, pressure, coupling)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].authorized)
            self.assertEqual(results[0].max_trials, 1)

    def test_baseline_fracture_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline.csv"
            pressure = root / "pressure.csv"
            coupling = root / "coupling.csv"

            self.write(baseline, [{
                "plan_id": "PLAN-1",
                "disposition": "BASELINE_FRACTURE",
                "pressure_eligible": "false",
            }])

            self.write(pressure, [{
                "plan_id": "PLAN-1",
                "contract_id": "PRESSURE-1",
                "attack_surface": "load",
                "pressure_execution_authorized": "false",
            }])

            self.write(coupling, [{
                "pressure_contract_id": "PRESSURE-1",
                "coupling_id": "COUPLING-1",
                "coupling_proven": "false",
            }])

            results = authorize_trials(baseline, pressure, coupling)

            self.assertFalse(results[0].authorized)
            self.assertEqual(results[0].max_trials, 0)


    def test_unsupported_surface_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline.csv"
            pressure = root / "pressure.csv"
            coupling = root / "coupling.csv"

            self.write(baseline, [{
                "plan_id": "PLAN-1",
                "disposition": "PROVEN_BASELINE",
                "pressure_eligible": "true",
            }])

            self.write(pressure, [{
                "plan_id": "PLAN-1",
                "contract_id": "PRESSURE-1",
                "attack_surface": "authority-conflict",
                "pressure_execution_authorized": "false",
            }])

            self.write(coupling, [{
                "pressure_contract_id": "PRESSURE-1",
                "coupling_id": "COUPLING-1",
                "coupling_proven": "false",
            }])

            results = authorize_trials(baseline, pressure, coupling)

            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].authorized)
            self.assertEqual(
                results[0].disposition,
                "COUPLING_TRIAL_BLOCKED",
            )
            self.assertEqual(results[0].max_trials, 0)

if __name__ == "__main__":
    unittest.main()
