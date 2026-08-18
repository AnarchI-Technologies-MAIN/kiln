# Kiln Core Live Preflight 011

Core 011 is the final read-only qualification before target execution.

It verifies:

- repository existence
- Git repository identity
- current source commit
- target test path
- supported runner
- supported recovery topology
- successful generalized dry run

A dirty repository is recorded but does not itself authorize execution in the original checkout.

All later execution must occur through the declared isolation topology.

Core 011 executes no tests and creates no worktrees.
