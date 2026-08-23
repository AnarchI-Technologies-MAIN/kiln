# Kiln

Kiln is a deterministic destructive software-testing and constructive-redesign system.

Kiln identifies a Git-backed target, materializes disposable specimens, establishes a baseline, discovers deterministic mutation candidates, executes bounded destructive trials inside the specimen boundary, records fracture or survival evidence, restores and tears down specimens, and verifies that the original source repository remains unchanged.

## Install

From a wheel:

    pip install anarchi_kiln-0.1.3-py3-none-any.whl

From Git:

    pip install git+https://github.com/AnarchI-Technologies-MAIN/kiln.git

## CLI

    kiln --version
    kiln capabilities --json
    kiln inspect TARGET --json
    kiln preflight TARGET --adapter python --entry tests --json
    kiln baseline TARGET --adapter python --entry tests --json
    kiln candidates TARGET --adapter python --json
    kiln surfaces TARGET --adapter python --json
    kiln prove TARGET --adapter python --entry tests --json

Destructive mutation cycles require explicit authorization:

    kiln cycle TARGET --adapter python --entry tests --destructive --max-passes 8 --until fracture --json

Independent destructive sandboxes can execute concurrently when early stopping
is disabled:

    kiln cycle TARGET --adapter python --entry tests --destructive --max-passes 8 --until stable --workers 4 --json

Supported v0.1.3 destructive-cycle adapters:

- Python
- JavaScript / TypeScript
- PowerShell
- Linux / WSL2
- API service

Ordinary destructive cycles do not mutate the target source repository. Kiln performs destructive work inside disposable specimens and verifies source preservation afterward.

Mutation IDs use a canonical semantic source fingerprint, so IDs emitted by
`kiln candidates` remain addressable by `kiln inject` across CRLF/LF checkout
normalization and Git worktree recreation. Parallel cycles materialize one
isolated Git worktree and evidence directory per mutation, serialize Git
worktree registry operations, execute tests concurrently, and aggregate trial
evidence in deterministic pass order. Parallel execution is intentionally
restricted to `--until stable`; early-stop campaigns remain sequential.

All destructive test backends are bounded by a finite timeout. Abrupt process
exits, timeouts, interruptions, restoration failures, cleanup failures, and
missing or contradictory worker evidence fail closed as explicit execution or
aggregate failures. Worker lifecycle journals support abandoned-sandbox
cleanup and deterministic full replay; partial resume is not supported.

Cycle evidence includes stable mutation, sandbox, failing-test, invariant,
assertion, and behavioral-fragment references. Every worker emits a standalone
proof-metadata bundle, and the cycle emits a path-independent canonical
aggregate. Assertion-bearing fragments include durable source records,
fragment-to-test-to-mutation proof links, enclosing context and prerequisite
records, expected outcomes, reproduction selectors, symbol requirements, and
compatibility keys. Missing, dangling, contradictory, or transient-path proof
metadata fails aggregate validation. These contracts prepare evidence for
future Frankentest composition; Kiln does not yet synthesize or splice tests.

Promotion is a separate authority boundary subject to Core 030 staging, contamination, adjudication, expected-HEAD, approval, Git, push, and remote-verification gates.

## Release lineage

v0.1.0 is the immutable 33-core canonical architecture freeze and Kiln's first self-specimen.

v0.1.1 adds the installable package, full CLI surface, five destructive-cycle adapters, session evidence, compatibility graph materialization, behavioral fragments, synthetic contracts, and Core 030-backed redesign/promotion surfaces.

v0.1.2 restricted Git-backed mutation discovery to tracked source files. The
recursive-proof membership reconciliation supersedes that repository-index
dependency: declared specimen content now participates identically whether it
is tracked, untracked, staged, modified, or copied without Git metadata, while
explicit generated, dependency, cache, session, and proof-output exclusions
remain enforced.

v0.1.3 adds deterministic baseline snapshots and semantic evidence digests for reproducible cross-specimen and cross-run generation comparison while preserving the historical regression furnace.
