"""Generate ground truth CSVs from materialized MIMIC-IV derived tables.

Prerequisites: Run `m4 init-derived mimic-iv` first to materialize derived tables.

Usage:
    python benchmark/shared/generate_ground_truth.py [--task TASK_NAME]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ORACLE_SQL_DIR = Path("benchmark/oracle_sql")

# Map ground truth name → source
# "query:" prefix = inline SQL, "file:" prefix = read from oracle_sql/
TASK_QUERIES = {
    "sirs-24h": "query:SELECT * FROM mimiciv_derived.sirs",
    "sirs-12h": f"file:{ORACLE_SQL_DIR / 'sirs_12h.sql'}",
    # Raw variants use the same ground truth as their non-raw counterpart
    # (same clinical concept, same time window — just different agent environment)
    "sirs-24h-raw": "alias:sirs-24h",
    "sirs-12h-raw": "alias:sirs-12h",
}

DB_PATH = Path("m4_data/databases/mimic_iv.duckdb")
OUTPUT_DIR = Path("benchmark/shared/ground_truth")


def generate(task_name: str | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)

    tasks = {task_name: TASK_QUERIES[task_name]} if task_name else TASK_QUERIES

    for name, source in tasks.items():
        out_path = OUTPUT_DIR / f"{name}.csv.gz"

        if source.startswith("alias:"):
            # Symlink or copy from another ground truth
            alias_name = source[len("alias:") :]
            alias_path = OUTPUT_DIR / f"{alias_name}.csv.gz"
            if not alias_path.exists():
                print(f"{name}: alias target {alias_name} not yet generated, skipping")
                continue
            import shutil

            shutil.copy2(alias_path, out_path)
            print(f"{name}: copied from {alias_name}")
            continue

        if source.startswith("query:"):
            sql = source[len("query:") :]
        elif source.startswith("file:"):
            sql_path = Path(source[len("file:") :])
            sql = sql_path.read_text()
        else:
            sql = source

        df = con.execute(sql).df()
        df.to_csv(out_path, index=False, compression="gzip")
        print(f"{name}: {len(df)} rows → {out_path}")

    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Generate for a specific task only")
    args = parser.parse_args()
    generate(args.task)
