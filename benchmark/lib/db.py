"""Create task-specific agent databases from the full MIMIC-IV source.

Copies the source DB and drops tables listed in the task's task.toml,
so the agent must compute them from scratch.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

LIB_DIR = Path(__file__).resolve().parent
BENCHMARK_ROOT = LIB_DIR.parent
REPO_ROOT = BENCHMARK_ROOT.parent

SOURCE_DBS = {
    "mimic-iv": REPO_ROOT / "m4_data" / "databases" / "mimic_iv.duckdb",
    "eicu": REPO_ROOT / "m4_data" / "databases" / "eicu.duckdb",
}
SOURCE_DB = SOURCE_DBS["mimic-iv"]  # default for backwards compat
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"
TASKS_DIR = BENCHMARK_ROOT / "tasks"


def _quote_duckdb_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _remove_wal(db_path: Path) -> None:
    wal = db_path.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()


def compact_duckdb_file(db_path: Path) -> None:
    """Rewrite a DuckDB file so dropped-table catalog strings are not retained."""
    tmp = db_path.with_suffix(".compact.duckdb")
    if tmp.exists():
        tmp.unlink()
    _remove_wal(tmp)

    con = duckdb.connect()
    try:
        con.execute(f"ATTACH {_quote_duckdb_path(db_path)} AS src")
        con.execute(f"ATTACH {_quote_duckdb_path(tmp)} AS dst")
        con.execute("COPY FROM DATABASE src TO dst")
    finally:
        con.close()

    _remove_wal(db_path)
    db_path.unlink()
    tmp.replace(db_path)
    _remove_wal(tmp)


def resolve_task_dir(task_name: str) -> Path:
    """Find a task directory by name within the (possibly nested) tasks tree.

    Walks TASKS_DIR looking for a directory matching task_name that contains
    a task.toml file. Supports both flat (tasks/mimic-sirs-24h/) and nested
    (tasks/sirs/mimic-sirs-24h/) layouts.
    """
    # Fast path: flat layout
    flat = TASKS_DIR / task_name
    if (flat / "task.toml").exists():
        return flat

    # Walk the tree
    for candidate in TASKS_DIR.rglob(task_name):
        if candidate.is_dir() and (candidate / "task.toml").exists():
            return candidate

    raise FileNotFoundError(
        f"Task '{task_name}' not found under {TASKS_DIR}. "
        f"Expected a directory containing task.toml."
    )


def list_task_dirs() -> list[Path]:
    """Discover all task directories (those containing task.toml)."""
    return sorted(p.parent for p in TASKS_DIR.rglob("task.toml"))


def load_task_config(task_dir: Path) -> dict:
    """Load task.toml from a task directory."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    config_path = task_dir / "task.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Task config not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def _task_key(task_name: str) -> str:
    """Strip the database prefix from a task name to get the task key."""
    for prefix in ("mimic-", "eicu-"):
        if task_name.startswith(prefix):
            return task_name[len(prefix) :]
    return task_name


def _db_prefix(task_name: str) -> str:
    """Get the database file prefix for a task name."""
    if task_name.startswith("eicu-"):
        return "eicu"
    return "mimic_iv"


def _source_db(task_name: str) -> Path:
    """Resolve the source database path for a task."""
    if task_name.startswith("eicu-"):
        return SOURCE_DBS["eicu"]
    return SOURCE_DBS["mimic-iv"]


def _is_raw_mimic_task(config: dict) -> bool:
    return (
        config.get("metadata", {}).get("mode") == "raw"
        and config.get("database", {}).get("source", "mimic-iv") == "mimic-iv"
    )


def _relations_in_schema(con: duckdb.DuckDBPyConnection, schema: str) -> list[str]:
    """Return fully qualified tables/views in a schema."""
    rows = con.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = ?
        ORDER BY table_name
        """,
        [schema],
    ).fetchall()
    return [f"{row[0]}.{row[1]}" for row in rows]


def _drop_table_or_view(con: duckdb.DuckDBPyConnection, relation: str) -> None:
    """Drop a relation without assuming whether DuckDB stored it as a table or view."""

    def quote_ident(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    if "." in relation:
        schema, name = relation.split(".", 1)
        quoted = f"{quote_ident(schema)}.{quote_ident(name)}"
    else:
        schema, name = "main", relation
        quoted = quote_ident(relation)

    table_type = con.execute(
        """
        SELECT table_type
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, name],
    ).fetchone()
    if not table_type:
        return
    if str(table_type[0]).upper() == "VIEW":
        con.execute(f"DROP VIEW IF EXISTS {quoted}")
    else:
        con.execute(f"DROP TABLE IF EXISTS {quoted}")


def effective_drop_tables(
    config: dict, con: duckdb.DuckDBPyConnection | None = None
) -> list[str]:
    """Return the relations that must be unavailable in the task DB.

    Raw MIMIC tasks are enforced at schema level: all `mimiciv_derived`
    relations are removed from the agent database, not only the shortcuts
    listed in task.toml. The task list remains useful documentation, while this
    helper is the actual leakage control used by setup and preflight.
    """
    configured = list(config.get("database", {}).get("drop_tables", []))
    if _is_raw_mimic_task(config):
        if con is None:
            return sorted(set(configured) | {"mimiciv_derived.*"})
        configured.extend(_relations_in_schema(con, "mimiciv_derived"))
    return sorted(dict.fromkeys(configured))


def setup_agent_db(task_dir: Path) -> Path:
    """Create an agent database for a task by dropping specified tables.

    For MIMIC-IV tasks, reads drop_tables from task.toml's [database] section.
    For eICU tasks, copies the full database (no derived tables to drop).

    Returns:
        Path to the created agent database.
    """
    config = load_task_config(task_dir)
    task_name = config["metadata"]["name"]
    task_key = _task_key(task_name)
    db_prefix = _db_prefix(task_name)
    source = _source_db(task_name)

    AGENT_DB_DIR.mkdir(parents=True, exist_ok=True)
    dest = AGENT_DB_DIR / f"{db_prefix}_{task_key}.duckdb"

    print(f"Copying {source} → {dest} ...")
    _remove_wal(dest)
    shutil.copy2(source, dest)

    # Also copy WAL file if it exists
    wal = source.with_suffix(".duckdb.wal")
    if wal.exists():
        shutil.copy2(wal, dest.with_suffix(".duckdb.wal"))
    else:
        _remove_wal(dest)

    con = duckdb.connect(str(dest))
    drop_tables = effective_drop_tables(config, con)
    if drop_tables:
        for table in drop_tables:
            print(f"Dropping {table} ...")
            _drop_table_or_view(con, table)
        con.close()
        print("Compacting agent DB ...")
        compact_duckdb_file(dest)
    else:
        con.close()

    print(f"Agent DB ready at {dest}")
    return dest
