# Kiln Recursive Proof Foundation 034

## Authority boundary

This foundation reconciles mutation identity, isolates destructive proof
workers, aggregates parallel evidence deterministically, and records metadata
needed by a future Frankentest composer. It does not authorize test synthesis,
redesign promotion, or mutation of the source repository.

## Canonical mutation identity

`KILN-MUTATION-IDENTITY-2` identifies semantic mutation intent from:

- repository-relative path;
- normalized source-text hash with CRLF and CR represented as LF;
- adapter mutation kind;
- token line and column;
- original token; and
- replacement token.

The candidate retains a raw source hash separately. Raw bytes remain the drift
guard used immediately before mutation, but they do not destabilize the public
candidate ID. A candidate advertised from a clean checkout must therefore
resolve uniquely after Git worktree and sandbox normalization.

## Canonical specimen membership

Before `KILN-SPECIMEN-MEMBERSHIP-1`, mutation source enumeration changed its
policy when a `.git` directory was present: Git-backed roots used only
`git ls-files`, while copied roots recursively scanned content. The same 154
files could therefore yield 766 candidates in a dirty checkout and 832 after
those files were frozen into a clean specimen.

Membership is now derived only from the declared proof root, eligible file
extensions, normalized repository-relative paths, and an explicit exclusion
policy. Git tracked, untracked, staged, and modified state is not an input.
The default policy excludes source-control metadata, virtual environments,
caches, build and package output, dependency/vendor trees, Kiln proof output,
sessions, training data, temporary directories, and sandboxes. Callers may
declare additional relative exclusions, or explicitly admit a path beneath a
default-excluded directory. Explicit relative exclusions always win.

Candidate discovery consumes that membership result and retains its existing
deterministic path, location, token, content-hash, and mutation-ID ordering.
This separation changes membership semantics only;
`KILN-MUTATION-IDENTITY-2` remains unchanged.

## Destructive sandbox contract

`KILN-SANDBOX-2` assigns every baseline or mutation trial a deterministic
sandbox ID derived from cycle identity, pass number, and mutation identity.
Each sandbox owns:

- a unique detached Git worktree;
- a unique mutation target;
- a unique evidence directory;
- an isolated test process; and
- an explicit teardown result.

Git worktree registration and removal are serialized. Test processes run
concurrently only after their independent worktrees exist. Worker evidence is
never written to a shared file.

Parallelism is bounded to 64 workers and requires `until=stable`. Kiln rejects
parallel early-stop modes because completion timing must not decide which
evidence is retained.

Every adapter test process has a finite execution deadline. Exit code `0`
means the mutation survived, exit code `1` means the test suite observed a
fracture, and every other exit or signal is an execution failure. Timeouts,
interruptions, restore failures, and cleanup failures are explicit unknown
outcomes; none may be reported as survival or fracture.

Workers journal materialization, mutation, test execution, and terminal
cleanup state. Teardown retries Git worktree removal, removes the sandbox,
prunes stale registrations, verifies absence, and is idempotent. Startup
recovers abandoned sandboxes. If the prior cycle did not reach `COMPLETE`, the
recovery evidence declares `FULL_REPLAY_REQUIRED`; partial resume is not part
of this foundation.

## Deterministic aggregation

Workers may complete in any order. `mutation-trials.csv` is always ordered by
the original deterministic candidate pass number. Aggregate paths are relative
to the cycle root, and tuple-valued metadata uses canonical compact JSON.
Repeated executions of an equivalent campaign therefore produce equivalent
aggregate evidence regardless of worker completion order.

Before aggregate evidence is accepted, Kiln requires exactly one result for
every authoritative pass and rejects missing, duplicate, or unknown passes.
Candidate coordinates, sandbox identity, process outcome, classification,
restoration, cleanup state, primary process/error evidence, proof metadata,
worker lifecycle, and the serialized trial record must all agree. Missing,
malformed, escaped, dangling, transient-path, or contradictory evidence yields
`AGGREGATE_VALIDATION_FAILED`, never a stable campaign.

## Recursive proof metadata

`KILN-PROOF-METADATA-2` and `KILN-FRAGMENT-CONTRACT-1` preserve, when
observable:

- the mutation identity that exposed the fragment;
- the test identifiers that detected the fracture;
- stable invariant and assertion records derived from assertion locations;
- the deepest nested test statement containing each observed traceback line;
- stable behavioral-fragment source records independent of specimen roots;
- explicit fragment-to-test-to-invariant/assertion-to-mutation proof links;
- ordered prior-statement prerequisites and enclosing statement contexts;
- required, provided, ambient, fixture, and unresolved symbols;
- expected outcomes and bounded parent-test reproduction selectors; and
- deterministic compatibility keys for later comparison.

Every worker writes a versioned `proof-metadata.json`, including an explicit
empty bundle when no fracture metadata is observable. The orchestrator reads
and validates each bundle independently before accepting its trial summary.
It then writes a canonical cycle-level `proof-metadata.json` in authoritative
pass order. `KILN-PROOF-EVIDENCE-3` excludes sandbox IDs, worker paths,
specimen roots, and session roots from that canonical proof aggregate.

The validator recomputes assertion, fragment, contract, invariant,
compatibility, and proof-link identities. It requires every reference to
resolve exactly once, every fragment to have a mutation proof link, every
assertion to belong to its fragment, every source path to be canonical and
relative, and every embedded source hash to match its normalized source text.

Raw stdout and stderr remain worker-local evidence. Their transient locations
are retained only in trial evidence, not inside reusable fragment contracts.

These fields permit later systems to reason about which proven test fragments
detected which mutations, reproduce the parent test, and compare declared
symbol contracts. Reproduction remains `DECLARATIVE_ONLY` and scoped to the
parent test. They are evidence inputs for Frankentest, not an implementation
of Frankentest or authority to synthesize, splice, or promote code.

## Recursive lifecycle

The supported foundation is:

    Discover -> Canonicalize -> Sandbox -> Mutate -> Observe
             -> Classify -> Preserve Evidence -> Feed Back

Feedback remains an adjudicated human or future system action. Proof evidence
does not authorize an automatic source rewrite.
