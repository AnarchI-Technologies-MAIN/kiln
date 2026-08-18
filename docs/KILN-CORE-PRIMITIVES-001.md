# Kiln Core Primitives 001

## Shared Test Library boundary

Kiln consumes Test Library identities and metadata.

Kiln does not own or rewrite the shared Test Library.

The initial KilnLibraryIndex is therefore read-only.

## Library Indexer

The indexer creates a deterministic Kiln-scoped view keyed by Test Library occurrence identity.

It may enrich those references later with Kiln-specific eligibility, attack-surface, pressure, recovery, fracture, and evidence references.

Those annotations belong to Kiln rather than the shared Test Library.

## Refinement State Machine

The state machine provides explicit allowed transitions.

Every transition requires an evidence identifier and reason.

Illegal state jumps fail closed.

Contradicted evidence may be reconciled or superseded without deleting history.

SUPERSEDED is terminal for that evidence lineage.

## Initial states

- DISCOVERED
- UNADJUDICATED
- PLAUSIBLE
- PROOF_REQUIRED
- PROVEN
- PRESSURE_AUTHORIZED
- FRACTURED
- ADJUDICATED
- REPAIR_TRIAL
- CHECKPOINTED
- PROMOTED
- EXHAUSTED
- BLOCKED
- CONTRADICTED
- RECONCILED
- SUPERSEDED
