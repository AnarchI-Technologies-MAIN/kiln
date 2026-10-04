# Security Patch Summary

## Issue
Repository-controlled code executes outside a real isolation boundary. Detached Git worktrees and temporary directories are not OS-level security boundaries.

## Root Cause
Kiln executes repository-controlled tests, mutations, API services, and contracts using `subprocess.run()` with:
- Working directory set to worktree/temp directory
- Full environment inherited via `os.environ.copy()`
- No OS-level privilege, filesystem, network, or syscall restrictions

This allows malicious repository code to:
- Access entire filesystem via absolute paths
- Access network resources
- Read inherited credentials from environment
- Spawn arbitrary processes
- Modify files outside execution directory

## Solution Implemented

### Defense-in-Depth Mitigations

1. **Environment Variable Sanitization**
   - Filter sensitive credentials before subprocess execution
   - Remove tokens, keys, passwords, cloud credentials
   - Preserve only safe variables (PATH, PYTHONPATH, etc.)

2. **Security Warnings**
   - Emit runtime warnings when executing repository code
   - Alert operators to security implications
   - Document that worktrees are not security boundaries

3. **Path Validation**
   - Validate execution paths to prevent traversal
   - Ensure paths stay within allowed roots

4. **Comprehensive Documentation**
   - Security notice document with isolation recommendations
   - Inline code documentation
   - Configuration guidance

### Files Modified

1. **New Files**
   - `engine/isolation_boundary.py` - Core security utilities
   - `docs/SECURITY-ISOLATION-BOUNDARIES.md` - Security documentation
   - `tests/test_isolation_boundary.py` - Unit tests
   - `SECURITY-PATCH-NOTES.md` - Patch documentation

2. **Modified Files**
   - `engine/baseline_executor.py` - Added warnings and sanitization
   - `engine/mutation_adapters.py` - Added warnings and sanitization
   - `engine/sandbox_execution.py` - Added warnings
   - `engine/environment_reconstruction.py` - Added warnings and sanitization

## Important Limitations

**These mitigations are defense-in-depth only. They do NOT provide complete security isolation.**

The mitigations do NOT prevent:
- Filesystem access via absolute paths
- Network access
- Process spawning
- System calls
- Credential access via files/services
- Resource exhaustion

## Recommendations

### For Production Use

1. **Only execute trusted repositories** - Safest approach
2. **Implement OS-level isolation** - Use containers, VMs, or MAC systems
3. **Network isolation** - Disable or restrict network access
4. **Credential management** - Never pass credentials to Kiln
5. **Monitoring** - Log and audit all executions

### OS-Level Isolation Options

- **Containers**: Docker, Podman with security restrictions
- **VMs**: Firecracker, QEMU/KVM, cloud VMs
- **MAC**: SELinux, AppArmor, seccomp
- **Namespaces**: unshare, bubblewrap
- **Platform**: Windows Sandbox, macOS sandbox-exec

See `docs/SECURITY-ISOLATION-BOUNDARIES.md` for detailed guidance.

## Testing

All changes are backward compatible. No breaking changes.

Run tests:
```bash
python -m unittest tests.test_isolation_boundary
python -m unittest discover tests
```

## Configuration

Warnings enabled by default. To disable (only with proper isolation):
```python
from engine.isolation_boundary import ENABLE_SECURITY_WARNINGS
ENABLE_SECURITY_WARNINGS = False
```

## Conclusion

This patch implements defense-in-depth mitigations and comprehensive documentation for the isolation boundary issue. While these measures improve security posture, **proper OS-level isolation is required for executing untrusted code**.

The patch:
- ✅ Filters sensitive environment variables
- ✅ Emits security warnings
- ✅ Validates execution paths
- ✅ Documents security implications
- ✅ Provides isolation recommendations
- ✅ Maintains backward compatibility
- ✅ Includes comprehensive tests

For complete security, implement OS-level isolation as documented.
