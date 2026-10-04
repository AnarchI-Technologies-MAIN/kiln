# Kiln Organization-Wide Reusable Workflow 001

## Authority boundary

The caller repository is the specimen. It is checked out at the caller event SHA
and is never installed as the Kiln runtime.

The furnace is a separate checkout of `AnarchI-Technologies-MAIN/kiln`, pinned by
the reusable workflow's `kiln_ref` input. The default is the first frozen green
cross-host self-turn commit:

`55362ad3599e8825937ce462ac0a934f1494cb10`

The proof job itself keeps read-only repository permission. Its mutation trials
may create detached worktrees and evidence under the runner's temporary directory,
but a survivor is not a repair and receives no commit or push authority.

A separate Core 030 boundary may stage an improvement only after all existing
baseline-preservation, fracture-mitigation, contamination, provenance, approval,
and expected-head gates succeed. The staging boundary:

- creates the commit in an isolated detached worktree;
- rejects every branch outside `kiln/staging-adjudication/`;
- pushes with an explicit `HEAD:refs/heads/kiln/staging-adjudication/...` refspec;
- verifies the remote branch resolves to the exact candidate commit;
- creates a draft pull request against the default branch;
- labels the outcome `HUMAN_ADJUDICATION_REQUIRED`, not promoted; and
- explicitly dispatches a new Kiln turn for the verified staging commit.

The draft pull request is the source-mutation boundary. Kiln does not mark it ready,
approve it, merge it, or push the default branch. Only a human adjudicator may take
those steps.

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

This authority does not authorize Frankentest synthesis, splicing, or promotion.
Frankentest remains disabled until a separate, explicit authority contract is
provided.

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

## Recursive dispatch behavior

GitHub intentionally suppresses ordinary `push` workflow events caused by the
built-in `GITHUB_TOKEN`. Therefore the verified staging path sends a
`kiln_staged_adjudication` repository dispatch containing the exact staging commit
and branch. The default-branch workflow validates that the branch is inside the
adjudication namespace and that GitHub's remote ref still equals the supplied
commit before checking it out as the next specimen.

This preserves the invariant that every Kiln-authored staging commit receives a
new furnace turn without granting a long-lived personal token or loading workflow
instructions from the unadjudicated branch.

Each staging branch is one bounded implementation chain. Every dispatched link
runs on a fresh GitHub runner, reconstructs the specimen from the verified staging
commit, installs the pinned Kiln runtime again, and reruns native and destructive
proof. The next action is determined by evidence:

| Fresh-turn result | Proven next repair | Chain disposition | Next action |
| --- | --- | --- | --- |
| No surviving mutation, regression, or execution failure within the bounded campaign | Not applicable | `CHAIN_SEALED_STABLE` | Stop implementation; leave the draft for human adjudication. |
| A mutation survives or another proved weakness appears | Yes, all Core 030 gates pass | `CHAIN_CONTINUES_PROVEN_REPAIR` | Add one new staging commit and dispatch that exact commit. |
| A mutation survives or another proved weakness appears | No, a repair fails proof or none is authorized | `CHAIN_STOPPED_NO_PROVEN_REPAIR` | Stop implementation and preserve the evidence for adjudication. |

A branch is never advanced merely because a mutation survived or a candidate was
generated. Only a newly proven repair may create another link. This produces the
intended “break it, fix it, and repeat until it refuses to break” behavior while
guaranteeing termination whenever Kiln can no longer prove a repair. Until the
separate Frankentest authority exists, no Frankentest-generated repair can satisfy
the middle row.

## Current GitHub enforcement limit

GitHub currently rejects branch-protection and repository-ruleset configuration
for this private repository on its active plan. Draft pull requests cannot be
merged until a person marks them ready, so they still enforce a human transition.
However, a required approving review and a prohibition on direct human pushes to
`main` cannot be enforced server-side until the repository plan supports branch
protection or rulesets. Kiln's own code rejects default-branch pushes regardless of
that hosting limitation.
