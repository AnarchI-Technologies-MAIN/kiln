import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.mutation_executor import (
    apply_mutation,
    discover_python_mutations,
)
from engine.specimen_membership import (
    SpecimenMembershipPolicy,
    normalize_specimen_path,
)


class MutationExecutorTests(unittest.TestCase):

    def initialize_git(
        self,
        root: Path,
    ):
        subprocess.run(
            ["git", "init", "-q", str(root)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
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
                str(root),
                "config",
                "user.name",
                "Kiln Test",
            ],
            check=True,
        )

    def commit_file(
        self,
        root: Path,
        relative_path: str,
    ):
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "add",
                relative_path,
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "commit",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
        )

    def test_discovery_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            source=root/"module.py"

            source.write_text(
                "FLAG = True\n"
                "VALUE = 1 + 1\n",
                encoding="utf-8",
            )

            first=discover_python_mutations(
                root
            )

            second=discover_python_mutations(
                root
            )

            self.assertEqual(
                first,
                second,
            )

            self.assertGreater(
                len(first),
                0,
            )

    def test_identity_survives_line_ending_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"module.py"

            source.write_bytes(
                b"FLAG = True\r\n"
            )

            crlf=discover_python_mutations(
                root
            )[0]

            source.write_bytes(
                b"FLAG = True\n"
            )

            lf=discover_python_mutations(
                root
            )[0]

            self.assertEqual(
                crlf.mutation_id,
                lf.mutation_id,
            )

            self.assertEqual(
                crlf.canonical_source_hash,
                lf.canonical_source_hash,
            )

            self.assertNotEqual(
                crlf.source_hash,
                lf.source_hash,
            )

    def test_explicit_policy_ignores_untracked_python_debris(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            self.initialize_git(
                root
            )

            tracked=root/"app.py"

            tracked.write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            self.commit_file(
                root,
                "app.py",
            )

            debris=root/"training"
            debris.mkdir()

            (debris/"broken.py").write_text(
                "value = \\\\ garbage\n",
                encoding="utf-8",
            )

            candidates=discover_python_mutations(
                root
            )

            self.assertGreater(
                len(candidates),
                0,
            )

            self.assertTrue(
                all(
                    item.relative_path == "app.py"
                    for item in candidates
                )
            )

    def test_tracked_and_untracked_content_have_same_membership(self):
        with tempfile.TemporaryDirectory() as tracked_temp, \
                tempfile.TemporaryDirectory() as untracked_temp:
            tracked=Path(tracked_temp)
            untracked=Path(untracked_temp)

            self.initialize_git(
                tracked
            )
            self.initialize_git(
                untracked
            )

            for root in (tracked, untracked):
                (root/"module.py").write_text(
                    "FLAG = True\n",
                    encoding="utf-8",
                )

            self.commit_file(
                tracked,
                "module.py",
            )

            self.assertEqual(
                discover_python_mutations(
                    tracked
                ),
                discover_python_mutations(
                    untracked
                ),
            )

    def test_tracked_modified_and_clean_content_have_same_membership(self):
        with tempfile.TemporaryDirectory() as clean_temp, \
                tempfile.TemporaryDirectory() as modified_temp:
            clean=Path(clean_temp)
            modified=Path(modified_temp)

            self.initialize_git(
                clean
            )
            self.initialize_git(
                modified
            )

            (clean/"module.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )
            self.commit_file(
                clean,
                "module.py",
            )

            (modified/"module.py").write_text(
                "FLAG = False\n",
                encoding="utf-8",
            )
            self.commit_file(
                modified,
                "module.py",
            )
            (modified/"module.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            self.assertEqual(
                discover_python_mutations(
                    clean
                ),
                discover_python_mutations(
                    modified
                ),
            )

    def test_staged_and_unstaged_content_have_same_membership(self):
        with tempfile.TemporaryDirectory() as staged_temp, \
                tempfile.TemporaryDirectory() as unstaged_temp:
            staged=Path(staged_temp)
            unstaged=Path(unstaged_temp)

            self.initialize_git(
                staged
            )
            self.initialize_git(
                unstaged
            )

            for root in (staged, unstaged):
                (root/"module.py").write_text(
                    "FLAG = True\n",
                    encoding="utf-8",
                )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(staged),
                    "add",
                    "module.py",
                ],
                check=True,
            )

            self.assertEqual(
                discover_python_mutations(
                    staged
                ),
                discover_python_mutations(
                    unstaged
                ),
            )

    def test_git_and_plain_tree_have_same_membership(self):
        with tempfile.TemporaryDirectory() as git_temp, \
                tempfile.TemporaryDirectory() as plain_temp:
            git_root=Path(git_temp)
            plain_root=Path(plain_temp)

            (git_root/"module.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )
            (plain_root/"module.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )
            self.initialize_git(
                git_root
            )

            self.assertEqual(
                discover_python_mutations(
                    git_root
                ),
                discover_python_mutations(
                    plain_root
                ),
            )

    def test_explicit_exclusions_override_inclusion_exceptions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"module.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            excluded_directories = (
                ".venv",
                "__pycache__",
                "build",
                "node_modules",
                "proof-output",
                "sandboxes",
                "sessions",
                "temp",
                "training",
                "vendor",
            )

            for name in excluded_directories:
                directory=root/name
                directory.mkdir()
                (directory/"generated.py").write_text(
                    "FLAG = True\n",
                    encoding="utf-8",
                )

            defaults=discover_python_mutations(
                root
            )

            self.assertEqual(
                {
                    item.relative_path
                    for item in defaults
                },
                {"module.py"},
            )

            (root/"vendor"/"allowed.py").write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )
            policy=SpecimenMembershipPolicy(
                excluded_relative_paths=(
                    r"vendor\generated.py",
                ),
                included_relative_paths=(
                    r"vendor",
                ),
            )
            selected=discover_python_mutations(
                root,
                policy,
            )

            self.assertEqual(
                {
                    item.relative_path
                    for item in selected
                },
                {
                    "module.py",
                    "vendor/allowed.py",
                },
            )

    def test_windows_membership_paths_normalize_to_posix(self):
        self.assertEqual(
            normalize_specimen_path(
                r"engine\nested\module.py"
            ),
            "engine/nested/module.py",
        )

        policy=SpecimenMembershipPolicy(
            excluded_relative_paths=(
                r"private\generated.py",
            ),
        )

        self.assertFalse(
            policy.includes(
                "private/generated.py"
            )
        )

    def test_candidate_id_round_trips_from_discovery_to_injection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"module.py"
            source.write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            advertised=discover_python_mutations(
                root
            )[0]
            by_id = {
                item.mutation_id: item
                for item in discover_python_mutations(
                    root
                )
            }
            resolved=by_id[
                advertised.mutation_id
            ]
            application=apply_mutation(
                root,
                resolved,
            )

            self.assertEqual(
                application.mutation_id,
                advertised.mutation_id,
            )
            self.assertEqual(
                source.read_text(
                    encoding="utf-8"
                ),
                "FLAG = False\n",
            )

    def test_mutation_changes_only_specimen_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            source=root/"module.py"

            source.write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            candidate=discover_python_mutations(
                root
            )[0]

            before=source.read_text(
                encoding="utf-8"
            )

            result=apply_mutation(
                root,
                candidate,
            )

            after=source.read_text(
                encoding="utf-8"
            )

            self.assertTrue(
                result.applied
            )

            self.assertNotEqual(
                before,
                after,
            )


if __name__ == "__main__":
    unittest.main()
