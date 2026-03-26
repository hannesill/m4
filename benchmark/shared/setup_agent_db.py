"""Create agent database by copying MIMIC-IV DuckDB and dropping target tables.

The agent database has all raw tables and intermediate derived tables,
but the specific derived table being tested is removed so the agent
must compute it from scratch.

Usage:
    python benchmark/shared/setup_agent_db.py --task sirs
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

# Map task name → table(s) to drop from agent DB
TASK_DROP_TABLES = {
    "sirs": ["mimiciv_derived.sirs"],
}

SOURCE_DB = Path("m4_data/databases/mimic_iv.duckdb")
AGENT_DB_DIR = Path("benchmark/agent_db")


def setup(task_name: str) -> Path:
    if task_name not in TASK_DROP_TABLES:
        raise ValueError(
            f"Unknown task: {task_name}. Available: {list(TASK_DROP_TABLES)}"
        )

    AGENT_DB_DIR.mkdir(parents=True, exist_ok=True)
    dest = AGENT_DB_DIR / "mimic_iv.duckdb"

    print(f"Copying {SOURCE_DB} → {dest} ...")
    shutil.copy2(SOURCE_DB, dest)

    # Also copy WAL file if it exists
    wal = SOURCE_DB.with_suffix(".duckdb.wal")
    if wal.exists():
        shutil.copy2(wal, dest.with_suffix(".duckdb.wal"))

    con = duckdb.connect(str(dest))
    for table in TASK_DROP_TABLES[task_name]:
        print(f"Dropping {table} ...")
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.close()

    print(f"Agent DB ready at {dest}")
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="Task name (e.g., sirs)")
    args = parser.parse_args()
    setup(args.task)
