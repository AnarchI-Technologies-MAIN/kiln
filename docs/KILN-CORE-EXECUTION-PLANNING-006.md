# Kiln Core Execution Planning 006

Core 006 transforms selected Kiln candidates into deterministic execution plans.

It does not execute those plans.

One candidate with multiple attack surfaces produces one plan per surface.

Every plan preserves:

- shared Test Library occurrence identity
- shared content identity
- Kiln candidate identity
- runner
- repository path
- attack surface
- recovery topology
- evidence provenance

Every generated plan begins with execution_authorized=false.

Execution authority belongs to a later explicit gate.
