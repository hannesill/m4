"""Tabular data tools for querying structured medical databases.

This module provides the core tools for querying tabular medical data:
- get_database_schema: List available tables
- get_table_info: Inspect table structure
- execute_query: Run SQL queries

These tools are intentionally minimal and dataset-agnostic. The LLM handles
adaptation to different datasets via schema introspection and adaptive SQL.

Architecture Note:
    Tools return native Python types. The MCP server serializes these
    for the protocol; the Python API receives them directly.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from m4.core.backends import get_backend
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import QueryError, SecurityError
from m4.core.tools.base import ToolInput
from m4.core.validation import (
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

    Returns:
        dict with 'backend_info' and 'tables' keys
    """

    name = "get_database_schema"
    description = "List all available tables in the database"
    input_model = GetDatabaseSchemaInput

    # Compatibility constraints
    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetDatabaseSchemaInput
    ) -> dict[str, Any]:
        """List available tables using the backend.

        Returns:
            dict with:
                - backend_info: str - Backend description
                - tables: list[str] - List of table names
        """
        backend = get_backend()
        tables = backend.get_table_list(dataset)

        return {
            "backend_info": backend.get_backend_info(dataset),
            "tables": tables,
        }

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

    Returns:
        dict with table metadata, schema DataFrame, and optional sample DataFrame
    """

    name = "get_table_info"
    description = "Get detailed information about a specific table"
    input_model = GetTableInfoInput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetTableInfoInput
    ) -> dict[str, Any]:
        """Get table structure and sample data using the backend.

        Returns:
            dict with:
                - backend_info: str - Backend description
                - table_name: str - Name of the table
                - schema: pd.DataFrame - Column information
                - sample: pd.DataFrame | None - Sample rows (if requested)

        Raises:
            QueryError: If table doesn't exist or query fails
        """
        backend = get_backend()

        # Validate table name
        if not validate_table_name(params.table_name):
            raise QueryError(f"Invalid table name '{params.table_name}'")

        # Get table schema
        schema_result = backend.get_table_info(params.table_name, dataset)
        if not schema_result.success:
            raise QueryError(schema_result.error or "Failed to get table info")

        result = {
            "backend_info": backend.get_backend_info(dataset),
            "table_name": params.table_name,
            "schema": schema_result.dataframe,
            "sample": None,
        }

        # Get sample data if requested
        if params.show_sample:
            sample_result = backend.get_sample_data(params.table_name, dataset, limit=3)
            if sample_result.success:
                result["sample"] = sample_result.dataframe

        return result

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

    Returns:
        pd.DataFrame with query results
    """

    name = "execute_query"
    description = "Execute SQL queries to analyze data"
    input_model = ExecuteQueryInput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: ExecuteQueryInput
    ) -> pd.DataFrame:
        """Execute a SQL query with safety validation.

        Returns:
            pd.DataFrame with query results

        Raises:
            SecurityError: If query violates security constraints
            QueryError: If query execution fails
        """
        # Validate query first
        safe, msg = is_safe_query(params.sql_query)
        if not safe:
            raise SecurityError(msg, query=params.sql_query)

        backend = get_backend()
        result = backend.execute_query(params.sql_query, dataset)

        if not result.success:
            raise QueryError(result.error or "Unknown error", sql=params.sql_query)

        return result.dataframe if result.dataframe is not None else pd.DataFrame()

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True
