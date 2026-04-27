"""Generate ground truth CSVs by running SQL from ground_truth/ against the full DB.

Prerequisites: Derived tables must be materialized in the database first.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .db import (
    BENCHMARK_ROOT,
    SOURCE_DBS,
    _task_key,
    list_task_dirs,
    load_task_config,
    resolve_task_dir,
)

GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_path(csv_path: Path) -> Path:
    return csv_path.with_suffix("").with_suffix(".manifest.json")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BENCHMARK_ROOT))
    except ValueError:
        return str(path)


def _sort_columns_for_task(df, eval_config: dict) -> list[str]:
    key_columns = [col for col in eval_config.get("key_columns", []) if col in df]
    remaining = [col for col in df.columns if col not in key_columns]
    return [*key_columns, *remaining]


def _write_ground_truth_csv(df, out_path: Path, eval_config: dict) -> list[str]:
    sort_columns = _sort_columns_for_task(df, eval_config)
    if sort_columns:
        df = df.sort_values(sort_columns, kind="mergesort", na_position="last")
    df.to_csv(
        out_path,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    return sort_columns


def _write_manifest(out_path: Path, manifest: dict) -> None:
    manifest["csv_sha256"] = _sha256_file(out_path)
    manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _manifest_path(out_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


def _source_db_hash(db_path: Path, db_hashes: dict[str, str]) -> str:
    key = str(db_path)
    if key not in db_hashes:
        db_hashes[key] = _sha256_file(db_path)
    return db_hashes[key]


def _generate_from_sql(
    *,
    task_key: str,
    sql_path: Path,
    out_path: Path,
    con: duckdb.DuckDBPyConnection,
    db_path: Path,
    eval_config: dict,
    db_hashes: dict[str, str],
) -> None:
    sql = sql_path.read_text()
    df = con.execute(sql).df()
    sort_columns = _write_ground_truth_csv(df, out_path, eval_config)
    duckdb_version = con.execute("PRAGMA version").fetchone()[0]
    _write_manifest(
        out_path,
        {
            "version": 1,
            "source": "sql",
            "task_key": task_key,
            "sql_path": _display_path(sql_path),
            "sql_sha256": _sha256_text(sql),
            "db_path": str(db_path),
            "db_sha256": _source_db_hash(db_path, db_hashes),
            "duckdb_version": duckdb_version,
            "row_count": len(df),
            "columns": list(df.columns),
            "sorted_by": sort_columns,
        },
    )
    print(f"{task_key}: {len(df)} rows -> {out_path}")


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
    db_hashes: dict[str, str] = {}

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
            alias_manifest_path = _manifest_path(alias_path)
            sql_path = GROUND_TRUTH_DIR / f"{alias}.sql"
            if not sql_path.exists():
                raise FileNotFoundError(
                    f"{tk}: alias target {alias} has no SQL file at {sql_path}"
                )
            _generate_from_sql(
                task_key=alias,
                sql_path=sql_path,
                out_path=alias_path,
                con=connections[db_key],
                db_path=db_path,
                eval_config=config["evaluation"],
                db_hashes=db_hashes,
            )
            shutil.copy2(alias_path, out_path)
            target_manifest = json.loads(alias_manifest_path.read_text())
            _write_manifest(
                out_path,
                {
                    "version": 1,
                    "source": "alias",
                    "task_key": tk,
                    "alias_target": alias,
                    "alias_csv_sha256": _sha256_file(alias_path),
                    "alias_manifest": target_manifest,
                },
            )
            print(f"{tk}: copied from {alias}")
            continue

        sql_path = GROUND_TRUTH_DIR / f"{tk}.sql"
        if not sql_path.exists():
            raise FileNotFoundError(f"{tk}: no SQL file found at {sql_path}")

        _generate_from_sql(
            task_key=tk,
            sql_path=sql_path,
            out_path=out_path,
            con=connections[db_key],
            db_path=db_path,
            eval_config=config["evaluation"],
            db_hashes=db_hashes,
        )

    for con in connections.values():
        con.close()
