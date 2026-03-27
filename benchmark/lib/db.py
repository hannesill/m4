"""Create task-specific agent databases from the full MIMIC-IV source.

Copies the source DB and drops tables listed in the task's task.toml,
so the agent must compute them from scratch.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

SOURCE_DB = Path("m4_data/databases/mimic_iv.duckdb")
AGENT_DB_DIR = Path("benchmark/agent_db")
TASKS_DIR = Path("benchmark/tasks")


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
    import tomllib

    config_path = task_dir / "task.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Task config not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def setup_agent_db(task_dir: Path) -> Path:
    """Create an agent database for a task by dropping specified tables.

    Reads drop_tables from task.toml's [database] section.

    Returns:
        Path to the created agent database.
    """
    config = load_task_config(task_dir)
    task_name = config["metadata"]["name"]
    task_key = task_name.replace("mimic-", "")

    drop_tables = config.get("database", {}).get("drop_tables", [])
    if not drop_tables:
        raise ValueError(f"No drop_tables defined in {task_dir / 'task.toml'}")

    AGENT_DB_DIR.mkdir(parents=True, exist_ok=True)
    dest = AGENT_DB_DIR / f"mimic_iv_{task_key}.duckdb"

    print(f"Copying {SOURCE_DB} → {dest} ...")
    shutil.copy2(SOURCE_DB, dest)

    # Also copy WAL file if it exists
    wal = SOURCE_DB.with_suffix(".duckdb.wal")
    if wal.exists():
        shutil.copy2(wal, dest.with_suffix(".duckdb.wal"))

    con = duckdb.connect(str(dest))
    for table in drop_tables:
        print(f"Dropping {table} ...")
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.close()

    print(f"Agent DB ready at {dest}")
    return dest
