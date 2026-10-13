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
from m4.data_io import (
    compute_parquet_dir_size,
    is_dataset_prepared,
    raw_files_left_to_convert,
    verify_table_rowcount,
)
from m4.services.results import WARNING_PARQUET_PATH_MISMATCH


def _absolute_path_or_none(path_value: str | Path | None) -> str | None:
    if not path_value:
        return None
    return str(Path(path_value).expanduser().resolve())


def _is_path_mismatch_error(exc: Exception) -> bool:
    message = str(exc)
    return "No files found" in message or "no such file" in message.lower()


def _is_prepared(name: str, ds_info: dict[str, Any]) -> bool:
    """Whether `m4 init` ran to the end for dataset `name`, which `ds_info` describes.

    Files being there is not enough. The views must have been made and
    verified over the Parquet files as they are now, and M4's own raw folder
    must hold no file that init has yet to convert, as it does when files
    came into it afterwards.
    """
    raw_root = _absolute_path_or_none(ds_info.get("raw_root"))
    parquet_root = _absolute_path_or_none(ds_info.get("parquet_root"))
    db_path = _absolute_path_or_none(ds_info.get("db_path"))
    if not (
        ds_info.get("parquet_present")
        and ds_info.get("db_present")
        and parquet_root
        and db_path
        and is_dataset_prepared(Path(parquet_root), Path(db_path))
    ):
        return False
    if not raw_root:
        return True
    ds_def = DatasetRegistry.get(name)
    return not raw_files_left_to_convert(
        Path(raw_root), Path(parquet_root), ds_def.schema_mapping if ds_def else None
    )


def is_ready(name: str) -> bool:
    """Whether dataset `name` is ready, as `m4 status` reports it."""
    ds_info = detect_available_local_datasets().get(name.lower())
    return bool(ds_info) and _is_prepared(name.lower(), ds_info)


def _collect_dataset_status(
    name: str,
    ds_info: dict[str, Any],
    selected_dataset: str | None,
    backend: str,
    *,
    include_row_count: bool,
    include_paths: bool,
) -> dict[str, Any]:
    ds_def = DatasetRegistry.get(name)
    raw_present = bool(ds_info.get("raw_present"))
    parquet_present = bool(ds_info.get("parquet_present"))
    db_present = bool(ds_info.get("db_present"))
    raw_root = _absolute_path_or_none(ds_info.get("raw_root"))
    parquet_root = _absolute_path_or_none(ds_info.get("parquet_root"))
    db_path = _absolute_path_or_none(ds_info.get("db_path"))
    bigquery_available = bool(ds_def and ds_def.bigquery_dataset_ids)
    requires_authentication = bool(ds_def and ds_def.requires_authentication)
    download_available = bool(ds_def and ds_def.file_listing_url)
    warnings: list[str] = []

    parquet_size_gb = None
    if parquet_present and parquet_root:
        try:
            size_bytes = compute_parquet_dir_size(Path(parquet_root))
            parquet_size_gb = float(size_bytes) / (1024**3)
        except Exception:
            pass

    row_count = None
    if (
        include_row_count
        and db_present
        and db_path
        and ds_def
        and ds_def.primary_verification_table
    ):
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

    prepared = _is_prepared(name, ds_info)

    if prepared:
        setup_state = "ready"
    elif requires_authentication and not raw_present and not parquet_present:
        setup_state = "credentials_required"
    elif not raw_present and not parquet_present:
        setup_state = "missing_raw_files"
    elif not parquet_present:
        setup_state = "missing_parquet"
    elif not db_present:
        setup_state = "missing_database"
    else:
        setup_state = "incomplete"

    result = {
        "name": name,
        "selected": name == selected_dataset,
        "raw_present": raw_present,
        "parquet_present": parquet_present,
        "db_present": db_present,
        "prepared": prepared,
        "requires_authentication": requires_authentication,
        "download_available": download_available,
        "setup_state": setup_state,
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

    if include_paths:
        result["raw_root"] = raw_root
        result["parquet_root"] = parquet_root
        result["db_path"] = db_path

    return result


def collect_status_snapshot(
    show_all: bool,
    include_paths: bool = False,
    selected_dataset: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    selected = selected_dataset.lower() if selected_dataset else None
    if selected is None:
        try:
            selected = get_active_dataset()
        except Exception:
            selected = None
    backend_name = (backend or get_active_backend()).lower()
    availability = detect_available_local_datasets()

    dataset_names = list(availability) if show_all else ([selected] if selected else [])
    datasets = []
    for name in dataset_names:
        ds_info = availability.get(name)
        if not ds_info:
            continue
        datasets.append(
            _collect_dataset_status(
                name,
                ds_info,
                selected,
                backend_name,
                include_row_count=not show_all,
                include_paths=include_paths,
            )
        )

    return {
        "version": 1,
        "active_dataset": selected,
        "selected_dataset": selected,
        "backend": backend_name,
        "bigquery_project_id": get_bigquery_project_id(),
        "datasets": datasets,
    }
