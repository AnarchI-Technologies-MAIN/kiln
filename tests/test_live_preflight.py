import tempfile
import unittest
from pathlib import Path

from engine.live_preflight import SUPPORTED_RUNNERS


class LivePreflightTests(unittest.TestCase):
    def test_supported_runner_set_is_explicit(self):
        self.assertEqual(
            SUPPORTED_RUNNERS,
            {"python-unittest", "pytest", "pytest-compatible"},
        )

    def test_runner_vocabulary_does_not_accept_unknown_values(self):
        self.assertNotIn("invented-runner", SUPPORTED_RUNNERS)


if __name__ == "__main__":
    unittest.main()
