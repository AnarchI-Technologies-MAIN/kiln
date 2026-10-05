"""Run the bounded first-party repair-lineage slice."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.repair_lineage import RepairSpec, run_bounded_repair_lineage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--specimen", type=Path, required=True)
    parser.add_argument("--repair", type=Path, required=True, help="JSON RepairSpec")
    parser.add_argument("--regression-oracle", nargs="+", required=True)
    parser.add_argument("--adverse-oracle", nargs="+", required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--parameters", default='{"repair_budget": 1}')
    parser.add_argument("--oracle-file", action="append", default=[])
    args = parser.parse_args()
    repair = RepairSpec(**json.loads(args.repair.read_text(encoding="utf-8")))
    baseline, successor = run_bounded_repair_lineage(
        args.specimen,
        repair,
        args.regression_oracle,
        args.adverse_oracle,
        args.checkpoint_root,
        json.loads(args.parameters),
        tuple(args.oracle_file),
    )
    print(json.dumps({"baseline": asdict(baseline), "successor": asdict(successor)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
