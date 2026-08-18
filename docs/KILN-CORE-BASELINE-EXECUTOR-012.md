# Kiln Core Isolated Baseline Executor 012

Core 012 is the first generalized Kiln phase allowed to execute target tests.

Execution is permitted only:

- after Core 011 live preflight
- for execution-authorized plans
- in detached Git worktrees
- at the exact preflight source commit
- without pressure
- without repair
- without source promotion

The original checkout is never used as the execution working directory.

Each execution records stdout, stderr, exit code, source commit, duration, worktree recovery, and original HEAD preservation.

A failing baseline is evidence, not authorization to repair.
