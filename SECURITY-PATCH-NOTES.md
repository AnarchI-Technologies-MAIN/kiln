# Security Patch: Isolation Boundary Mitigation

## Overview

This patch addresses a security finding regarding insufficient isolation boundaries in Kiln's code execution paths. The issue identified that detached Git worktrees and temporary directories are not OS-level security boundaries, and repository-controlled code can access the host system.

## Changes Made

### 1. New Module: `engine/isolation_boundary.py`

Created a new module providing:

- **Security warnings**: Runtime warnings about insufficient isolation
- **Environment sanitization**: Filtering of sensitive environment variables
- **Path validation**: Prevention of path traversal attacks
- **Documentation**: Inline documentation of security implications

Key functions:
- `warn_insufficient_isolation()`: Emits security warnings
- `sanitize_environment()`: Filters sensitive environment variables
- `validate_execution_path()`: Validates execution paths
- `get_isolation_recommendations()`: Provides isolation guidance

### 2. Updated Execution Modules

Modified the following modules to use isolation boundary utilities:

#### `engine/baseline_executor.py`
- Added security warning before baseline test execution
- Replaced `os.environ.copy()` with `sanitize_environment()`
- Filters sensitive credentials from environment

#### `engine/mutation_adapters.py`
- Added security warnings for all execution paths:
  - WSL2 shell test execution
  - API service test execution
  - Adapter test execution
- Replaced `os.environ` usage with `sanitize_environment()`

#### `engine/sandbox_execution.py`
- Added security warning in `materialize()` method
- Documents that "sandboxes" are not security boundaries

#### `engine/environment_reconstruction.py`
- Added security warnings for all reconstruction functions:
  - Python reconstruction
  - JavaScript reconstruction
  - PowerShell reconstruction
- Replaced environment copying with `sanitize_environment()`

### 3. Documentation

#### `docs/SECURITY-ISOLATION-BOUNDARIES.md`

Comprehensive security documentation covering:
- Critical security warnings
- Affected components
- Current mitigations and their limitations
- Recommendations for secure deployment
- OS-level isolation options (containers, VMs, MAC, namespaces)
- Configuration options
- Future improvements

### 4. Tests

#### `tests/test_isolation_boundary.py`

Unit tests for isolation boundary utilities:
- Environment variable sanitization
- Path validation
- Security warning emission

## Security Mitigations Implemented

### 1. Environment Variable Sanitization

Filters sensitive environment variables before passing to subprocess execution:

```python
# Before
env = os.environ.copy()

# After
env = sanitize_environment(preserve_keys={"PYTHONPATH"})
```

Filtered patterns include:
- Credentials (key, token, secret, password)
- Cloud provider credentials (AWS, Azure, GCP)
- API keys and authentication tokens
- Private keys

### 2. Security Warnings

Runtime warnings alert operators when executing repository-controlled code:

```python
warn_insufficient_isolation("Baseline test execution")
```

Warnings include:
- Clear statement that worktrees are not security boundaries
- List of capabilities malicious code retains
- Recommendation to use OS-level isolation

### 3. Path Validation

Validates execution paths to prevent traversal:

```python
validated = validate_execution_path(path, allowed_root)
```

## Limitations

**Important**: These mitigations are **defense-in-depth** measures only. They do NOT provide complete security isolation.

The mitigations do NOT prevent:
- Filesystem access via absolute paths
- Network access to local or remote services
- Process spawning and privilege escalation
- System call execution
- Access to credentials stored in files or services
- Resource exhaustion attacks

## Recommendations

### For Trusted Repositories Only

The safest approach is to only execute Kiln against repositories you fully trust and control.

### For Untrusted Code

Implement OS-level isolation using one of:

1. **Containers**: Docker, Podman with security restrictions
2. **Virtual Machines**: Firecracker, QEMU/KVM, cloud VMs
3. **Mandatory Access Control**: SELinux, AppArmor, seccomp
4. **User Namespaces**: unshare, bubblewrap
5. **Platform Sandboxing**: Windows Sandbox, macOS sandbox-exec

See `docs/SECURITY-ISOLATION-BOUNDARIES.md` for detailed guidance.

## Testing

Run the new tests:

```bash
python -m unittest tests.test_isolation_boundary
```

Run all tests to ensure no regressions:

```bash
python -m unittest discover tests
```

## Configuration

### Disabling Warnings

If you have implemented proper OS-level isolation:

```python
from engine.isolation_boundary import ENABLE_SECURITY_WARNINGS

ENABLE_SECURITY_WARNINGS = False
```

**Warning**: Only disable warnings with proper isolation in place.

## Migration Guide

No breaking changes. The patch is backward compatible:

- Existing code continues to work
- Security warnings are emitted by default
- Environment sanitization is automatic
- No configuration changes required

## Future Work

Potential enhancements:

1. Built-in container support (Docker/Podman integration)
2. Configurable isolation backends
3. Resource limits (CPU, memory, I/O quotas)
4. Network policy enforcement
5. Filesystem restrictions
6. Automatic privilege dropping

## References

- Original security finding: Repository-controlled code executes outside a real isolation boundary
- Related files: `baseline_executor.py`, `mutation_adapters.py`, `sandbox_execution.py`, `environment_reconstruction.py`
- Documentation: `docs/SECURITY-ISOLATION-BOUNDARIES.md`

## Contact

For security concerns or questions, please contact the security team.
