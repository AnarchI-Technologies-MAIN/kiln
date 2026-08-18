# Kiln Core Candidate Selection 005

Core 005 creates a deterministic queue of Kiln candidates.

A shared Test Library occurrence is selectable only when:

- Kiln eligibility has already been admitted.
- At least one attack surface has already been admitted.
- The shared occurrence and content identities still resolve exactly.
- Evidence references are preserved.

Core 005 selects but never executes.

Recovery mode is conservative:

- ELIGIBLE -> DETACHED_WORKTREE
- REQUIRES_ISOLATION -> DETACHED_WORKTREE
- REQUIRES_SANDBOX -> SANDBOX

Candidate identity is deterministic over shared identity plus the admitted attack-surface set.
