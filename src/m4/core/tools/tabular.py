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

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalize_schema_df(schema_df: pd.DataFrame) -> pd.DataFrame:
    """Map backend-specific column layouts to consistent [column_name, data_type, nullable].

    DuckDB returns: name, type, notnull, (cid, dflt_value, pk)
    BigQuery returns: column_name, data_type, is_nullable
    """
    cols = set(schema_df.columns)

    if "name" in cols and "type" in cols:
        # DuckDB layout
        df = pd.DataFrame(
            {
                "column_name": schema_df["name"],
                "data_type": schema_df["type"],
                "nullable": ~schema_df["notnull"].astype(bool)
                if "notnull" in cols
                else True,
            }
        )
    elif "column_name" in cols and "data_type" in cols:
        # BigQuery layout
        df = pd.DataFrame(
            {
                "column_name": schema_df["column_name"],
                "data_type": schema_df["data_type"],
                "nullable": schema_df["is_nullable"].str.upper() != "NO"
                if "is_nullable" in cols
                else True,
            }
        )
    else:
        # Unknown layout — pass through first two columns
        columns = list(schema_df.columns)
        df = pd.DataFrame(
            {
                "column_name": schema_df[columns[0]] if len(columns) > 0 else [],
                "data_type": schema_df[columns[1]] if len(columns) > 1 else [],
                "nullable": True,
            }
        )

    return df


def _generate_ddl(table_name: str, columns_df: pd.DataFrame) -> str:
    """Build a CREATE TABLE DDL string from a normalized columns DataFrame."""
    lines = []
    for _, row in columns_df.iterrows():
        col_def = f"  {row['column_name']} {row['data_type']}"
        if row.get("nullable") is False:
            col_def += " NOT NULL"
        lines.append(col_def)
    body = ",\n".join(lines)
    return f"CREATE TABLE {table_name} (\n{body}\n);"


# Input/Output models for specific tools
@dataclass
class GetDatabaseSchemaInput(ToolInput):
    """Input for get_database_schema tool."""

    include_ddl: bool = False


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
    available tables with descriptions. Works with any dataset that has tabular data.

    Returns:
        dict with 'backend', 'dataset', and 'tables' (name → description) keys
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
                - backend: str - Backend name ('duckdb' or 'bigquery')
                - dataset: str - Active dataset name
                - tables: dict[str, str] - Table name → description
                - ddl: str | None - Combined DDL for all tables (when include_ddl=True)
        """
        backend = get_backend()
        table_names = backend.get_table_list(dataset)

        descriptions = dataset.table_descriptions
        tables = {t: descriptions.get(t, "") for t in table_names}

        result: dict[str, Any] = {
            "backend": backend.name,
            "dataset": dataset.name,
            "tables": tables,
        }

        if params.include_ddl:
            ddl_parts = []
            for table_name in table_names:
                if not validate_table_name(table_name):
                    continue
                schema_result = backend.get_table_info(table_name, dataset)
                if schema_result.success and schema_result.dataframe is not None:
                    columns_df = _normalize_schema_df(schema_result.dataframe)
                    ddl_parts.append(_generate_ddl(table_name, columns_df))
            result["ddl"] = "\n\n".join(ddl_parts)

        return result

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
    specified table. Returns normalized columns and DDL.

    Returns:
        dict with table_name, columns DataFrame, ddl string, and optional sample DataFrame
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
                - table_name: str - Name of the table
                - columns: pd.DataFrame - Normalized [column_name, data_type, nullable]
                - ddl: str - CREATE TABLE DDL string
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

        columns_df = _normalize_schema_df(schema_result.dataframe)
        ddl = _generate_ddl(params.table_name, columns_df)

        result = {
            "table_name": params.table_name,
            "columns": columns_df,
            "ddl": ddl,
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
