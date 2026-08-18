import tempfile
import unittest
from pathlib import Path

from engine.injector_discovery import discover_file


class InjectorDiscoveryTests(unittest.TestCase):
    def discover(self, text, terms):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.py"
            path.write_text(text, encoding="utf-8")
            return discover_file(path, terms)

    def test_snake_case_identifier_detects_component(self):
        terms, lines = self.discover(
            "if token_revoked:\\n    return False\\n",
            ("token", "revoked"),
        )
        self.assertIn("token", terms)
        self.assertIn("revoked", terms)
        self.assertGreaterEqual(lines, 1)

    def test_hyphenated_identifier_detects_component(self):
        terms, _ = self.discover(
            "authority-conflict",
            ("authority", "conflict"),
        )
        self.assertIn("authority", terms)

    def test_dotted_identifier_detects_component(self):
        terms, _ = self.discover(
            "state.version",
            ("version",),
        )
        self.assertIn("version", terms)

    def test_plain_identifier_detects_exact_term(self):
        terms, _ = self.discover(
            "revoked = True",
            ("revoked",),
        )
        self.assertIn("revoked", terms)

    def test_longer_alphanumeric_word_does_not_false_match(self):
        terms, _ = self.discover(
            "revokedness = True",
            ("revoked",),
        )
        self.assertNotIn("revoked", terms)

    def test_missing_file_returns_no_carrier(self):
        terms, lines = discover_file(
            Path("definitely-not-present"),
            ("stale",),
        )
        self.assertEqual(terms, tuple())
        self.assertEqual(lines, 0)


if __name__ == "__main__":
    unittest.main()
