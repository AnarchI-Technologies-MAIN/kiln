# Kiln Frankentest 1

This is the executable extension to Recursive Proof Foundation 034. Historical
Foundation 034 described preparation for synthesis; this extension implements
composition and recursive qualification without changing mutation identity,
existing coal schemas, source preservation or Core 030 promotion authority.

Frankentest consumes a bounded, duplicate-key-free proof aggregate. It validates
every assertion/fragment/prerequisite/proof-link identity using Kiln's existing
validator and checks the parent-source digest against the current target. Only
assertion-bearing segments with resolved symbols are considered.

The Python unittest composer retains the original module/class context and the
ordered statements through the assertion's enclosing statement. It composes
two independently challenged segments into a new test. Each segment gets its
own unittest fixture and cleanup lifecycle. Original tests are excluded from
generated execution. Custom runners, module fixtures, decorated methods,
cross-module/class joins, early exits, Python assert statements and unresolved
contexts are held. Non-Python synthesis has no executable backend in this
version. These are explicit capability limits, not successful qualification.

A candidate must pass ten fresh-specimen executions: in both normal and
optimized Python, an unchanged positive baseline, each of two identified
production-source mutation challenges, and each mutation with its corresponding
segment removed. Fault challenges must fail an assertion; removal controls must
pass or explicitly retain another segment's detection. The designated segment
must detect its predeclared fault; executed segment identities are checked
against the parent's generated inventory. Errors, skips, zero tests, timeouts, unresolved mutations, test-only
mutations, build failures and failed cleanup do not qualify a candidate.

Target-declared environment variables and rebuild commands are retained.
Generated tests run with the current Python interpreter in isolated mode, with
the specimen explicitly added to its import path. Execution has a finite shared
deadline across rebuild and test commands. The composition backend is separate
from the original target's test-command adapter. Git worktree isolation is a
source boundary, not an OS security sandbox for hostile executables.

Outputs bind source commit, proof digest, fragment identities and generated
source digest. Per-scenario commands, stdout/stderr, outcomes and teardown
results are preserved. Qualification returns QUALIFIED_APPROVAL_CANDIDATE,
never shared approval. Insufficient proof fails closed. Output directories must
be new and outside the target. Original HEAD, clean state and working-tree
fingerprint are compared after execution. This is before/after observation,
not an atomic writer lock or a claim that every runtime dependency was pinned.

Explicit approval requires an authority reference and expected candidate SHA256.
It verifies candidate/source/proof/commit bindings and independently reruns all
recursive checks before creating a create-only, tamper-evident APPROVED_SYSTEM_WIDE_TEST_CANDIDATE
registry entry. Approval never silently installs the candidate, rewrites Brain
contracts, closes numbered gates, activates a host or changes adjacent products.

The candidate identity also binds the composer source, interpreter bytes/version
and coal execution-profile digest. Registry entries contain the exact generated
source and complete qualification snapshot. A complete fsynced receipt is linked
create-only as the admission marker. The receipt is serialized once and its digest
returned for independent custody. Inspection requires the expected receipt digest
and rejects any authority-reference change. The temporary hard-link alias is
removed. This is tamper evidence under trusted-local custody, not immutable storage.
A directory without that marker is pending;
competing approvals produce a conflict rather than an overwrite. Registry
inspection rejects partial entries, content drift and inconsistent snapshots.
These guarantees do not claim host-loss recovery or full filesystem crash durability.

The repair loop remains: preserve fracture evidence, rewind disposable specimens,
repair an isolated successor, re-establish the positive baseline, increase the
declared attack pressure and repeat. A finite surviving campaign is bounded
evidence; it cannot prove that no possible attack will ever break a system.
