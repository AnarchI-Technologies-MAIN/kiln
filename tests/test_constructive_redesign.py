import tempfile
import unittest
from pathlib import Path

from engine.constructive_redesign import (
    artifact_hash,
    stage_artifact,
)


class ConstructiveRedesignTests(unittest.TestCase):

    def test_staging_preserves_artifact_bytes_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repair.py"
            staging = root / "kiln-staging"

            source.write_text(
                "value = 42\n",
                encoding="utf-8",
            )

            before = artifact_hash(
                source
            )

            result = stage_artifact(
                source,
                staging,
                "fracture:KILN-FRACTURE-TEST",
            )

            staged = Path(
                result.staged_path
            )

            self.assertTrue(
                staged.exists()
            )

            self.assertEqual(
                before,
                artifact_hash(staged),
            )

            self.assertEqual(
                result.provenance_ref,
                "fracture:KILN-FRACTURE-TEST",
            )

            self.assertEqual(
                result.disposition,
                "STAGED_FOR_ADJUDICATION",
            )

    def test_candidate_identity_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repair.py"
            staging = root / "kiln-staging"

            source.write_text(
                "value = 42\n",
                encoding="utf-8",
            )

            first = stage_artifact(
                source,
                staging,
                "fracture:KILN-FRACTURE-TEST",
            )

            second = stage_artifact(
                source,
                staging,
                "fracture:KILN-FRACTURE-TEST",
            )

            self.assertEqual(
                first.candidate_id,
                second.candidate_id,
            )


    def test_proven_improvement_becomes_promotion_eligible(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            adjudicate_redesign,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repair.py"
            staging = root / "kiln-staging"

            source.write_text(
                "value = 42\n",
                encoding="utf-8",
            )

            artifact = stage_artifact(
                source,
                staging,
                "fracture:KILN-FRACTURE-TEST",
            )

            decision = adjudicate_redesign(
                artifact,
                baseline_preserved=True,
                fracture_mitigated=True,
            )

            self.assertTrue(
                decision.promotion_eligible
            )

            self.assertEqual(
                decision.disposition,
                "PROMOTION_ELIGIBLE",
            )

    def test_regression_blocks_promotion(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            adjudicate_redesign,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repair.py"
            staging = root / "kiln-staging"

            source.write_text(
                "value = 42\n",
                encoding="utf-8",
            )

            artifact = stage_artifact(
                source,
                staging,
                "fracture:KILN-FRACTURE-TEST",
            )

            decision = adjudicate_redesign(
                artifact,
                baseline_preserved=False,
                fracture_mitigated=True,
            )

            self.assertFalse(
                decision.promotion_eligible
            )

            self.assertIn(
                "BASELINE_REGRESSION",
                decision.failed_gates,
            )

    def test_clean_staged_artifact_passes_contamination_gate(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            scan_staged_artifact,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repair.py"
            staging = root / "stage"

            source.write_text(
                "value = 42\n",
                encoding="utf-8",
            )

            artifact = stage_artifact(
                source,
                staging,
                "fracture:TEST",
            )

            scan = scan_staged_artifact(
                artifact
            )

            self.assertTrue(
                scan.clean
            )

            self.assertEqual(
                scan.disposition,
                "PROMOTION_CONTAMINATION_CLEAR",
            )

    def test_secret_pattern_blocks_promotion(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            scan_staged_artifact,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "config.txt"
            staging = root / "stage"

            source.write_text(
                "STRIPE_SECRET_KEY=should-not-enter-history\n",
                encoding="utf-8",
            )

            artifact = stage_artifact(
                source,
                staging,
                "fracture:TEST",
            )

            scan = scan_staged_artifact(
                artifact
            )

            self.assertFalse(
                scan.clean
            )

            self.assertIn(
                "SECRET_PATTERN_DETECTED",
                scan.findings,
            )

    def test_approved_clean_candidate_passes_promotion_preflight(self):
        import subprocess
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            adjudicate_redesign,
            preflight_promotion,
            scan_staged_artifact,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()

            subprocess.run(["git","init","-q",str(repo)],check=True)
            subprocess.run(["git","-C",str(repo),"config","user.email","kiln@example.invalid"],check=True)
            subprocess.run(["git","-C",str(repo),"config","user.name","Kiln Test"],check=True)

            source = repo / "repair.py"
            source.write_text("value = 1\n",encoding="utf-8")

            subprocess.run(["git","-C",str(repo),"add","repair.py"],check=True)
            subprocess.run(["git","-C",str(repo),"commit","-q","-m","baseline"],check=True)

            head = subprocess.check_output(
                ["git","-C",str(repo),"rev-parse","HEAD"],
                text=True,
            ).strip()

            candidate = root / "candidate.py"
            candidate.write_text("value = 2\n",encoding="utf-8")

            artifact = stage_artifact(
                candidate,
                root / "stage",
                "fracture:TEST",
            )

            adjudication = adjudicate_redesign(
                artifact,
                baseline_preserved=True,
                fracture_mitigated=True,
            )

            scan = scan_staged_artifact(artifact)

            result = preflight_promotion(
                artifact,
                adjudication,
                scan,
                repo,
                "repair.py",
                head,
                approved=True,
                branch_name=(
                    "kiln/staging-adjudication/test-candidate"
                ),
            )

            self.assertTrue(result.promotion_authorized)
            self.assertEqual(result.disposition,"PROMOTION_AUTHORIZED")

    def test_head_drift_blocks_promotion(self):
        import subprocess
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            adjudicate_redesign,
            preflight_promotion,
            scan_staged_artifact,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()

            subprocess.run(["git","init","-q",str(repo)],check=True)
            subprocess.run(["git","-C",str(repo),"config","user.email","kiln@example.invalid"],check=True)
            subprocess.run(["git","-C",str(repo),"config","user.name","Kiln Test"],check=True)

            source = repo / "repair.py"
            source.write_text("value = 1\n",encoding="utf-8")
            subprocess.run(["git","-C",str(repo),"add","repair.py"],check=True)
            subprocess.run(["git","-C",str(repo),"commit","-q","-m","baseline"],check=True)

            old_head = subprocess.check_output(
                ["git","-C",str(repo),"rev-parse","HEAD"],
                text=True,
            ).strip()

            source.write_text("value = 3\n",encoding="utf-8")
            subprocess.run(["git","-C",str(repo),"add","repair.py"],check=True)
            subprocess.run(["git","-C",str(repo),"commit","-q","-m","drift"],check=True)

            candidate = root / "candidate.py"
            candidate.write_text("value = 2\n",encoding="utf-8")

            artifact = stage_artifact(candidate,root / "stage","fracture:TEST")
            adjudication = adjudicate_redesign(artifact,True,True)
            scan = scan_staged_artifact(artifact)

            result = preflight_promotion(
                artifact,
                adjudication,
                scan,
                repo,
                "repair.py",
                old_head,
                approved=True,
                branch_name=(
                    "kiln/staging-adjudication/test-candidate"
                ),
            )

            self.assertFalse(result.promotion_authorized)
            self.assertIn("TARGET_HEAD_DRIFT",result.failed_gates)

    def test_improvement_with_insufficient_evidence_returns_to_fire(self):
        from engine.constructive_redesign import decide_redesign_route

        result = decide_redesign_route(
            candidate_id="KILN-REDESIGN-TEST",
            baseline_preserved=True,
            fracture_mitigated=True,
            regression_observed=False,
            evidence_sufficient=False,
            candidate_recoverable=True,
        )

        self.assertEqual(
            result.route,
            "RETURN_TO_FIRE",
        )

    def test_proven_improvement_routes_to_adjudication(self):
        from engine.constructive_redesign import decide_redesign_route

        result = decide_redesign_route(
            candidate_id="KILN-REDESIGN-TEST",
            baseline_preserved=True,
            fracture_mitigated=True,
            regression_observed=False,
            evidence_sufficient=True,
            candidate_recoverable=True,
        )

        self.assertEqual(
            result.route,
            "STAGE_FOR_ADJUDICATION",
        )

    def test_regression_routes_to_soft_rollback(self):
        from engine.constructive_redesign import decide_redesign_route

        result = decide_redesign_route(
            candidate_id="KILN-REDESIGN-TEST",
            baseline_preserved=False,
            fracture_mitigated=True,
            regression_observed=True,
            evidence_sufficient=False,
            candidate_recoverable=True,
        )

        self.assertEqual(
            result.route,
            "SOFT_ROLLBACK",
        )

    def test_unrecoverable_candidate_routes_to_hard_rollback(self):
        from engine.constructive_redesign import decide_redesign_route

        result = decide_redesign_route(
            candidate_id="KILN-REDESIGN-TEST",
            baseline_preserved=False,
            fracture_mitigated=False,
            regression_observed=True,
            evidence_sufficient=False,
            candidate_recoverable=False,
        )

        self.assertEqual(
            result.route,
            "HARD_ROLLBACK",
        )

    def test_soft_rollback_restores_last_good_and_preserves_failure(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import rollback_artifact

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            active = root / "active.py"
            soft = root / "soft.py"
            hard = root / "hard.py"
            evidence = root / "evidence"

            active.write_text("value = 3\n",encoding="utf-8")
            soft.write_text("value = 2\n",encoding="utf-8")
            hard.write_text("value = 1\n",encoding="utf-8")

            result = rollback_artifact(
                active,
                soft,
                hard,
                evidence,
                "SOFT_ROLLBACK",
            )

            self.assertTrue(result.rollback_proven)
            self.assertEqual(
                active.read_text(encoding="utf-8"),
                "value = 2\n",
            )

            self.assertEqual(
                Path(result.evidence_path).read_text(encoding="utf-8"),
                "value = 3\n",
            )

    def test_hard_rollback_restores_baseline_and_preserves_failure(self):
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import rollback_artifact

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            active = root / "active.py"
            soft = root / "soft.py"
            hard = root / "hard.py"
            evidence = root / "evidence"

            active.write_text("value = 9\n",encoding="utf-8")
            soft.write_text("value = 2\n",encoding="utf-8")
            hard.write_text("value = 1\n",encoding="utf-8")

            result = rollback_artifact(
                active,
                soft,
                hard,
                evidence,
                "HARD_ROLLBACK",
            )

            self.assertTrue(result.rollback_proven)
            self.assertEqual(
                active.read_text(encoding="utf-8"),
                "value = 1\n",
            )

            self.assertEqual(
                Path(result.evidence_path).read_text(encoding="utf-8"),
                "value = 9\n",
            )

    def test_proven_improvement_stages_without_mutating_source_branch(self):
        import subprocess
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            adjudicate_redesign,
            execute_promotion,
            preflight_promotion,
            scan_staged_artifact,
            stage_artifact,
        )

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            repo=root/"repo"
            remote=root/"remote.git"

            subprocess.run(
                ["git","init","-q",str(repo)],
                check=True,
            )

            subprocess.run(
                ["git","init","--bare","-q",str(remote)],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"config","user.email","kiln@example.invalid"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"config","user.name","Kiln Test"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"remote","add","origin",str(remote)],
                check=True,
            )

            original=repo/"repair.py"
            original.write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["git","-C",str(repo),"add","repair.py"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(repo),"commit","-q","-m","baseline"],
                check=True,
            )

            head=subprocess.check_output(
                ["git","-C",str(repo),"rev-parse","HEAD"],
                text=True,
            ).strip()

            candidate=root/"candidate.py"
            candidate.write_text(
                "value = 2\n",
                encoding="utf-8",
            )

            artifact=stage_artifact(
                candidate,
                root/"stage",
                "fracture:TEST",
            )

            adjudication=adjudicate_redesign(
                artifact,
                True,
                True,
            )

            contamination=scan_staged_artifact(
                artifact
            )

            preflight=preflight_promotion(
                artifact,
                adjudication,
                contamination,
                repo,
                "repair.py",
                head,
                True,
                "kiln/staging-adjudication/test-candidate",
            )

            result=execute_promotion(
                artifact,
                preflight,
                repo,
                "origin",
                "kiln/staging-adjudication/test-candidate",
                "kiln: proven redesign",
            )

            self.assertTrue(
                result.pushed
            )

            self.assertTrue(
                result.remote_verified
            )

            self.assertEqual(
                result.commit_hash,
                result.remote_commit,
            )

            self.assertEqual(
                result.disposition,
                "ADJUDICATION_BRANCH_VERIFIED",
            )

            self.assertTrue(
                result.human_adjudication_required
            )

            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    text=True,
                ).strip(),
                head,
            )

            self.assertEqual(
                original.read_text(encoding="utf-8"),
                "value = 1\n",
            )

            main_remote = subprocess.run(
                [
                    "git", "-C", str(repo), "ls-remote", "origin",
                    "refs/heads/main",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(main_remote.stdout.strip(), "")

    def test_default_branch_is_rejected_before_staging(self):
        from engine.constructive_redesign import (
            adjudication_branch_failures,
        )

        self.assertIn(
            "ADJUDICATION_BRANCH_REQUIRED",
            adjudication_branch_failures("main"),
        )

        self.assertEqual(
            adjudication_branch_failures(
                "kiln/staging-adjudication/proven-candidate"
            ),
            (),
        )

        self.assertIn(
            "ADJUDICATION_BRANCH_INVALID",
            adjudication_branch_failures(
                "kiln/staging-adjudication/a//b"
            ),
        )

    def test_verified_promotion_removes_only_promoted_candidate(self):
        import csv
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            PromotionResult,
            close_promoted_candidate,
            stage_artifact,
            write_registry,
        )

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            registry=root/"registry.csv"

            first_source=root/"first.py"
            second_source=root/"second.py"

            first_source.write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            second_source.write_text(
                "value = 2\n",
                encoding="utf-8",
            )

            first=stage_artifact(
                first_source,
                root/"stage",
                "fracture:FIRST",
            )

            second=stage_artifact(
                second_source,
                root/"stage",
                "fracture:SECOND",
            )

            artifacts=(first,second)

            write_registry(
                registry,
                artifacts,
            )

            promotion=PromotionResult(
                candidate_id=first.candidate_id,
                commit_hash="abc123",
                remote_commit="abc123",
                branch_name="kiln/staging-adjudication/merged",
                pushed=True,
                remote_verified=True,
                human_adjudication_required=False,
                disposition="PROMOTION_VERIFIED",
            )

            remaining=close_promoted_candidate(
                registry,
                artifacts,
                promotion,
            )

            self.assertEqual(
                remaining,
                (second,),
            )

            with registry.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows=list(
                    csv.DictReader(handle)
                )

            self.assertEqual(
                len(rows),
                1,
            )

            self.assertEqual(
                rows[0]["candidate_id"],
                second.candidate_id,
            )

    def test_unverified_promotion_preserves_registry(self):
        import csv
        import tempfile
        from pathlib import Path

        from engine.constructive_redesign import (
            PromotionResult,
            close_promoted_candidate,
            stage_artifact,
            write_registry,
        )

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            registry=root/"registry.csv"

            source=root/"candidate.py"

            source.write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            artifact=stage_artifact(
                source,
                root/"stage",
                "fracture:TEST",
            )

            artifacts=(artifact,)

            write_registry(
                registry,
                artifacts,
            )

            promotion=PromotionResult(
                candidate_id=artifact.candidate_id,
                commit_hash="abc123",
                remote_commit="",
                branch_name="kiln/staging-adjudication/unverified",
                pushed=False,
                remote_verified=False,
                human_adjudication_required=True,
                disposition="ADJUDICATION_PUSH_FAILED",
            )

            remaining=close_promoted_candidate(
                registry,
                artifacts,
                promotion,
            )

            self.assertEqual(
                remaining,
                artifacts,
            )

            with registry.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows=list(
                    csv.DictReader(handle)
                )

            self.assertEqual(
                len(rows),
                1,
            )

            self.assertEqual(
                rows[0]["candidate_id"],
                artifact.candidate_id,
            )

if __name__ == "__main__":
    unittest.main()
