"""Dataset management tools for M4.

This module provides tools for switching between datasets and listing
available datasets. These tools are always available regardless of
the active dataset.

All tools use config functions directly - no circular dependencies.
"""

import os
from dataclasses import dataclass

from m4.config import (
    detect_available_local_datasets,
    get_active_dataset,
    set_active_dataset,
)
from m4.core.datasets import Capability, DatasetDefinition, DatasetRegistry, Modality
from m4.core.tools.base import ToolInput, ToolOutput


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
    """

    name = "list_datasets"
    description = "📋 List all available medical datasets"
    input_model = ListDatasetsInput
    output_model = ToolOutput

    # Management tools have no capability requirements
    required_modalities: frozenset[Modality] = frozenset()
    required_capabilities: frozenset[Capability] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(
        self, dataset: DatasetDefinition, params: ListDatasetsInput
    ) -> ToolOutput:
        """List all available datasets with their status."""
        active = get_active_dataset() or "(unset)"
        availability = detect_available_local_datasets()
        backend_name = os.getenv("M4_BACKEND", "duckdb")

        if not availability:
            return ToolOutput(result="No datasets detected.")

        output = [f"Active dataset: {active}\n"]
        output.append(
            f"Backend: {'local (DuckDB)' if backend_name == 'duckdb' else 'cloud (BigQuery)'}\n"
        )

        for label, info in availability.items():
            is_active = " (Active)" if label == active else ""
            output.append(f"=== {label.upper()}{is_active} ===")

            parquet_icon = "✅" if info["parquet_present"] else "❌"
            db_icon = "✅" if info["db_present"] else "❌"

            output.append(f"  Local Parquet: {parquet_icon}")
            output.append(f"  Local Database: {db_icon}")

            # BigQuery status
            ds_def = DatasetRegistry.get(label)
            if ds_def:
                bq_status = "✅" if ds_def.bigquery_dataset_ids else "❌"
                output.append(f"  BigQuery Support: {bq_status}")
            output.append("")

        return ToolOutput(result="\n".join(output))

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True


class SetDatasetTool:
    """Tool for switching the active dataset.

    Changes which dataset subsequent queries will run against.
    Automatically handles both DuckDB and BigQuery backends.
    """

    name = "set_dataset"
    description = "🔄 Switch to a different dataset"
    input_model = SetDatasetInput
    output_model = ToolOutput

    # Management tools have no capability requirements
    required_modalities: frozenset[Modality] = frozenset()
    required_capabilities: frozenset[Capability] = frozenset()
    supported_datasets: frozenset[str] | None = None  # Always available

    def invoke(self, dataset: DatasetDefinition, params: SetDatasetInput) -> ToolOutput:
        """Switch to a different dataset."""
        dataset_name = params.dataset_name.lower()
        availability = detect_available_local_datasets()
        backend_name = os.getenv("M4_BACKEND", "duckdb")

        if dataset_name not in availability:
            supported = ", ".join(availability.keys())
            return ToolOutput(
                result=(
                    f"❌ Error: Dataset '{dataset_name}' not found. "
                    f"Supported datasets: {supported}"
                )
            )

        set_active_dataset(dataset_name)

        # Get details about the new dataset to provide context
        info = availability[dataset_name]
        status_msg = f"✅ Active dataset switched to '{dataset_name}'."

        if not info["db_present"] and backend_name == "duckdb":
            status_msg += (
                "\n⚠️ Note: Local database not found. "
                "You may need to run initialization if using DuckDB."
            )

        ds_def = DatasetRegistry.get(dataset_name)
        if ds_def and not ds_def.bigquery_dataset_ids and backend_name == "bigquery":
            status_msg += "\n⚠️ Warning: This dataset is not configured for BigQuery."

        return ToolOutput(result=status_msg)

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True
