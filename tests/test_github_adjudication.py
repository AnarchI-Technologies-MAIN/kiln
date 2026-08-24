import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.github_adjudication import (
    github_repository_from_remote,
    publish_github_adjudication,
)


class GitHubAdjudicationTests(unittest.TestCase):
    @patch("engine.github_adjudication.subprocess.run")
    def test_repository_is_inferred_from_https_remote(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "https://github.com/AnarchI-Technologies-MAIN/"
                "kiln.git\n"
            ),
            stderr="",
        )

        self.assertEqual(
            github_repository_from_remote(Path("."), "origin"),
            "AnarchI-Technologies-MAIN/kiln",
        )

    @patch("engine.github_adjudication.subprocess.run")
    def test_verified_branch_creates_draft_then_reignites(self, run):
        run.side_effect = (
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/example/project/pull/7\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
        )

        result = publish_github_adjudication(
            target_repo=Path("."),
            remote_name="origin",
            branch_name=(
                "kiln/staging-adjudication/proven-candidate"
            ),
            base_branch="main",
            commit_hash="a" * 40,
            title="kiln: proven improvement",
            body="Human adjudication required.",
            repository="example/project",
        )

        self.assertTrue(result.draft_pr_created)
        self.assertTrue(result.cycle_reignited)
        self.assertEqual(
            result.disposition,
            "HUMAN_ADJUDICATION_REQUIRED",
        )
        self.assertIn("--draft", run.call_args_list[0].args[0])
        self.assertIn(
            "event_type=kiln_staged_adjudication",
            run.call_args_list[1].args[0],
        )

    @patch("engine.github_adjudication.subprocess.run")
    def test_failed_draft_pr_does_not_dispatch(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="not allowed",
        )

        result = publish_github_adjudication(
            target_repo=Path("."),
            remote_name="origin",
            branch_name=(
                "kiln/staging-adjudication/proven-candidate"
            ),
            base_branch="main",
            commit_hash="b" * 40,
            title="kiln: proven improvement",
            body="Human adjudication required.",
            repository="example/project",
        )

        self.assertFalse(result.draft_pr_created)
        self.assertFalse(result.cycle_reignited)
        self.assertEqual(run.call_count, 1)

    def test_non_adjudication_head_is_rejected(self):
        with self.assertRaises(RuntimeError):
            publish_github_adjudication(
                target_repo=Path("."),
                remote_name="origin",
                branch_name="main",
                base_branch="main",
                commit_hash="c" * 40,
                title="unsafe",
                body="unsafe",
                repository="example/project",
            )


if __name__ == "__main__":
    unittest.main()
