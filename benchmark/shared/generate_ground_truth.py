"""Generate ground truth CSVs from materialized MIMIC-IV derived tables.

Prerequisites: Run `m4 init-derived mimic-iv` first to materialize derived tables.

Usage:
    python benchmark/shared/generate_ground_truth.py [--task TASK_NAME]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

# Map task name → derived table query
TASK_QUERIES = {
    "sirs": "SELECT * FROM mimiciv_derived.sirs",
}

DB_PATH = Path("m4_data/databases/mimic_iv.duckdb")
OUTPUT_DIR = Path("benchmark/shared/ground_truth")


def generate(task_name: str | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)

    tasks = {task_name: TASK_QUERIES[task_name]} if task_name else TASK_QUERIES

    for name, query in tasks.items():
        df = con.execute(query).df()
        out_path = OUTPUT_DIR / f"{name}.csv"
        df.to_csv(out_path, index=False)
        print(f"{name}: {len(df)} rows → {out_path}")

    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Generate for a specific task only")
    args = parser.parse_args()
    generate(args.task)
