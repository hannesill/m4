"""Tabular data tools for querying structured medical databases.

This module provides the core tools for querying tabular medical data:
- get_database_schema: List available tables
- get_table_info: Inspect table structure
- execute_query: Run SQL queries

These tools are intentionally minimal and dataset-agnostic. The LLM handles
adaptation to different datasets via schema introspection and adaptive SQL.
"""

from dataclasses import dataclass

from m4.core.backends import get_backend
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.tools.base import ToolInput, ToolOutput
from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
    validate_table_name,
)


# Input/Output models for specific tools
@dataclass
class GetDatabaseSchemaInput(ToolInput):
    """Input for get_database_schema tool."""

    pass  # No parameters needed


@dataclass
class GetTableInfoInput(ToolInput):
    """Input for get_table_info tool."""

    table_name: str
    show_sample: bool = True


@dataclass
class ExecuteQueryInput(ToolInput):
    """Input for execute_query tool."""

    sql_query: str


# Tool implementations
class GetDatabaseSchemaTool:
    """Tool for listing available tables in the database.

    This tool provides schema introspection capabilities, showing all
    available tables. Works with any dataset that has tabular data.
    """

    name = "get_database_schema"
    description = "List all available tables in the database"
    input_model = GetDatabaseSchemaInput
    output_model = ToolOutput

    # Compatibility constraints
    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetDatabaseSchemaInput
    ) -> ToolOutput:
        """List available tables using the backend."""
        backend = get_backend()
        backend_info = backend.get_backend_info(dataset)

        try:
            tables = backend.get_table_list(dataset)
            if not tables:
                return ToolOutput(
                    result=f"{backend_info}\n**Available Tables:**\nNo tables found"
                )

            table_list = "\n".join(f"  {t}" for t in tables)
            return ToolOutput(
                result=f"{backend_info}\n**Available Tables:**\n{table_list}"
            )
        except Exception as e:
            return ToolOutput(result=f"{backend_info}\nError: {e}")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if this tool is compatible with the given dataset."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True


class GetTableInfoTool:
    """Tool for inspecting table structure and sample data.

    Shows column names, data types, and optionally sample rows for a
    specified table.
    """

    name = "get_table_info"
    description = "Get detailed information about a specific table"
    input_model = GetTableInfoInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetTableInfoInput
    ) -> ToolOutput:
        """Get table structure and sample data using the backend."""
        backend = get_backend()
        backend_info = backend.get_backend_info(dataset)

        # Validate table name
        if not validate_table_name(params.table_name):
            return ToolOutput(
                result=f"{backend_info}\nError: Invalid table name '{params.table_name}'"
            )

        try:
            # Get table schema
            schema_result = backend.get_table_info(params.table_name, dataset)
            if not schema_result.success:
                return ToolOutput(result=f"{backend_info}\n{schema_result.error}")

            result_parts = [
                backend_info,
                f"**Table:** {params.table_name}",
                "",
                "**Column Information:**",
                schema_result.data,
            ]

            # Get sample data if requested
            if params.show_sample:
                sample_result = backend.get_sample_data(
                    params.table_name, dataset, limit=3
                )
                if sample_result.success:
                    result_parts.extend(
                        [
                            "",
                            "**Sample Data (first 3 rows):**",
                            sample_result.data,
                        ]
                    )

            return ToolOutput(result="\n".join(result_parts))
        except Exception as e:
            return ToolOutput(
                result=f"{backend_info}\nError examining table '{params.table_name}': {e}"
            )

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True


class ExecuteQueryTool:
    """Tool for executing SQL queries on the dataset.

    Allows running SELECT queries with built-in safety validation
    to prevent SQL injection and unauthorized operations.
    """

    name = "execute_query"
    description = "Execute SQL queries to analyze data"
    input_model = ExecuteQueryInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: ExecuteQueryInput
    ) -> ToolOutput:
        """Execute a SQL query with safety validation."""
        # Validate query first
        safe, msg = is_safe_query(params.sql_query)
        if not safe:
            return ToolOutput(result=f"**Security Error:** {msg}")

        backend = get_backend()

        try:
            result = backend.execute_query(params.sql_query, dataset)
            if result.success:
                return ToolOutput(result=result.data)
            else:
                return ToolOutput(
                    result=format_error_with_guidance(result.error or "Unknown error")
                )
        except Exception as e:
            return ToolOutput(result=format_error_with_guidance(str(e)))

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True
