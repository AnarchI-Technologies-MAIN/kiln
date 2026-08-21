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

Supported v0.1.3 destructive-cycle adapters:

- Python
- JavaScript / TypeScript
- PowerShell
- Linux / WSL2
- API service

Ordinary destructive cycles do not mutate the target source repository. Kiln performs destructive work inside disposable specimens and verifies source preservation afterward.

Promotion is a separate authority boundary subject to Core 030 staging, contamination, adjudication, expected-HEAD, approval, Git, push, and remote-verification gates.

## Release lineage

v0.1.0 is the immutable 33-core canonical architecture freeze and Kiln's first self-specimen.

v0.1.1 adds the installable package, full CLI surface, five destructive-cycle adapters, session evidence, compatibility graph materialization, behavioral fragments, synthetic contracts, and Core 030-backed redesign/promotion surfaces.

v0.1.2 fixes Git-backed mutation discovery so only tracked source files participate in deterministic mutation selection.

v0.1.3 adds deterministic baseline snapshots and semantic evidence digests for reproducible cross-specimen and cross-run generation comparison while preserving the historical regression furnace.
