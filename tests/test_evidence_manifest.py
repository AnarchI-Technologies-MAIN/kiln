import csv
import tempfile
import unittest
from pathlib import Path

from engine.evidence_manifest import build_manifest
from engine.target_intake import TargetIdentity


class EvidenceManifestTests(unittest.TestCase):

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

    def target(self):
        return TargetIdentity(
            target_id="KILN-TARGET-TEST",
            target_kind="LOCAL_GIT_REPOSITORY",
            source_location="fixture",
            repository_root="fixture",
            git_repository=True,
            source_commit="abc123",
            repository_clean=True,
            local_or_remote="LOCAL",
            language_hints=("python",),
            manifest_hints=tuple(),
            target_fingerprint="fingerprint",
            disposition="TARGET_IDENTIFIED",
        )

    def evidence(self, root):
        capability = root / "capability.csv"
        injector = root / "injector.csv"
        surface = root / "surface.csv"

        self.write(capability, [{
            "authorized_actions": "BASELINE_EXECUTION;INJECTOR_PROOF_TRIAL",
            "blocked_actions": "PRESSURE_EVIDENCE_ACCEPTED",
        }])

        self.write(injector, [{
            "plan_id": "PLAN-1",
            "authorized": "true",
        }])

        self.write(surface, [{
            "attack_surface": "filesystem-state",
            "readiness": "CONTRACT_ONLY",
        }])

        return capability, injector, surface

    def test_manifest_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = self.evidence(root)

            first = build_manifest(
                self.target(),
                *paths,
            )

            second = build_manifest(
                self.target(),
                *paths,
            )

            self.assertEqual(
                first.manifest_hash,
                second.manifest_hash,
            )

            self.assertEqual(
                first.final_disposition,
                "EVIDENCE_CLOSED",
            )

    def test_evidence_change_changes_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = self.evidence(root)

            first = build_manifest(
                self.target(),
                *paths,
            )

            with paths[0].open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write("\n")

            second = build_manifest(
                self.target(),
                *paths,
            )

            self.assertNotEqual(
                first.manifest_hash,
                second.manifest_hash,
            )

    def test_missing_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            with self.assertRaises(
                RuntimeError
            ):
                build_manifest(
                    self.target(),
                    root / "missing-a.csv",
                    root / "missing-b.csv",
                    root / "missing-c.csv",
                )


if __name__ == "__main__":
    unittest.main()
