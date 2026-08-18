import csv
import tempfile
import unittest
from pathlib import Path

from engine.dry_run_executor import execute_dry_run


class DryRunExecutorTests(unittest.TestCase):
    def write(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_complete_contract_chain_reaches_live_preflight_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plans = root / "plans.csv"
            pressures = root / "pressure.csv"
            couplings = root / "coupling.csv"

            self.write(plans, [{
                "plan_id": "PLAN-1",
                "attack_surface": "load",
                "recovery_mode": "DETACHED_WORKTREE",
                "execution_authorized": "true",
            }])

            self.write(pressures, [{
                "contract_id": "PRESSURE-1",
                "plan_id": "PLAN-1",
                "attack_surface": "load",
                "pressure_execution_authorized": "false",
            }])

            self.write(couplings, [{
                "coupling_id": "COUPLING-1",
                "pressure_contract_id": "PRESSURE-1",
                "attack_surface": "load",
                "coupling_proven": "false",
            }])

            results = execute_dry_run(plans, pressures, couplings)

            self.assertEqual(len(results), 1)
            self.assertEqual(
                results[0].dry_run_result,
                "READY_FOR_LIVE_PREFLIGHT",
            )
            self.assertFalse(results[0].live_execution_authorized)


if __name__ == "__main__":
    unittest.main()
