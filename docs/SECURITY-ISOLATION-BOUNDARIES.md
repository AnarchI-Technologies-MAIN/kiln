# Security Notice: Isolation Boundaries

## Critical Security Warning

**The current Kiln implementation does NOT provide OS-level security isolation for repository-controlled code execution.**

Detached Git worktrees and temporary directories are **NOT** security boundaries. They provide only logical separation of Git checkout state, not operating system security isolation.

## What This Means

When Kiln executes repository-controlled tests, mutations, API services, contracts, or reconstruction adapters, the executed code:

- **CAN** access the entire filesystem using absolute paths
- **CAN** access network resources and services (local and remote)
- **CAN** read all inherited environment variables (including credentials)
- **CAN** spawn arbitrary child processes with full privileges
- **CAN** modify files outside the execution directory
- **CAN** access local services (databases, APIs, etc.)
- **CAN** make system calls without restriction
- **INHERITS** the Kiln user's privileges and capabilities

## Affected Components

The following execution paths are affected:

1. **Baseline Execution** (`baseline_executor.py`)
   - Executes baseline tests in detached worktrees
   - No privilege restriction or filesystem isolation

2. **Mutation Testing** (`mutation_adapters.py`, `sandbox_execution.py`)
   - Python adapter test execution
   - WSL2 shell script execution
   - API service execution
   - Contract command execution
   - PowerShell script execution
   - npm script execution

3. **Environment Reconstruction** (`environment_reconstruction.py`)
   - Python reconstruction tests
   - JavaScript/TypeScript reconstruction tests
   - PowerShell reconstruction tests

## Current Mitigations

The following defense-in-depth measures have been implemented:

### 1. Environment Variable Sanitization

Sensitive environment variables are filtered before passing to subprocess execution:
- Credentials (tokens, keys, passwords)
- Cloud provider credentials (AWS, Azure, GCP)
- API keys and authentication tokens
- Private keys

**Limitation**: This does NOT prevent malicious code from accessing credentials through other means (filesystem, process inspection, network services).

### 2. Security Warnings

Runtime warnings are emitted when executing repository-controlled code to alert operators of the security implications.

**Limitation**: Warnings do not prevent exploitation, only inform operators.

### 3. Path Validation

Execution paths are validated to prevent path traversal attacks.

**Limitation**: This only prevents the Kiln code from being tricked into accessing wrong paths. It does NOT prevent executed repository code from using absolute paths.

## What These Mitigations Do NOT Prevent

The current mitigations are **defense-in-depth** measures only. They do NOT prevent:

- Filesystem access via absolute paths
- Network access to local or remote services
- Process spawning and privilege escalation
- System call execution
- Access to credentials stored in files or services
- Modification of files outside the execution directory
- Resource exhaustion attacks
- Side-channel attacks

## Recommendations for Secure Deployment

### Do NOT Execute Untrusted Repositories

The safest approach is to only execute Kiln against repositories you fully trust and control.

### Implement OS-Level Isolation

For executing untrusted or partially-trusted code, implement one of the following OS-level isolation mechanisms:

#### Option 1: Container-Based Isolation (Linux)

```bash
# Docker with security restrictions
docker run --rm \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  --network=none \
  --read-only \
  --tmpfs /tmp \
  kiln-image

# Podman with user namespaces
podman run --rm \
  --userns=keep-id \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  --network=none \
  kiln-image
```

#### Option 2: Virtual Machine Isolation

- Firecracker microVMs for lightweight isolation
- QEMU/KVM with minimal guest OS
- Cloud-based ephemeral VMs (AWS EC2, GCP Compute Engine)

#### Option 3: Mandatory Access Control

- **SELinux**: Create custom policy for Kiln execution
- **AppArmor**: Create restrictive profile
- **seccomp-bpf**: Filter system calls

#### Option 4: User Namespace Isolation (Linux)

```bash
# Using unshare
unshare --user --mount --net --pid --fork \
  --map-root-user \
  kiln-command

# Using bubblewrap (bwrap)
bwrap --unshare-all \
  --ro-bind /usr /usr \
  --tmpfs /tmp \
  --proc /proc \
  --dev /dev \
  kiln-command
```

#### Option 5: Platform-Specific Sandboxing

- **Windows**: AppContainer or Windows Sandbox
- **macOS**: sandbox-exec or App Sandbox

### Network Isolation

Even with filesystem isolation, consider network isolation:

- Disable network access entirely if not needed
- Use network namespaces (Linux)
- Implement egress filtering
- Use isolated VLANs or VPCs

### Credential Management

- Never pass credentials via environment variables to Kiln
- Use credential management systems with fine-grained access control
- Rotate credentials regularly
- Monitor for credential exfiltration

### Monitoring and Auditing

- Log all Kiln executions
- Monitor for suspicious filesystem access
- Monitor for unexpected network connections
- Implement intrusion detection
- Review execution logs regularly

## Configuration Options

### Disabling Security Warnings

If you have implemented proper OS-level isolation and want to suppress warnings:

```python
from engine.isolation_boundary import ENABLE_SECURITY_WARNINGS

# Set to False to suppress warnings (not recommended without proper isolation)
ENABLE_SECURITY_WARNINGS = False
```

**Warning**: Only disable warnings if you have implemented proper OS-level isolation.

## Future Improvements

Potential future enhancements to improve isolation:

1. **Built-in container support**: Native Docker/Podman integration
2. **Configurable isolation backends**: Plugin system for isolation mechanisms
3. **Resource limits**: CPU, memory, and I/O quotas
4. **Network policy enforcement**: Configurable network access rules
5. **Filesystem restrictions**: Configurable read-only mounts
6. **Privilege dropping**: Automatic privilege reduction where possible

## References

- [Linux Namespaces](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Docker Security](https://docs.docker.com/engine/security/)
- [SELinux](https://www.redhat.com/en/topics/linux/what-is-selinux)
- [AppArmor](https://gitlab.com/apparmor/apparmor/-/wikis/home)
- [seccomp](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
- [Bubblewrap](https://github.com/containers/bubblewrap)

## Contact

For security concerns or questions about isolation, please contact the security team.

---

**Last Updated**: 2024
**Version**: 1.0
