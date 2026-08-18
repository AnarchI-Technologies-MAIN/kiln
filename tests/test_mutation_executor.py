import tempfile
import unittest
from pathlib import Path

from engine.mutation_executor import (
    apply_mutation,
    discover_python_mutations,
)


class MutationExecutorTests(unittest.TestCase):

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

    def test_git_discovery_ignores_untracked_python_debris(self):
        import subprocess

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)

            subprocess.run(
                ["git","init","-q",str(root)],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(root),"config","user.email","kiln@example.invalid"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(root),"config","user.name","Kiln Test"],
                check=True,
            )

            tracked=root/"app.py"

            tracked.write_text(
                "FLAG = True\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["git","-C",str(root),"add","app.py"],
                check=True,
            )

            subprocess.run(
                ["git","-C",str(root),"commit","-q","-m","baseline"],
                check=True,
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
