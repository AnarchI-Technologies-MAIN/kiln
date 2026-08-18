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
