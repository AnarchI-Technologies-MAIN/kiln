# Kiln Core Eligibility Admission 003

Core 003 admits only eligibility already justified by harvested baseline preflight evidence.

The shared Test Library remains authoritative for test identity.

Kiln owns the eligibility interpretation.

Attack surfaces are not modified by this phase.

Known mapping:

- READY_FOR_BASELINE_EXECUTION_PLANNING -> ELIGIBLE
- READY_BUT_DIRTY_REPOSITORY -> REQUIRES_ISOLATION
- ISOLATION_TOPOLOGY_REQUIRED -> REQUIRES_ISOLATION
- SANDBOX_TOPOLOGY_REQUIRED -> REQUIRES_SANDBOX
- RUNNER_RECONCILIATION_REQUIRED -> RUNNER_BLOCKED
- SUPPORT_ARTIFACT_ONLY -> SUPPORT_ONLY
- BLOCKED -> BLOCKED

When several execution contexts map to one occurrence, the most restrictive supported disposition wins.

Every admitted decision preserves row-level preflight evidence provenance.
