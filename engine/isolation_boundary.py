"""
Isolation boundary utilities for Kiln execution environments.

WARNING: The current implementation does NOT provide OS-level security isolation.
Detached Git worktrees and temporary directories are NOT security boundaries.

Repository-controlled code executed by Kiln can:
- Access the entire filesystem using absolute paths
- Access network resources and services
- Read inherited environment variables (including credentials)
- Spawn arbitrary child processes
- Modify files outside the execution directory
- Access local and remote services

DO NOT execute untrusted repository code without additional OS-level isolation
such as containers (Docker, Podman), VMs, or mandatory access control systems.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict
import os
import warnings

# Security warning flag - set to False to suppress warnings (not recommended)
ENABLE_SECURITY_WARNINGS = True


class IsolationBoundaryWarning(UserWarning):
    """Warning about insufficient isolation boundaries."""

    pass


def repository_path_is_absolute(value: str) -> bool:
    """Reject anchored paths from either platform, including drive-relative paths."""
    return bool(PurePosixPath(value).anchor or PureWindowsPath(value).anchor)


def warn_insufficient_isolation(context: str) -> None:
    """
    Emit a warning about insufficient isolation boundaries.

    Args:
        context: Description of the execution context (e.g., "baseline execution")
    """
    if not ENABLE_SECURITY_WARNINGS:
        return

    message = (
        f"SECURITY WARNING: {context} executes repository-controlled code "
        f"without OS-level isolation. The detached worktree or temporary "
        f"directory is NOT a security boundary. Malicious code can access "
        f"the filesystem, network, environment variables, and spawn processes. "
        f"Do not execute untrusted repositories without additional isolation "
        f"(containers, VMs, or mandatory access control)."
    )

    warnings.warn(message, IsolationBoundaryWarning, stacklevel=2)


def sanitize_environment(
    base_env: Dict[str, str] | None = None,
    preserve_keys: set[str] | None = None,
) -> Dict[str, str]:
    """
    Create a sanitized environment with sensitive variables filtered.

    This provides defense-in-depth but is NOT a complete security boundary.
    Malicious code can still access credentials through other means.

    Args:
        base_env: Base environment to sanitize (defaults to os.environ)
        preserve_keys: Additional keys to preserve beyond the safe list

    Returns:
        Sanitized environment dictionary
    """
    if base_env is None:
        base_env = dict(os.environ)

    # Keys that are generally safe to pass through
    safe_keys = {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "SYSTEMROOT",
        "WINDIR",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "COMSPEC",
        "PATHEXT",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        # Kiln-specific variables
        "KILN_HOST",
        "KILN_PORT",
    }

    if preserve_keys:
        safe_keys.update(preserve_keys)

    # Patterns of sensitive keys to filter (case-insensitive)
    sensitive_patterns = {
        "key",
        "token",
        "secret",
        "password",
        "credential",
        "auth",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "aws_",
        "azure_",
        "gcp_",
        "github_",
        "gitlab_",
    }

    sanitized = {}

    for key, value in base_env.items():
        # Preserve explicitly safe keys
        if key in safe_keys:
            sanitized[key] = value
            continue

        # Filter keys matching sensitive patterns
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in sensitive_patterns):
            continue

        # Include other keys (may still contain sensitive data)
        sanitized[key] = value

    return sanitized


def validate_execution_path(
    path: Path,
    allowed_root: Path,
) -> Path:
    """
    Validate that an execution path is within the allowed root.

    This prevents path traversal but does NOT prevent the executed code
    from accessing paths outside the root using absolute paths.

    Args:
        path: Path to validate
        allowed_root: Root directory that must contain the path

    Returns:
        Resolved path if valid

    Raises:
        RuntimeError: If path escapes the allowed root
    """
    resolved_path = Path(path).resolve()
    resolved_root = Path(allowed_root).resolve()

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise RuntimeError(f"Execution path {path} escapes allowed root {allowed_root}")

    return resolved_path


def get_isolation_recommendations() -> str:
    """
    Get recommendations for implementing proper OS-level isolation.

    Returns:
        Multi-line string with isolation recommendations
    """
    return """
ISOLATION RECOMMENDATIONS:

For proper security isolation, consider implementing one of:

1. Container-based isolation (Linux):
   - Docker with --security-opt=no-new-privileges
   - Podman with --userns=keep-id
   - systemd-nspawn with appropriate restrictions
   
2. Virtual machine isolation:
   - Firecracker microVMs
   - QEMU/KVM with minimal guest OS
   - Cloud-based ephemeral VMs
   
3. Mandatory access control:
   - SELinux with custom policy
   - AppArmor with restrictive profile
   - seccomp-bpf filters
   
4. User namespace isolation (Linux):
   - unshare with user/mount/network/PID namespaces
   - bubblewrap (bwrap) sandboxing
   
5. Platform-specific sandboxing:
   - Windows: AppContainer or Windows Sandbox
   - macOS: sandbox-exec or App Sandbox
   
Each approach requires careful configuration to balance security and functionality.
"""
