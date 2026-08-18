# Kiln Core Pressure Contracts 008

Core 008 defines bounded pressure contracts.

It does not execute pressure.

Each pressure contract:

- belongs to one execution plan
- belongs to one attack surface
- has a finite ordered ladder
- halts on the first unexplained fracture
- requires behavioral coupling proof
- starts with pressure_execution_authorized=false

Current generic pressure families are derived from Cycle 001 evidence:

- load
- state-staleness
- authority-conflict
- filesystem-state

Unknown attack surfaces fail closed until their semantics are separately admitted.
