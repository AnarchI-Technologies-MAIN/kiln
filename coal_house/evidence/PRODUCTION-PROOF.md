# KILN coal-house and tongs production proof

Date: 2026-08-23

## Disposition

The coal house contains 17 dynamically discovered language/build/test packs and
16 independently discovered specimen-environment adapters. The stable runtime
boundary remains `KILN-COAL-CONTRACT-1`; no field was added to the v1 contract or
JSON Schema. Pack and environment manifests are validated sidecars.

Two packs have an available runtime on this host and earned metal through fixture
replay plus a production-shaped repository run:

- `python-unittest` with `python-runtime`;
- `rust-cargo` with `rust-cargo`.

The other 15 packs are implemented but runtime-unavailable and are not reported
as passing or production-proven: C/CMake, C++/CMake, Dart, .NET, Elixir/Mix, Go,
Haskell/Cabal, Java/Maven, Kotlin/Gradle, Lua, PHP/Composer, R, Ruby/Bundler,
Swift/SwiftPM, and Zig.

## Automated verification

- Full Kiln suite: 281 tests passed in 96.337 seconds.
- Adapter/contract focused suite: 34 tests passed in 11.300 seconds.
- Every pack passes the canonical Draft 2020-12 JSON Schema and runtime validator.
- Every pack fixture has deterministic candidate discovery and complete static
  test, invariant, assertion, and behavioral-fragment proof.
- Negative coverage includes unknown fields, forbidden control environments,
  malformed placeholders, shell-injection tokens, timeouts, missing runtimes,
  failed runtime probes, malformed proof, observation-only proof, cleanup failure,
  path escape, unauthorized pack movement, and nondeterministic replay hashes.
- All commands are token arrays and execute without shell-string evaluation.
- The isolated wheel smoke test imported `KILN-COAL-CONTRACT-1`, discovered all
  17 packs and 16 environment adapters, and contained the packaged v1 Schema.

## Python/unittest production proof

Target: `AnarchI-Technologies-MAIN/anar-core`

- Target ID: `KILN-TARGET-092E2B8D036FF71D`
- Commit: `b2bf2aa6800aec63cb6f8503682a1787e5974f9f`
- Fixture candidates: 1
- Fixture execution: one destructive trial in each of two independent replays
- Fixture result: 1 fracture, 0 survivors per replay
- Production execution: 1 destructive trial
- Production result: 1 fracture, 0 survivors, 0 execution failures
- Production proof counts: 31 test references, 14 invariant references,
  1 assertion reference, and 14 behavioral-fragment references
- Every trial restored: true
- Every specimen removed: true
- Source checkout after campaign: clean, same commit, one worktree

Deterministic fixture aggregates:

- `mutation-trials.csv`:
  `94b7485e705941f86a4e914e2f625ceb311732478c6f0f21dc5b50ba237a58df`
- `proof-metadata.json`:
  `fffbc3a5980c1f95e225bcc9e8309a8ad3c3084ff8c859d7de2a83c0732fba2c`

Production aggregates:

- `production-mutation-trials.csv`:
  `5d2c17daf14af26e194af5ca52ffeb83e090ee7333301969f9c55258cf9bd74d`
- `production-proof-metadata.json`:
  `37e7aca5d89922a4a7fc9b8f7c6aa0555d47fe6dc6c37bc84efcc7a70d083658`

## Rust/Cargo production proof

Target: `AnarchI-Technologies/Core-Engine`, entry `core_engine`

- Target ID: `KILN-TARGET-061E172CEBB3F4C9`
- Commit: `a9620132ed9fe9640a020a90e657df84fd672c4a`
- Fixture candidates: 4
- Fixture execution: one destructive trial in each of two independent replays
- Fixture result: 1 fracture, 0 survivors per replay
- Production execution: 1 destructive trial
- Production result: 0 fractures, 1 survivor, 0 execution failures
- Every trial restored: true
- Every specimen removed: true
- Source checkout after campaign: clean, same commit, no disposable Kiln worktree

Deterministic fixture aggregates:

- `mutation-trials.csv`:
  `671dacae8de9eeb594ced29873a7cb0b048fc2d462e17fd7ac651d0914304a41`
- `proof-metadata.json`:
  `2b48ec0dc5062094af978e6cff250ace6c2e900de21928d30c3c0cd9eb4f528d`

Production aggregates:

- `production-mutation-trials.csv`:
  `68acc48805db433ae06f393ac0de437de80adb66ae6442c941aadafdb0541841`
- `production-proof-metadata.json`:
  `2c8e4e10f7eeb380f35a0fd842170c4dbf776295b920844c4e2b4a88d2877ad1`

## Survivors requiring adjudication

One production survivor remains and has no repair or promotion authority:

- `rust-cargo` / `KILN-MUTATION-5CC75DD45EAF5E154453`

Its disposition is `REQUIRES_ADJUDICATION`. No adapter may repair, promote,
commit, push, publish, deploy, or otherwise act on this survivor.

## Evidence and packaging

The deterministic per-adapter evidence manifest binds every bundle to its
contract, pack manifest, environment adapter, and file hashes:

- `evidence-manifest.json`:
  `f4d59868e762e4c9349711e1af8881aa75a8e7ddc974f7fc8821a9a32c6eac15`

The final wheel hash is recorded below after isolated packaging verification.
Build artifacts and smoke-test environments are created outside the source tree
and removed after verification.

- `anarchi_kiln-0.1.3-py3-none-any.whl`:
  `ad8c7f552ecfc2e07a87baf64577b37b459a9f11dd44df34ef8a8d293d7de0bb`

The Kiln changes remain uncommitted and unpushed pending explicit authorization.
