"""Generate ground truth CSVs by running SQL from ground_truth/ against the full DB.

Prerequisites: Run `m4 init-derived mimic-iv` first to materialize derived tables.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

from .db import list_task_dirs, load_task_config, resolve_task_dir

DB_PATH = Path("m4_data/databases/mimic_iv.duckdb")
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

    con = duckdb.connect(str(DB_PATH), read_only=True)

    for task_dir in task_dirs:
        config = load_task_config(task_dir)
        name = config["metadata"]["name"]
        task_key = name.replace("mimic-", "")
        out_path = GROUND_TRUTH_DIR / f"{task_key}.csv.gz"

        gt_config = config.get("ground_truth", {})
        alias = gt_config.get("alias")

        if alias:
            alias_path = GROUND_TRUTH_DIR / f"{alias}.csv.gz"
            if not alias_path.exists():
                print(f"{task_key}: alias target {alias} not yet generated, skipping")
                continue
            shutil.copy2(alias_path, out_path)
            print(f"{task_key}: copied from {alias}")
            continue

        sql_path = GROUND_TRUTH_DIR / f"{task_key}.sql"
        if not sql_path.exists():
            print(f"{task_key}: no SQL file found at {sql_path}, skipping")
            continue

        sql = sql_path.read_text()
        df = con.execute(sql).df()
        df.to_csv(out_path, index=False, compression="gzip")
        print(f"{task_key}: {len(df)} rows → {out_path}")

    con.close()
