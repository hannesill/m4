from __future__ import annotations

from m4.config import get_active_backend, get_default_database_path, logger
from m4.core.datasets import DatasetRegistry
from m4.core.derived.builtins import list_builtins
from m4.core.derived.materializer import (
    get_derived_table_count,
    materialize_all,
)
from m4.services.events import EventReporter
from m4.services.results import CommandError, CommandResult


def init_derived_service(
    dataset_name: str,
    *,
    list_only: bool = False,
    force: bool = False,
    event_reporter: EventReporter | None = None,
) -> CommandResult | CommandError:
    dataset_key = dataset_name.lower()
    ds = DatasetRegistry.get(dataset_key)

    if not ds:
        supported = ", ".join(d.name for d in DatasetRegistry.list_all())
        return CommandError(
            command="init-derived",
            code="dataset_not_found",
            message=f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )

    if dataset_key in ("mimic-iv-demo",):
        return CommandError(
            command="init-derived",
            code="derived_not_supported",
            message=f"Derived tables are not supported for '{dataset_key}'.",
            hint=(
                "The demo dataset has only 100 patients; many derived concepts "
                "produce empty or unreliable results. Use the full mimic-iv dataset."
            ),
        )

    if get_active_backend() == "bigquery":
        return CommandResult(
            command="init-derived",
            data={
                "dataset": dataset_key,
                "status": "skipped",
                "reason": "bigquery_derived_tables_available",
                "created_tables": [],
                "table_count": 0,
            },
        )

    if list_only:
        try:
            names = list_builtins(dataset_key)
        except ValueError as exc:
            return CommandError(
                command="init-derived",
                code="derived_not_supported",
                message=str(exc),
            )
        return CommandResult(
            command="init-derived",
            data={
                "dataset": dataset_key,
                "status": "listed",
                "tables": names,
                "table_count": len(names),
            },
        )

    db_path = get_default_database_path(dataset_key)
    if not db_path or not db_path.exists():
        return CommandError(
            command="init-derived",
            code="database_not_found",
            message=f"No DuckDB database found for '{dataset_key}'.",
            hint=f"Initialize first: m4 init {dataset_key}",
        )

    existing_count = get_derived_table_count(db_path)
    if existing_count > 0 and not force:
        return CommandResult(
            command="init-derived",
            data={
                "dataset": dataset_key,
                "status": "skipped",
                "reason": "already_materialized",
                "database": str(db_path),
                "existing_table_count": existing_count,
                "created_tables": [],
                "table_count": 0,
            },
        )

    try:
        created = materialize_all(dataset_key, db_path, event_reporter=event_reporter)
    except ValueError as exc:
        return CommandError(
            command="init-derived",
            code="derived_not_supported",
            message=str(exc),
        )
    except RuntimeError as exc:
        return CommandError(
            command="init-derived",
            code="derived_materialization_failed",
            message=str(exc),
            hint=(
                "If the database is locked, stop MCP servers or notebooks using it."
                if "locked by another process" in str(exc)
                else None
            ),
        )
    except Exception as exc:
        logger.error("Derived table materialization error: %s", exc, exc_info=True)
        return CommandError(
            command="init-derived",
            code="derived_materialization_failed",
            message=f"Materialization failed: {exc}",
        )

    return CommandResult(
        command="init-derived",
        data={
            "dataset": dataset_key,
            "status": "completed",
            "database": str(db_path),
            "created_tables": created,
            "table_count": len(created),
        },
    )
