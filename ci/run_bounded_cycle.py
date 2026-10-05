"""Run a bounded Kiln cycle without importing the legacy CLI surface."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from engine.cycle_orchestrator import finalize_cycle_result, run_cycle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--adapter", default="python")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--max-passes", type=int, default=8)
    parser.add_argument("--until", choices=("fracture", "stable"), default="stable")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run_cycle(
        args.target,
        args.adapter,
        args.entry,
        args.max_passes,
        args.until,
        args.session_root,
        workers=args.workers,
    )
    finalized = finalize_cycle_result(result, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(finalized), sort_keys=True, default=str, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(finalized), sort_keys=True, default=str))
    return 0 if finalized.disposition in {"CYCLE_COMPLETE", "FRACTURE_EVIDENCE_PRODUCED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
