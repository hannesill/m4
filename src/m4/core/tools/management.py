"""Dataset management tools for M4.

This module provides tools for switching between datasets and listing
available datasets. These tools are always available regardless of
the selected request dataset.

All tools use config functions directly - no circular dependencies.

Architecture Note:
    Tools return native Python types. The MCP server serializes these
    for the protocol; the Python API receives them directly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m4.config import (
    detect_available_local_datasets,
    get_active_backend,
    get_active_dataset,  # noqa: F401 - retained for compatibility patch targets
    set_active_dataset,  # noqa: F401 - retained for compatibility patch targets
)
from m4.core.context import M4ExecutionContext
from m4.core.datasets import DatasetDefinition, DatasetRegistry, Modality
from m4.core.derived.builtins import has_derived_support, list_builtins
from m4.core.derived.materializer import get_derived_table_count
from m4.core.exceptions import DatasetError
from m4.core.tools.base import ToolInput


@dataclass
class ListDatasetsInput(ToolInput):
    """Input for list_datasets tool."""

    pass  # No parameters needed


@dataclass
class SetDatasetInput(ToolInput):
    """Input for set_dataset tool."""

    dataset_name: str


class ListDatasetsTool:
    """Tool for listing all available datasets.

    This tool shows which datasets are configured and available,
    both locally (DuckDB) and remotely (BigQuery).

    Returns:
        dict with selected dataset, backend info, and dataset availability
    """

    name = "list_datasets"
    description = "📋 List all available medical datasets"
    input_model = ListDatasetsInput

    # Management tools have no modality requirements - always available
    required_modalities: frozenset[Modality] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(
        self,
        dataset: DatasetDefinition,
        params: ListDatasetsInput,
        context: M4ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """List all available datasets with their status.

        Returns:
            dict with:
                - selected_dataset: str | None - Request-scoped dataset, if any
                - backend: str - Backend type (duckdb or bigquery)
                - datasets: dict[str, dict] - Dataset availability info
        """
        try:
            selected = context.dataset.name if context else None
        except Exception:
            selected = None
        availability = detect_available_local_datasets()
        backend_name = context.backend_name if context else get_active_backend()

        datasets_info: dict[str, dict] = {}

        for label, info in availability.items():
            ds_def = DatasetRegistry.get(label)

            # Derived table info
            derived_info = None
            if has_derived_support(label):
                total = len(list_builtins(label))
                materialized = None
                if backend_name == "duckdb":
                    if info["db_present"] and info.get("db_path"):
                        materialized = get_derived_table_count(Path(info["db_path"]))
                    else:
                        materialized = 0
                derived_info = {
                    "supported": True,
                    "total": total,
                    "materialized": materialized,
                }

            datasets_info[label] = {
                "is_active": label == selected,
                "selected": label == selected,
                "parquet_present": info["parquet_present"],
                "db_present": info["db_present"],
                "bigquery_support": bool(ds_def and ds_def.bigquery_dataset_ids),
                "modalities": ([m.name for m in ds_def.modalities] if ds_def else []),
                "derived": derived_info,
            }

        return {
            "active_dataset": selected,
            "selected_dataset": selected,
            "backend": backend_name,
            "datasets": datasets_info,
        }

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True


class SetDatasetTool:
    """Deprecated compatibility shim for removed global dataset state."""

    name = "set_dataset"
    description = "🔄 Switch to a different dataset"
    input_model = SetDatasetInput

    # Management tools have no modality requirements - always available
    required_modalities: frozenset[Modality] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(
        self,
        dataset: DatasetDefinition,
        params: SetDatasetInput,
        context: M4ExecutionContext | None = None,
    ) -> dict[str, Any]:
        raise DatasetError(
            "set_dataset is no longer supported because M4 no longer keeps a "
            "global active dataset. Pass dataset explicitly to each tool call."
        )

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True
