from __future__ import annotations

from m4.config import (
    VALID_BACKENDS,
    get_active_dataset,
    get_bigquery_project_id,
    set_active_backend,
    set_bigquery_project_id,
)
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError
from m4.services.results import (
    ERROR_DATASET_INCOMPATIBLE,
    ERROR_INVALID_BACKEND,
    ERROR_INVALID_OPTION,
    ERROR_PROJECT_ID_REQUIRED,
    CommandError,
    CommandResult,
)


def _get_active_dataset_or_none() -> str | None:
    try:
        return get_active_dataset()
    except DatasetError:
        return None


def set_active_backend_service(
    target: str, project_id: str | None = None
) -> CommandResult | CommandError:
    """Set the active backend and return a machine-readable command result."""
    target = target.lower()

    if target not in VALID_BACKENDS:
        return CommandError(
            command="backend",
            code=ERROR_INVALID_BACKEND,
            message=f"Backend '{target}' is not valid.",
            hint=f"Valid backends: {', '.join(sorted(VALID_BACKENDS))}",
        )

    if target == "duckdb" and project_id:
        return CommandError(
            command="backend",
            code=ERROR_INVALID_OPTION,
            message="--project-id can only be used with bigquery backend.",
        )

    active_dataset = _get_active_dataset_or_none()
    if target == "bigquery" and active_dataset:
        ds_def = DatasetRegistry.get(active_dataset)
        if ds_def and not ds_def.bigquery_dataset_ids:
            return CommandError(
                command="backend",
                code=ERROR_DATASET_INCOMPATIBLE,
                message=(
                    f"Current dataset '{active_dataset}' is not available on BigQuery."
                ),
                hint="Switch dataset first: m4 use <dataset>",
            )

    effective_project_id = None
    if target == "bigquery":
        effective_project_id = project_id or get_bigquery_project_id()
        if not effective_project_id:
            return CommandError(
                command="backend",
                code=ERROR_PROJECT_ID_REQUIRED,
                message="BigQuery backend requires a project ID.",
                hint="Set it with: m4 backend bigquery --project-id <ID>",
            )

    set_active_backend(target)
    if project_id:
        set_bigquery_project_id(project_id)

    return CommandResult(
        command="backend",
        data={
            "backend": target,
            "active_dataset": active_dataset,
            "bigquery_project_id": (
                project_id or effective_project_id or get_bigquery_project_id()
            ),
        },
        warnings=[],
    )
