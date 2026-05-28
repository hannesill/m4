from __future__ import annotations

from pathlib import Path
from typing import Any

from m4.config import (
    detect_available_local_datasets,
    get_active_backend,
    set_active_dataset,
)
from m4.core.datasets import DatasetRegistry
from m4.services.results import (
    ERROR_BACKEND_INCOMPATIBLE,
    ERROR_DATASET_NOT_FOUND,
    WARNING_LOCAL_DB_MISSING,
    WARNING_LOCAL_PARQUET_MISSING,
    CommandError,
    CommandResult,
)


def _absolute_path_or_none(path_value: str | Path | None) -> str | None:
    if not path_value:
        return None
    return str(Path(path_value).expanduser().resolve())


def _supported_datasets_text() -> str:
    return ", ".join([ds.name for ds in DatasetRegistry.list_all()])


def set_active_dataset_service(target: str) -> CommandResult | CommandError:
    """Set the active dataset and return a machine-readable command result."""
    target = target.lower()

    availability = detect_available_local_datasets().get(target)
    if not availability:
        return CommandError(
            command="use",
            code=ERROR_DATASET_NOT_FOUND,
            message=f"Dataset '{target}' not found or not registered.",
            hint=f"Supported datasets: {_supported_datasets_text()}",
        )

    ds_def = DatasetRegistry.get(target)
    backend_name = get_active_backend()

    if ds_def and not ds_def.bigquery_dataset_ids and backend_name == "bigquery":
        return CommandError(
            command="use",
            code=ERROR_BACKEND_INCOMPATIBLE,
            message=f"Dataset '{target}' is not available on the BigQuery backend.",
            hint="Switch to DuckDB first: m4 backend duckdb",
        )

    set_active_dataset(target)

    warnings = []
    if not availability["parquet_present"]:
        warnings.append(WARNING_LOCAL_PARQUET_MISSING)
    if backend_name == "duckdb" and not availability["db_present"]:
        warnings.append(WARNING_LOCAL_DB_MISSING)

    data: dict[str, Any] = {
        "active_dataset": target,
        "backend": backend_name,
        "dataset": {
            "name": target,
            "parquet_present": bool(availability["parquet_present"]),
            "db_present": bool(availability["db_present"]),
            "parquet_root": _absolute_path_or_none(availability.get("parquet_root")),
            "db_path": _absolute_path_or_none(availability.get("db_path")),
            "bigquery_available": bool(ds_def and ds_def.bigquery_dataset_ids),
        },
    }
    return CommandResult(command="use", data=data, warnings=warnings)
