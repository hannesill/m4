"""Materializer for built-in derived concept tables.

Handles the full pipeline of creating derived tables in DuckDB from
vendored mimic-code SQL. Uses direct CREATE TABLE statements — the same
approach mimic-code itself uses.

WARNING: This module writes to the database (DROP/CREATE schemas and tables).
It is intentionally excluded from all tool surfaces (MCP server, Python API)
so that neither LLM tools nor user-facing APIs can trigger materialization.
Only the CLI (``m4 init-derived``, ``m4 init``) should call into this module.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

from m4.config import logger
from m4.console import console, create_task_progress, success
from m4.core.derived.builtins import get_execution_order

# Base schemas that vendored SQL expects to exist per dataset.
# These are created by `m4 init` via schema_mapping in DatasetDefinition.
_REQUIRED_SCHEMAS: dict[str, list[str]] = {
    "mimic-iv": ["mimiciv_hosp", "mimiciv_icu"],
}


def _check_required_schemas(con: duckdb.DuckDBPyConnection, dataset_name: str) -> None:
    """Verify required base schemas exist before materialization.

    The vendored SQL references schema-qualified tables (e.g.,
    mimiciv_icu.chartevents). These schemas are created by ``m4 init``
    with the current schema mapping. Databases initialized with older
    versions may use flat naming and need reinitialization.

    Raises:
        RuntimeError: If required schemas are missing.
    """
    required = _REQUIRED_SCHEMAS.get(dataset_name, [])
    if not required:
        return

    existing = {
        row[0]
        for row in con.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
    }

    missing = [s for s in required if s not in existing]
    if missing:
        raise RuntimeError(
            f"Required schemas not found: {', '.join(missing)}. "
            f"The vendored SQL expects schema-qualified tables "
            f"(e.g., mimiciv_icu.chartevents, mimiciv_hosp.patients). "
            f"Your database may have been initialized with an older version "
            f"of M4. Reinitialize with: m4 init {dataset_name} --force"
        )


def get_derived_table_count(db_path: Path) -> int:
    """Count existing tables in the mimiciv_derived schema.

    Opens a read-only connection to check how many derived tables
    have already been materialized.

    Args:
        db_path: Path to the DuckDB database file.

    Returns:
        Number of tables in mimiciv_derived schema, or 0 if the
        schema doesn't exist or the database is locked.
    """
    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except duckdb.IOException:
        # Database locked or inaccessible — return 0 so the caller
        # proceeds to materialize and gets a clearer lock error there.
        return 0

    try:
        result = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'mimiciv_derived'"
        ).fetchone()
        return result[0] if result else 0
    except duckdb.CatalogException:
        # Schema doesn't exist
        return 0
    finally:
        con.close()


def materialize_all(
    dataset_name: str,
    db_path: Path,
) -> list[str]:
    """Materialize all derived concept tables for a dataset.

    Opens a read-write connection to the existing DuckDB (which already
    has all base table views), drops and recreates the mimiciv_derived
    schema, then executes each SQL file in dependency order.

    Args:
        dataset_name: Name of the dataset (e.g., "mimic-iv").
        db_path: Path to the DuckDB database file.

    Returns:
        List of created table names.

    Raises:
        ValueError: If the dataset has no built-in derived tables.
        FileNotFoundError: If SQL files are missing.
        RuntimeError: If the database is missing required schemas.
        duckdb.Error: If SQL execution fails.
    """
    execution_order = get_execution_order(dataset_name)

    try:
        con = duckdb.connect(str(db_path))
    except duckdb.IOException as e:
        if "Could not set lock" in str(e):
            raise RuntimeError(
                f"Database '{db_path.name}' is locked by another process. "
                "Close any running M4 servers or other DuckDB connections "
                "to this database and try again."
            ) from e
        raise

    try:
        _check_required_schemas(con, dataset_name)

        # Clean slate: drop and recreate derived schema
        con.execute("DROP SCHEMA IF EXISTS mimiciv_derived CASCADE")
        con.execute("CREATE SCHEMA mimiciv_derived")

        created: list[str] = []
        start_time = time.time()

        console.print()
        with create_task_progress() as progress:
            task = progress.add_task(
                f"Materializing {len(execution_order)} derived tables...",
                total=len(execution_order),
            )

            for sql_path in execution_order:
                table_name = sql_path.stem
                progress.update(task, description=f"Creating {table_name}...")

                sql = sql_path.read_text()
                t0 = time.time()
                try:
                    con.execute(sql)
                except Exception as e:
                    progress.stop()
                    raise RuntimeError(
                        f"Failed to create derived table '{table_name}': {e}"
                    ) from e
                dt = time.time() - t0
                created.append(table_name)

                if dt >= 5.0:
                    logger.debug(f"  {table_name}: {dt:.1f}s")

                progress.update(task, advance=1)

        elapsed = time.time() - start_time
        success(f"Materialized {len(created)} derived tables in {elapsed:.1f}s")
        logger.info(
            f"Created derived tables: {', '.join(created[:10])}"
            f"{'...' if len(created) > 10 else ''}"
        )

        return created
    finally:
        con.close()
