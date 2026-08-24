# Kiln Organization-Wide Reusable Workflow 001

## Authority boundary

The caller repository is the specimen. It is checked out at the caller event SHA
and is never installed as the Kiln runtime.

The furnace is a separate checkout of `AnarchI-Technologies-MAIN/kiln`, pinned by
the reusable workflow's `kiln_ref` input. The default is the first frozen green
cross-host self-turn commit:

`55362ad3599e8825937ce462ac0a934f1494cb10`

The reusable workflow has read-only repository permission. It may create detached
worktrees and evidence under the runner's temporary directory, but it receives no
promotion, repair, commit, or push authority.

## Caller contract

Each private AnarchI repository can call:

```yaml
jobs:
  kiln:
    uses: AnarchI-Technologies-MAIN/kiln/.github/workflows/kiln-proof.yml@<pinned-workflow-sha>
    with:
      adapter: python
      entry: tests
      native_test_result: ${{ needs.native-tests.result }}
```

Callers must pin the workflow revision. The reusable workflow independently pins
the Kiln runtime revision, so changing a specimen cannot silently replace the
furnace.

The initial interface accepts explicit `adapter` and `entry` inputs. A committed
repository contract such as `kiln.toml` may replace those inputs later, after the
reusable workflow itself has earned a stable proof record.

## Evidence behavior

Every call records:

- caller repository, ref, SHA, run, and attempt;
- caller native-test result;
- requested and resolved Kiln runtime identity;
- caller specimen identity and host capabilities;
- baseline, mutation, fracture, survivor, restoration, and cleanup evidence.

Survivors are evidence requiring adjudication. They do not authorize automatic
repair or promotion.

The first recursive backlog item is
`registry/evidence/kiln-recursive-survivor-backlog-001.csv`, sourced from successful
run `32686029023`. Its four survivors are preserved with `repair_authorized=false`.

## Access boundary

Kiln is currently private. GitHub organization access can expose this reusable
workflow to other private repositories in `AnarchI-Technologies-MAIN` without
making the furnace public.

Public callers cannot consume a private reusable workflow under the same trust
model. Supporting public AnarchI repositories therefore requires a separate,
explicit distribution decision, such as a public, release-pinned Kiln package or
a deliberately public workflow host. Private source visibility must not be
weakened implicitly for rollout convenience.
