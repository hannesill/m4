from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from m4.config import (
    get_active_backend,
    get_dataset_parquet_root,
    get_default_database_path,
    set_active_dataset,
)
from m4.console import console
from m4.core.datasets import DatasetRegistry
from m4.core.derived.builtins import has_derived_support
from m4.core.derived.materializer import get_derived_table_count, materialize_all
from m4.data_io import (
    convert_csv_to_parquet,
    download_dataset,
    init_duckdb_from_parquet,
    verify_table_rowcount,
)
from m4.services.results import (
    ERROR_DATASET_NOT_FOUND,
    ERROR_INVALID_OPTION,
    CommandError,
    CommandResult,
)

STEP_STATUSES = {"skipped", "completed", "blocked", "failed"}


def _step(
    name: str,
    status: str,
    message: str | None = None,
) -> dict[str, str]:
    if status not in STEP_STATUSES:
        raise ValueError(f"Invalid init step status: {status}")
    result = {"name": name, "status": status}
    if message:
        result["message"] = message
    return result


@contextmanager
def _silence_console_output():
    previous_quiet = console.quiet
    console.quiet = True
    try:
        yield
    finally:
        console.quiet = previous_quiet


def _build_data(
    dataset_key: str,
    db_path: Path | None,
    pq_root: Path | None,
    raw_root: Path | None,
    steps: list[dict[str, str]],
) -> dict:
    return {
        "dataset": dataset_key,
        "db_path": str(db_path.resolve()) if db_path else None,
        "parquet_root": str(pq_root.resolve()) if pq_root else None,
        "raw_root": str(raw_root.resolve()) if raw_root else None,
        "steps": steps,
    }


def initialize_dataset_service(
    dataset_name: str,
    src: str | None = None,
    db_path_str: str | None = None,
    force: bool = False,
) -> CommandResult | CommandError:
    """Run the non-interactive dataset initialization workflow."""
    dataset_key = dataset_name.lower()
    ds = DatasetRegistry.get(dataset_key)
    if not ds:
        supported = ", ".join([d.name for d in DatasetRegistry.list_all()])
        return CommandError(
            command="init",
            code=ERROR_DATASET_NOT_FOUND,
            message=f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )

    with _silence_console_output():
        pq_root = get_dataset_parquet_root(dataset_key)
        if pq_root is None:
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message="Could not determine dataset directories.",
            )

        csv_root_default = pq_root.parent.parent / "raw_files" / dataset_key
        csv_root = Path(src).resolve() if src else csv_root_default
        final_db_path = (
            Path(db_path_str).resolve()
            if db_path_str
            else get_default_database_path(dataset_key)
        )

        steps: list[dict[str, str]] = []
        parquet_present = any(pq_root.rglob("*.parquet"))
        raw_present = any(csv_root.rglob("*.csv.gz"))

        if not raw_present and not parquet_present:
            if ds.requires_authentication:
                steps.extend(
                    [
                        _step(
                            "raw_files",
                            "blocked",
                            (
                                f"Files not found for credentialed dataset "
                                f"'{dataset_key}'. Download manually and rerun init."
                            ),
                        ),
                        _step("parquet", "skipped", "Raw files are not available."),
                        _step(
                            "database", "skipped", "Parquet files are not available."
                        ),
                        _step(
                            "derived",
                            "skipped",
                            "Database initialization did not run.",
                        ),
                    ]
                )
                return CommandResult(
                    command="init",
                    data=_build_data(
                        dataset_key, final_db_path, pq_root, csv_root, steps
                    ),
                    warnings=[],
                )

            listing_url = ds.file_listing_url
            if not listing_url:
                steps.extend(
                    [
                        _step(
                            "raw_files",
                            "blocked",
                            (
                                f"Auto-download is not available for '{dataset_key}'. "
                                "Place raw CSV.gz files in the expected location or use --src."
                            ),
                        ),
                        _step("parquet", "skipped", "Raw files are not available."),
                        _step(
                            "database", "skipped", "Parquet files are not available."
                        ),
                        _step(
                            "derived",
                            "skipped",
                            "Database initialization did not run.",
                        ),
                    ]
                )
                return CommandResult(
                    command="init",
                    data=_build_data(
                        dataset_key, final_db_path, pq_root, csv_root, steps
                    ),
                    warnings=[],
                )

            csv_root_default.mkdir(parents=True, exist_ok=True)
            if not download_dataset(dataset_key, csv_root_default):
                return CommandError(
                    command="init",
                    code=ERROR_INVALID_OPTION,
                    message="Download failed. Please check logs for details.",
                )
            csv_root = csv_root_default
            raw_present = True
            steps.append(_step("raw_files", "completed", "Downloaded raw files."))
        elif raw_present:
            steps.append(_step("raw_files", "completed", "Raw files are present."))
        else:
            steps.append(
                _step("raw_files", "skipped", "Parquet files are already present.")
            )

        if not parquet_present:
            if not raw_present:
                steps.append(
                    _step("parquet", "skipped", "Raw files are not available.")
                )
            elif not convert_csv_to_parquet(dataset_key, csv_root, pq_root):
                return CommandError(
                    command="init",
                    code=ERROR_INVALID_OPTION,
                    message="Conversion failed. Please check logs for details.",
                )
            else:
                parquet_present = True
                steps.append(_step("parquet", "completed", "Converted CSV to Parquet."))
        else:
            steps.append(_step("parquet", "skipped", "Parquet files are present."))

        if not final_db_path:
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message=f"Could not determine database path for '{dataset_name}'.",
            )

        final_db_path.parent.mkdir(parents=True, exist_ok=True)
        if force and final_db_path.exists():
            final_db_path.unlink()

        if not pq_root.exists():
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message=f"Parquet directory not found at {pq_root}",
            )

        if not init_duckdb_from_parquet(
            dataset_name=dataset_key, db_target_path=final_db_path
        ):
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message=(
                    f"Dataset '{dataset_name}' initialization FAILED. "
                    "Please check logs for details."
                ),
            )
        steps.append(_step("database", "completed", "Created DuckDB views."))

        verification_table_name = ds.primary_verification_table
        if verification_table_name:
            try:
                record_count = verify_table_rowcount(
                    final_db_path, verification_table_name
                )
                steps.append(
                    _step(
                        "verification",
                        "completed",
                        f"Verified {record_count} records in '{verification_table_name}'.",
                    )
                )
            except Exception as exc:
                steps.append(
                    _step("verification", "failed", f"Verification failed: {exc}")
                )
        else:
            steps.append(
                _step("verification", "skipped", "No verification table configured.")
            )

        set_active_dataset(dataset_key)

        if has_derived_support(dataset_key) and get_active_backend() == "duckdb":
            try:
                existing_derived = get_derived_table_count(final_db_path)
            except Exception as exc:
                steps.append(
                    _step(
                        "derived", "failed", f"Could not inspect derived tables: {exc}"
                    )
                )
            else:
                if existing_derived > 0 and force:
                    try:
                        created = materialize_all(dataset_key, final_db_path)
                        steps.append(
                            _step(
                                "derived",
                                "completed",
                                f"Materialized {len(created)} derived tables.",
                            )
                        )
                    except Exception as exc:
                        steps.append(
                            _step(
                                "derived",
                                "failed",
                                f"Derived table materialization failed: {exc}",
                            )
                        )
                elif existing_derived > 0:
                    steps.append(
                        _step(
                            "derived",
                            "skipped",
                            (
                                f"Derived tables already materialized "
                                f"({existing_derived} tables)."
                            ),
                        )
                    )
                else:
                    steps.append(
                        _step(
                            "derived",
                            "skipped",
                            "Derived materialization is skipped in non-interactive mode.",
                        )
                    )
        else:
            steps.append(
                _step(
                    "derived",
                    "skipped",
                    "Derived materialization is not available for this configuration.",
                )
            )

        return CommandResult(
            command="init",
            data=_build_data(dataset_key, final_db_path, pq_root, csv_root, steps),
            warnings=[],
        )
