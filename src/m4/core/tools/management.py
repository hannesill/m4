"""Dataset management tools for M4.

This module provides tools for switching between datasets and listing
available datasets. These tools are always available regardless of
the active dataset.
"""

from dataclasses import dataclass

from m4.core.datasets import Capability, DatasetDefinition, Modality
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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._list_datasets_internal()
        return ToolOutput(result=result)

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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._set_dataset_internal(params.dataset_name)
        return ToolOutput(result=result)

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Management tools are always compatible."""
        return True
