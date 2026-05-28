from pathlib import Path
from typing import Any

from m4.config import (
    detect_available_local_datasets,
    get_active_backend,
    get_active_dataset,
    get_bigquery_project_id,
)
from m4.core.datasets import DatasetRegistry
from m4.core.derived.builtins import has_derived_support, list_builtins
from m4.core.derived.materializer import get_derived_table_count
from m4.core.exceptions import DatasetError
from m4.data_io import compute_parquet_dir_size, verify_table_rowcount
from m4.services.results import WARNING_PARQUET_PATH_MISMATCH


def _absolute_path_or_none(path_value: str | Path | None) -> str | None:
    if not path_value:
        return None
    return str(Path(path_value).expanduser().resolve())


def _is_path_mismatch_error(exc: Exception) -> bool:
    message = str(exc)
    return "No files found" in message or "no such file" in message.lower()


def _collect_dataset_status(
    name: str,
    ds_info: dict[str, Any],
    active_dataset: str | None,
    backend: str,
) -> dict[str, Any]:
    ds_def = DatasetRegistry.get(name)
    parquet_present = bool(ds_info.get("parquet_present"))
    db_present = bool(ds_info.get("db_present"))
    parquet_root = _absolute_path_or_none(ds_info.get("parquet_root"))
    db_path = _absolute_path_or_none(ds_info.get("db_path"))
    bigquery_available = bool(ds_def and ds_def.bigquery_dataset_ids)
    warnings: list[str] = []

    parquet_size_gb = None
    if parquet_present and parquet_root:
        try:
            size_bytes = compute_parquet_dir_size(Path(parquet_root))
            parquet_size_gb = float(size_bytes) / (1024**3)
        except Exception:
            pass

    row_count = None
    if db_present and db_path and ds_def and ds_def.primary_verification_table:
        try:
            row_count = verify_table_rowcount(
                Path(db_path), ds_def.primary_verification_table
            )
        except Exception as exc:
            if _is_path_mismatch_error(exc):
                warnings.append(WARNING_PARQUET_PATH_MISMATCH)

    derived_supported = has_derived_support(name)
    derived_bigquery = (
        backend == "bigquery" and bigquery_available and derived_supported
    )
    derived_total = None
    derived_materialized = None
    if derived_supported:
        try:
            derived_total = len(list_builtins(name))
        except Exception:
            pass

    if derived_supported and not derived_bigquery and db_present and db_path:
        try:
            derived_materialized = get_derived_table_count(Path(db_path))
        except Exception:
            pass

    return {
        "name": name,
        "active": name == active_dataset,
        "parquet_present": parquet_present,
        "db_present": db_present,
        "parquet_root": parquet_root,
        "db_path": db_path,
        "bigquery_available": bigquery_available,
        "row_count": row_count,
        "parquet_size_gb": parquet_size_gb,
        "derived": {
            "supported": derived_supported,
            "total": derived_total,
            "materialized": derived_materialized,
            "bigquery": derived_bigquery,
        },
        "warnings": warnings,
    }


def collect_status_snapshot(show_all: bool) -> dict[str, Any]:
    try:
        active = get_active_dataset()
    except DatasetError:
        active = None

    backend = get_active_backend()
    availability = detect_available_local_datasets()

    dataset_names = list(availability) if show_all else ([active] if active else [])
    datasets = []
    for name in dataset_names:
        ds_info = availability.get(name)
        if not ds_info:
            continue
        datasets.append(_collect_dataset_status(name, ds_info, active, backend))

    return {
        "version": 1,
        "active_dataset": active,
        "backend": backend,
        "bigquery_project_id": get_bigquery_project_id(),
        "datasets": datasets,
    }
