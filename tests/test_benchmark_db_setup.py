from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_compact_duckdb_file_removes_dropped_catalog_strings(tmp_path):
    db_module = _load_module("benchmark_db_setup", "benchmark/lib/db.py")
    db_path = tmp_path / "agent.duckdb"
    removed_name = b"secret_removed_shortcut_table"

    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE kept_table (id INTEGER)")
    con.execute("INSERT INTO kept_table VALUES (1)")
    con.execute("CREATE TABLE secret_removed_shortcut_table (answer INTEGER)")
    con.execute("INSERT INTO secret_removed_shortcut_table VALUES (42)")
    con.execute("DROP TABLE secret_removed_shortcut_table")
    con.close()

    db_module.compact_duckdb_file(db_path)

    assert removed_name not in db_path.read_bytes()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute("SELECT SUM(id) FROM kept_table").fetchone()[0] == 1
        assert (
            con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'secret_removed_shortcut_table'
                """
            ).fetchone()[0]
            == 0
        )
    finally:
        con.close()
