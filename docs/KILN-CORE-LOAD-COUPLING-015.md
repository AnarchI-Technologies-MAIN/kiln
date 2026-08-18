# Kiln Core Load Coupling Executor 015

Core 015 performs the first generalized target-native coupling proof.

Only the load attack surface is supported.

The proof compares:

- one untouched baseline invocation
- two untouched pressured invocations

The target-native carrier is the test execution path itself.

Successful observation proves load coupling.

It does not prove resilience.

It does not authorize repair.

It does not mutate production source.

All executions occur in detached worktrees at the proven source commit.
