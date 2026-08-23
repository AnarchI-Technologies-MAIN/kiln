# KILN-COAL-CONTRACT-1

## Purpose

Kiln is language-agnostic. A coal contract translates one repository's language, build environment, test runner, mutation vocabulary, and failure format into a single contract consumed by the Kiln furnace.

There is no language-name allowlist for repository-supplied coal contracts. A language is runnable when its repository provides a valid `kiln.coal.json` and the declared command-line tools are available in the execution environment.

The canonical machine-readable schema is `schemas/kiln.coal-contract.v1.schema.json`.

The contract is the language-agnostic execution boundary. Coal-house metadata,
runtime probes, conformance fixtures, capability state, and qualification evidence
are sidecars and never add fields to a v1 repository contract.

## Placement and validation

Place one contract at the target repository root:

```text
TARGET/
  kiln.coal.json
```

Validate and inspect the normalized result without running tests:

```text
kiln coal TARGET --adapter ADAPTER_NAME --json
```

The accepted result has disposition `COAL_CONTRACT_ACCEPTED`. Preflight, baseline, candidate inventory, destructive cycles, worker evidence, and proof aggregation resolve the same contract again; they do not trust the earlier command's output.

## Accepted repository contract shape

Repository contracts use these fixed top-level fields:

| Field | Meaning |
| --- | --- |
| `schema` | Must be `kiln.coal-contract.v1`. |
| `contractVersion` | Must be `KILN-COAL-CONTRACT-1`. |
| `adapter` | Stable lowercase adapter identity used by `--adapter`. |
| `languages` | Canonical sorted language identities. |
| `sourceExtensions` | Canonical sorted source-file suffixes. |
| `mutation` | Deterministic text mutation rules. |
| `execution` | Tokenized rebuild and test commands. |
| `proof` | Failure-location, test-ID, and assertion patterns. |

Unknown, missing, duplicated, non-canonical, or malformed fields fail validation.

### Mutation

Repository contracts use the `text-rules` strategy. Each rule supplies:

- a stable uppercase `kind`;
- a regular expression `pattern`;
- an exact `replacements` map;
- optional `ignoreCase` behavior.

Kiln enumerates only declared source extensions, excludes tests and generated/dependency/cache directories, calculates canonical source identities, and rejects duplicate mutation identities.

### Execution and environment reconstruction

Repository contracts use the `command` driver. `rebuildCommands` run in order inside every disposable specimen before `testCommand`. Commands are arrays of process arguments, never shell strings.

Allowed placeholders are:

- `{specimen}`: absolute disposable specimen root;
- `{entry}`: the CLI `--entry` value.

`entryKind` is one of:

- `none`: the contract owns the complete test scope;
- `opaque`: a non-empty runner-specific selector;
- `path`: a repository-relative path that must exist;
- `script`: a named package script (reserved for normalized built-ins).

`appendEntry` appends the entry as one final argument. Environment values may use the same placeholders. Repository contracts cannot override `KILN_*` control variables.

This supports virtual environments, SDK environments, dependency restoration, compilation, code generation, and test preparation without placing those products in the target repository. Examples include creating `.venv`, restoring locked packages, compiling Cargo targets, building Gradle projects, or selecting an SDK wrapper. Every command shares the cycle's finite timeout and runs only inside the disposable specimen.

For the generic command driver, a nonzero final test command is classified as a
fracture only when the declared proof patterns identify both a test and a source
location. Runner-specific codes such as Cargo's `101` are normalized to Kiln's
fracture code only after that evidence is present. A rebuild failure or nonzero
test result with malformed or missing proof fails closed as an execution failure.

### Proof

Repository contracts use the `generic` proof parser:

- every `locationPatterns` expression must expose named `path` and `line` groups;
- every `testPatterns` expression must expose a named `test` group;
- `assertionPatterns` identify assertion-bearing source lines.

Kiln resolves reported paths back into the specimen, rejects paths outside it, derives stable source-relative test and fragment identities, records matching assertions, and emits the same invariant/fragment/proof-link schema used by optimized built-ins. A failure location that is not recognized as an assertion remains a truthful `OBSERVATION` fragment instead of being mislabeled, but observation-only evidence cannot qualify a coal or earn metal.

## Security and determinism boundary

- No contract command is passed through a shell.
- Command tokens cannot contain newlines, NULs, or unknown placeholders.
- All processes have a finite shared deadline.
- Mutation is restricted to deterministic source-token replacements inside declared specimen membership.
- Rebuild products, virtual environments, dependencies, and caches remain specimen-local and are torn down with it.
- The original Git head and cleanliness are verified after execution.
- Contract presence grants capability, not destructive authorization, repair approval, adjudication, promotion, or publication authority.
- Repository contracts cannot invoke known repository mutation, promotion,
  publication, or deployment commands. The tongs move a library contract only
  into an explicitly marked disposable specimen.

## Coal house and tongs

Packaged coals live under `coal_house/packs/ADAPTER/`. Each directory contains:

- `kiln.coal.json`: the unchanged `KILN-COAL-CONTRACT-1` runtime contract;
- `pack.json`: build system, test runner, runtime probe, target marker, and
  named specimen-local environment binding metadata;
- `fixture.json`: deterministic source, test, mutation, and proof fixtures.

Specimen environment adapters live separately under `coal_house/venvs/`. A
`kiln.coal-venv.v1` sidecar declares a reusable set of specimen-relative
directories and environment values. It performs no command execution and grants
no authority. Loading a pack fails unless its `venvAdapter` exists and its
environment is byte-for-byte equivalent to `execution.environment` in the v1
contract. Materialization resolves and creates only declared paths beneath an
already created specimen.

`engine.coal_adapters` exposes each pack as independently reusable language,
build, test/proof, and virtual-environment components. `engine.coal_venvs`
provides dynamic environment discovery, strict validation, and confined
materialization. These sidecars organize implementation; they neither change the
v1 JSON Schema nor restrict valid external adapter names.

The sidecar schemas are `schemas/kiln.coal-pack.v1.schema.json`,
`schemas/kiln.coal-fixture.v1.schema.json`, and
`schemas/kiln.coal-venv.v1.schema.json`. They are additional metadata schemas;
`schemas/kiln.coal-contract.v1.schema.json` remains the unchanged language-
agnostic execution boundary.

Pack discovery enumerates directories and validates their contents. It is not a
language-name allowlist, and a repository may still supply any valid external
adapter identity. Use:

```text
kiln coal-house --json
kiln coal-venvs --json
kiln coal-fixture DESTINATION --adapter rust-cargo --json
kiln coal-qualify --adapter rust-cargo --evidence-root EVIDENCE --destructive --json
```

Capability reporting keeps three independent facts: implemented, runtime
available on this host, and production proven by evidence matching the current
contract hash. A missing or failing runtime probe is never reported as passing.
Qualification runs a passing baseline, one isolated destructive fixture trial,
proof parsing, restoration, cleanup, and a second independent replay. The trial
and proof aggregate hashes must match before fixture qualification succeeds.
Production proof is a separate run against a matching real Git repository.

The reusable tongs are exposed from `engine.coal_tongs`: pack and fixture
discovery, target matching, runtime probing, fixture generation, specimen marking,
safe pack/environment movement, proof-fixture validation, replay comparison, cycle
qualification, evidence writing, and capability-matrix generation.

After every qualification or production-evidence reconciliation, the complete
current survivor set is written to
`C:\Users\alexg\Desktop\AnarchI-Adjudication\To-Adjudicate\kiln-adjudication-candidates.json`.
The `KILN_ADJUDICATION_INBOX` environment variable exists for isolated tests and
relocated installations. Routing supplies evidence for adjudication only; it
grants no repair, promotion, commit, push, or deployment authority.

## Known v1 expressiveness boundary

V1 deliberately describes one deterministic command profile. It cannot express
ordered runtime alternatives or platform-specific command profiles (for example,
`gradlew` versus `gradle`, `mvnw` versus `mvn`, or different Windows and POSIX
wrapper tokens) without selecting one portable executable in the pack. That is a
documented limitation, not permission to add fields to v1.

A future `KILN-COAL-CONTRACT-2` may add an `execution.profiles` structure with
explicit host predicates, tokenized probe commands, and deterministic preference
order. Such a proposal must receive a new schema ID and contract version; v1
contracts and their hashes remain unchanged.

## Adapter-author conformance loop

1. Copy `docs/examples/kiln.coal.json` into the target root.
2. Change the adapter name, languages, extensions, commands, and patterns.
3. Run `kiln coal TARGET --adapter NAME --json`.
4. Run `kiln preflight TARGET --adapter NAME --entry SELECTOR --json`.
5. Run an isolated baseline.
6. Exercise a one-pass disposable cycle with explicit destructive authorization.
7. Verify the trial has stable mutation, test, invariant, assertion, and behavioral-fragment references. Observation-only evidence is retained but fails qualification.
8. Add the adapter fixture and expected evidence to the Kiln test library.

The core contract and tongs conformance suites are:

```text
python -m unittest tests.test_coal_contracts
python -m unittest tests.test_coal_tongs
```

## Frankentest preparation

Every coal produces the same `FragmentContract`, `AssertionRecord`, and `FragmentProofLink` structures. Language-specific adapters may later provide richer symbol, fixture, prerequisite, and context extraction, but generic coals already create stable source-bound proof segments. Frankentest composition can therefore select only compatible, proven segments without depending on the language-specific execution adapter that originally produced them.
