# Kiln Core Annotations 002

## Boundary

The shared Test Library owns test occurrence and content identities.

Kiln owns annotations about how those shared identities participate in adversarial refinement.

Kiln annotations must never create a test identity that does not exist in the shared Test Library.

## Eligibility

Initial eligibility states:

- UNADJUDICATED
- ELIGIBLE
- REQUIRES_ISOLATION
- REQUIRES_SANDBOX
- RUNNER_BLOCKED
- SUPPORT_ONLY
- BLOCKED

The live index initially seeds every shared occurrence as UNADJUDICATED.

No test becomes ELIGIBLE merely because it exists.

## Attack surfaces

Attack-surface claims require explicit evidence references.

Kiln must not invent or silently infer an attack surface without preserving evidence.

## Duplicate semantics

An identical duplicate annotation is idempotent.

A conflicting duplicate is rejected.

This prevents later ingestion order from silently changing Kiln truth.

## Shared identity invariant

occurrence_id and content_id must resolve exactly to the shared Test Library.

Kiln cannot fork or rewrite those identities.
