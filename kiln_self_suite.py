from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class KilnSelfSuiteTests(unittest.TestCase):

    def test_complete_kiln_suite(self):
        root = Path(__file__).resolve().parent

        result = subprocess.run(
            [
                sys.executable,
                "-W",
                "error::ResourceWarning",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
            ],
            cwd=str(root),
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            "canonical Kiln test suite failed",
        )


if __name__ == "__main__":
    unittest.main()
