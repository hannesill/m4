"""Dataset management tools for M4.

This module provides tools for switching between datasets and listing
available datasets. These tools are always available regardless of
the active dataset.

All tools use config functions directly - no circular dependencies.

Architecture Note:
    Tools return native Python types. The MCP server serializes these
    for the protocol; the Python API receives them directly.
"""

import os
from dataclasses import dataclass
from typing import Any

from m4.config import (
    detect_available_local_datasets,
    get_active_dataset,
    set_active_dataset,
)
from m4.core.datasets import DatasetDefinition, DatasetRegistry, Modality
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
        dict with active dataset, backend info, and dataset availability
    """

    name = "list_datasets"
    description = "📋 List all available medical datasets"
    input_model = ListDatasetsInput

    # Management tools have no modality requirements - always available
    required_modalities: frozenset[Modality] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(
        self, dataset: DatasetDefinition, params: ListDatasetsInput
    ) -> dict[str, Any]:
        """List all available datasets with their status.

        Returns:
            dict with:
                - active_dataset: str | None - Currently active dataset
                - backend: str - Backend type (duckdb or bigquery)
                - datasets: dict[str, dict] - Dataset availability info
        """
        active = get_active_dataset()
        availability = detect_available_local_datasets()
        backend_name = os.getenv("M4_BACKEND", "duckdb")

        datasets_info: dict[str, dict] = {}

        for label, info in availability.items():
            ds_def = DatasetRegistry.get(label)
            datasets_info[label] = {
                "is_active": label == active,
                "parquet_present": info["parquet_present"],
                "db_present": info["db_present"],
                "bigquery_support": bool(ds_def and ds_def.bigquery_dataset_ids),
                "modalities": ([m.name for m in ds_def.modalities] if ds_def else []),
            }

        return {
            "active_dataset": active,
            "backend": backend_name,
            "datasets": datasets_info,
        }

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True


class SetDatasetTool:
    """Tool for switching the active dataset.

    Changes which dataset subsequent queries will run against.
    Automatically handles both DuckDB and BigQuery backends.

    Returns:
        dict with new dataset info and any warnings
    """

    name = "set_dataset"
    description = "🔄 Switch to a different dataset"
    input_model = SetDatasetInput

    # Management tools have no modality requirements - always available
    required_modalities: frozenset[Modality] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(
        self, dataset: DatasetDefinition, params: SetDatasetInput
    ) -> dict[str, Any]:
        """Switch to a different dataset.

        Returns:
            dict with:
                - dataset_name: str - New active dataset
                - db_present: bool - Whether local DB exists
                - bigquery_support: bool - Whether BigQuery is configured
                - modalities: list[str] - Available modalities
                - warnings: list[str] - Any warnings

        Raises:
            DatasetError: If dataset doesn't exist
        """
        dataset_name = params.dataset_name.lower()
        availability = detect_available_local_datasets()
        backend_name = os.getenv("M4_BACKEND", "duckdb")

        if dataset_name not in availability:
            supported = ", ".join(availability.keys())
            raise DatasetError(
                f"Dataset '{dataset_name}' not found. Supported datasets: {supported}",
                dataset_name=dataset_name,
            )

        set_active_dataset(dataset_name)

        # Get details about the new dataset
        info = availability[dataset_name]
        ds_def = DatasetRegistry.get(dataset_name)

        warnings: list[str] = []

        if not info["db_present"] and backend_name == "duckdb":
            warnings.append(
                "Local database not found. "
                "You may need to run initialization if using DuckDB."
            )

        if ds_def and not ds_def.bigquery_dataset_ids and backend_name == "bigquery":
            warnings.append("This dataset is not configured for BigQuery.")

        return {
            "dataset_name": dataset_name,
            "db_present": info["db_present"],
            "bigquery_support": bool(ds_def and ds_def.bigquery_dataset_ids),
            "modalities": [m.name for m in ds_def.modalities] if ds_def else [],
            "warnings": warnings,
        }

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True
