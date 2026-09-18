#!/usr/bin/env python3
"""Import exact successful task and phase timings from fresh-run CSV reports."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common-layer"))

from common.database import TaskPhaseEstimateRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import exact successful task phase timings into TaskPhaseEstimateTable."
    )
    parser.add_argument(
        "phase_csv",
        nargs="+",
        help="One or more aggregate-phase-summary.csv files from the fresh Minikube runner.",
    )
    parser.add_argument(
        "--source-type",
        default="fresh-minikube",
        help="Source type label stored with imported rows.",
    )
    parser.add_argument(
        "--table-name",
        default="",
        help="Explicit DynamoDB table name. Use the deployed SAM stack output value.",
    )
    return parser.parse_args()


def import_phase_csv(path: Path, repo: TaskPhaseEstimateRepository, source_type: str) -> tuple[int, int]:
    imported = 0
    skipped = 0
    source_run_id = path.parent.name

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if int(row.get("exit_code", "1")) != 0:
                skipped += 1
                continue
            game = row.get("game", "").strip()
            task = row.get("task", "").strip()
            phase = row.get("phase", "").strip()
            duration_text = row.get("duration_seconds", "").strip()
            if not game or not task or not phase or not duration_text:
                skipped += 1
                continue
            repo.save(
                game=game,
                task_id=task,
                phase=phase,
                duration_seconds=float(duration_text),
                source_run_id=source_run_id,
                source_type=source_type,
            )
            imported += 1

    return imported, skipped


def main() -> int:
    args = parse_args()
    repo = TaskPhaseEstimateRepository(table_name=args.table_name or None)
    total_imported = 0
    total_skipped = 0

    for csv_path in args.phase_csv:
        path = Path(csv_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        imported, skipped = import_phase_csv(path, repo, args.source_type)
        total_imported += imported
        total_skipped += skipped
        print(f"{path}: imported={imported} skipped={skipped}")

    print(f"total_imported={total_imported} total_skipped={total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
