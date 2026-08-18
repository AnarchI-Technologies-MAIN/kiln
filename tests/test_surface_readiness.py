import csv
import tempfile
import unittest
from pathlib import Path

from engine.surface_readiness import KNOWN_SURFACES, reconcile


class SurfaceReadinessTests(unittest.TestCase):
    def write_csv(self, path, fields, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_known_surface_vocabulary_is_exact(self):
        self.assertEqual(
            KNOWN_SURFACES,
            (
                "load",
                "state-staleness",
                "authority-conflict",
                "filesystem-state",
            ),
        )

    def test_coupling_surface_is_resolved_through_pressure_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaigns = root / "campaigns.csv"
            pressures = root / "pressures.csv"
            couplings = root / "couplings.csv"

            self.write_csv(
                campaigns,
                ["attack_surface", "disposition"],
                [],
            )

            self.write_csv(
                pressures,
                ["contract_id", "attack_surface"],
                [{
                    "contract_id": "P-1",
                    "attack_surface": "state-staleness",
                }],
            )

            self.write_csv(
                couplings,
                ["pressure_contract_id", "coupling_id"],
                [{
                    "pressure_contract_id": "P-1",
                    "coupling_id": "C-1",
                }],
            )

            results = reconcile(campaigns, pressures, couplings)
            by_surface = {item.attack_surface: item for item in results}

            item = by_surface["state-staleness"]
            self.assertEqual(item.readiness, "CONTRACT_ONLY")
            self.assertTrue(item.injector_discovery_authorized)

    def test_proven_campaign_overrides_contract_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaigns = root / "campaigns.csv"
            pressures = root / "pressures.csv"
            couplings = root / "couplings.csv"

            self.write_csv(
                campaigns,
                ["attack_surface", "disposition"],
                [{
                    "attack_surface": "load",
                    "disposition": "LOAD_PRESSURE_ENVELOPE_PROVEN",
                }],
            )

            self.write_csv(
                pressures,
                ["contract_id", "attack_surface"],
                [{
                    "contract_id": "P-LOAD",
                    "attack_surface": "load",
                }],
            )

            self.write_csv(
                couplings,
                ["pressure_contract_id"],
                [{"pressure_contract_id": "P-LOAD"}],
            )

            results = reconcile(campaigns, pressures, couplings)
            by_surface = {item.attack_surface: item for item in results}

            item = by_surface["load"]
            self.assertEqual(item.readiness, "PROVEN")
            self.assertFalse(item.injector_discovery_authorized)

    def test_unknown_pressure_reference_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaigns = root / "campaigns.csv"
            pressures = root / "pressures.csv"
            couplings = root / "couplings.csv"

            self.write_csv(
                campaigns,
                ["attack_surface", "disposition"],
                [],
            )

            self.write_csv(
                pressures,
                ["contract_id", "attack_surface"],
                [{
                    "contract_id": "P-1",
                    "attack_surface": "load",
                }],
            )

            self.write_csv(
                couplings,
                ["pressure_contract_id"],
                [{"pressure_contract_id": "DOES-NOT-EXIST"}],
            )

            with self.assertRaises(RuntimeError):
                reconcile(campaigns, pressures, couplings)


if __name__ == "__main__":
    unittest.main()
