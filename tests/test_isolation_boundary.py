"""
Tests for isolation boundary utilities.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import warnings
from pathlib import Path

from engine.isolation_boundary import (
    IsolationBoundaryWarning,
    sanitize_environment,
    validate_execution_path,
    warn_insufficient_isolation,
)


class IsolationBoundaryTests(unittest.TestCase):

    def test_sanitize_environment_filters_sensitive_keys(self):
        """Test that sensitive environment variables are filtered."""
        env = {
            "PATH": "/usr/bin",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "GITHUB_TOKEN": "token",
            "API_KEY": "key",
            "NORMAL_VAR": "value",
        }

        sanitized = sanitize_environment(env)

        # Safe keys should be preserved
        self.assertIn("PATH", sanitized)
        self.assertIn("NORMAL_VAR", sanitized)

        # Sensitive keys should be filtered
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", sanitized)
        self.assertNotIn("GITHUB_TOKEN", sanitized)
        self.assertNotIn("API_KEY", sanitized)

    def test_sanitize_environment_preserves_specified_keys(self):
        """Test that explicitly preserved keys are kept."""
        env = {
            "PATH": "/usr/bin",
            "CUSTOM_KEY": "value",
        }

        sanitized = sanitize_environment(env, preserve_keys={"CUSTOM_KEY"})

        self.assertIn("PATH", sanitized)
        self.assertIn("CUSTOM_KEY", sanitized)

    def test_sanitize_environment_case_insensitive_filtering(self):
        """Test that filtering is case-insensitive."""
        env = {
            "path": "/usr/bin",
            "api_key": "key",
            "API_TOKEN": "token",
            "Secret_Value": "secret",
        }

        sanitized = sanitize_environment(env)

        # Sensitive keys should be filtered regardless of case
        self.assertNotIn("api_key", sanitized)
        self.assertNotIn("API_TOKEN", sanitized)
        self.assertNotIn("Secret_Value", sanitized)

    def test_validate_execution_path_accepts_valid_path(self):
        """Test that valid paths within root are accepted."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subdir = root / "subdir"
            subdir.mkdir()

            validated = validate_execution_path(subdir, root)

            self.assertEqual(validated, subdir.resolve())

    def test_validate_execution_path_rejects_escaped_path(self):
        """Test that paths outside root are rejected."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()

            outside = Path(temp) / "outside"
            outside.mkdir()

            with self.assertRaises(RuntimeError) as context:
                validate_execution_path(outside, root)

            self.assertIn("escapes allowed root", str(context.exception))

    def test_validate_execution_path_rejects_traversal(self):
        """Test that path traversal attempts are rejected."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()

            traversal = root / ".." / ".." / "etc" / "passwd"

            with self.assertRaises(RuntimeError):
                validate_execution_path(traversal, root)

    def test_warn_insufficient_isolation_emits_warning(self):
        """Test that security warnings are emitted."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            warn_insufficient_isolation("test context")

            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, IsolationBoundaryWarning))
            self.assertIn("test context", str(w[0].message))
            self.assertIn("NOT a security boundary", str(w[0].message))


if __name__ == "__main__":
    unittest.main()
