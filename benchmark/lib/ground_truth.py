"""Generate ground truth CSVs by running SQL from ground_truth/ against the full DB.

Prerequisites: Run `m4 init-derived mimic-iv` first to materialize derived tables.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

from .db import (
    SOURCE_DBS,
    _task_key,
    list_task_dirs,
    load_task_config,
    resolve_task_dir,
)

GROUND_TRUTH_DIR = Path("benchmark/ground_truth")


def generate(task_name: str | None = None) -> None:
    """Generate ground truth for one or all tasks.

    Runs the SQL file from ground_truth/{task_key}.sql against the full DB.
    Tasks with ground_truth.alias in task.toml copy from the aliased task.
    """
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    if task_name:
        task_dirs = [resolve_task_dir(task_name)]
    else:
        task_dirs = list_task_dirs()

    # Open connections lazily per database
    connections: dict[str, duckdb.DuckDBPyConnection] = {}

    for task_dir in task_dirs:
        config = load_task_config(task_dir)
        name = config["metadata"]["name"]
        tk = _task_key(name)
        out_path = GROUND_TRUTH_DIR / f"{tk}.csv.gz"

        # Resolve the right database for this task
        db_source = config.get("database", {}).get("source", "mimic-iv")
        db_path = SOURCE_DBS.get(db_source, SOURCE_DBS["mimic-iv"])
        db_key = str(db_path)
        if db_key not in connections:
            connections[db_key] = duckdb.connect(str(db_path), read_only=True)

        gt_config = config.get("ground_truth", {})
        alias = gt_config.get("alias")

        if alias:
            alias_path = GROUND_TRUTH_DIR / f"{alias}.csv.gz"
            if not alias_path.exists():
                print(f"{tk}: alias target {alias} not yet generated, skipping")
                continue
            shutil.copy2(alias_path, out_path)
            print(f"{tk}: copied from {alias}")
            continue

        sql_path = GROUND_TRUTH_DIR / f"{tk}.sql"
        if not sql_path.exists():
            print(f"{tk}: no SQL file found at {sql_path}, skipping")
            continue

        sql = sql_path.read_text()
        con = connections[db_key]
        df = con.execute(sql).df()
        df.to_csv(out_path, index=False, compression="gzip")
        print(f"{tk}: {len(df)} rows → {out_path}")

    for con in connections.values():
        con.close()
