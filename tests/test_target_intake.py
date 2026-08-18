import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.target_intake import inspect_target


class TargetIntakeTests(unittest.TestCase):

    def test_local_directory_identity_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            (root / "sample.py").write_text(
                "print('kiln')\n",
                encoding="utf-8",
            )

            first = inspect_target(root)
            second = inspect_target(root)

            self.assertEqual(
                first.target_id,
                second.target_id,
            )

            self.assertEqual(
                first.target_fingerprint,
                second.target_fingerprint,
            )

            self.assertEqual(
                first.disposition,
                "TARGET_IDENTIFIED",
            )

            self.assertIn(
                "python",
                first.language_hints,
            )

    def test_local_content_change_changes_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sample.py"

            source.write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            first = inspect_target(root)

            source.write_text(
                "value = 2\n",
                encoding="utf-8",
            )

            second = inspect_target(root)

            self.assertNotEqual(
                first.target_id,
                second.target_id,
            )

    def test_dirty_git_worktree_changes_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
            )

            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "kiln@example.invalid"],
                check=True,
            )

            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Kiln Test"],
                check=True,
            )

            source = root / "sample.py"
            source.write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["git", "-C", str(root), "add", "sample.py"],
                check=True,
            )

            subprocess.run(
                ["git", "-C", str(root), "commit", "-q", "-m", "fixture"],
                check=True,
            )

            clean = inspect_target(root)

            source.write_text(
                "value = 2\n",
                encoding="utf-8",
            )

            dirty = inspect_target(root)

            self.assertEqual(
                clean.source_commit,
                dirty.source_commit,
            )

            self.assertNotEqual(
                clean.target_fingerprint,
                dirty.target_fingerprint,
            )

            self.assertNotEqual(
                clean.target_id,
                dirty.target_id,
            )

            self.assertFalse(
                dirty.repository_clean
            )
    def test_missing_target_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "missing"

            result = inspect_target(target)

            self.assertEqual(
                result.disposition,
                "TARGET_NOT_FOUND",
            )

            self.assertEqual(
                result.target_id,
                "",
            )

    def test_remote_git_acquisition_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()

            subprocess.run(
                ["git", "init", "-q", str(source)],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "config",
                    "user.email",
                    "kiln@example.invalid",
                ],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "config",
                    "user.name",
                    "Kiln Test",
                ],
                check=True,
            )

            (source / "sample.py").write_text(
                "value = 1\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "add",
                    "sample.py",
                ],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
            )

            remote = source.as_uri()

            first = inspect_target(remote)
            second = inspect_target(remote)

            self.assertEqual(
                first.disposition,
                "TARGET_IDENTIFIED",
            )

            self.assertEqual(
                first.target_kind,
                "REMOTE_GIT_REPOSITORY",
            )

            self.assertEqual(
                first.local_or_remote,
                "REMOTE",
            )

            self.assertTrue(
                first.source_commit
            )

            self.assertEqual(
                first.target_id,
                second.target_id,
            )

            self.assertEqual(
                first.source_commit,
                second.source_commit,
            )

            self.assertEqual(
                first.repository_root,
                "",
            )


if __name__ == "__main__":
    unittest.main()
