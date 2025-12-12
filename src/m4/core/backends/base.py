"""Backend protocol and base types for query execution.

This module defines the abstract Backend protocol that all database backends
must implement. This enables clean separation between the tool layer and
the actual database implementations (DuckDB, BigQuery, etc.).
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from m4.config import logger
from m4.core.datasets import DatasetDefinition


def sanitize_error_message(error: Exception, backend_name: str = "unknown") -> str:
    """Sanitize error message to avoid exposing internal paths or structure.

    This function logs the full error internally for debugging while
    returning a user-friendly message that doesn't leak sensitive details
    like internal file paths, database structure, or system information.

    Args:
        error: The exception that occurred
        backend_name: Name of the backend for logging context

    Returns:
        A sanitized error message safe to return to users
    """
    error_str = str(error).lower()

    # Log full error for debugging (including stack trace if needed)
    logger.debug(f"[{backend_name}] Query execution error: {error}")

    # Return specific but safe messages for common errors
    if "no such table" in error_str or (
        "table" in error_str and "not found" in error_str
    ):
        return "Table not found. Use get_database_schema() to see available tables."

    if (
        "no such column" in error_str
        or "unknown column" in error_str
        or ("column" in error_str and "not found" in error_str)
    ):
        return "Column not found. Use get_table_info('table_name') to see available columns."

    if "syntax error" in error_str or "parse error" in error_str:
        return "SQL syntax error. Please check your query syntax."

    if (
        "permission" in error_str
        or "access denied" in error_str
        or "unauthorized" in error_str
    ):
        return "Permission denied. Check your access credentials."

    if "timeout" in error_str or "timed out" in error_str:
        return "Query timed out. Try a simpler query or add LIMIT clause."

    if "connection" in error_str or "network" in error_str:
        return "Connection error. Please check your network and try again."

    # Generic fallback - don't expose internal details
    return "Query execution failed. Please check your query and try again."


@dataclass
class QueryResult:
    """Result of a query execution.

    Attributes:
        data: The query result as a formatted string
        row_count: Total number of rows returned
        truncated: Whether the result was truncated
        error: Error message if the query failed, None otherwise
    """

    data: str
    row_count: int = 0
    truncated: bool = False
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if the query executed successfully."""
        return self.error is None


@runtime_checkable
class Backend(Protocol):
    """Protocol defining the interface for all database backends.

    Backends must implement this protocol to be usable with M4 tools.
    The protocol uses structural typing (duck typing) so backends don't
    need to explicitly inherit from a base class.

    Example:
        class DuckDBBackend:
            def execute_query(self, sql, dataset):
                # DuckDB-specific implementation
                ...

            def get_table_list(self, dataset):
                # Return list of tables
                ...

        # Usage
        backend = DuckDBBackend()
        result = backend.execute_query("SELECT * FROM patients LIMIT 5", mimic_demo)
    """

    def execute_query(self, sql: str, dataset: DatasetDefinition) -> QueryResult:
        """Execute a SQL query against the dataset.

        Args:
            sql: SQL query string (must be a safe SELECT or PRAGMA query)
            dataset: The dataset definition to query against

        Returns:
            QueryResult with the query output or error message

        Note:
            Implementations should NOT perform SQL validation - that is
            handled at the tool layer before queries reach the backend.
        """
        ...

    def get_table_list(self, dataset: DatasetDefinition) -> list[str]:
        """Get list of available tables in the dataset.

        Args:
            dataset: The dataset definition to query

        Returns:
            List of table names available in the dataset
        """
        ...

    def get_table_info(
        self, table_name: str, dataset: DatasetDefinition
    ) -> QueryResult:
        """Get schema information for a specific table.

        Args:
            table_name: Name of the table to inspect
            dataset: The dataset definition

        Returns:
            QueryResult with column information (name, type, nullable)
        """
        ...

    def get_sample_data(
        self, table_name: str, dataset: DatasetDefinition, limit: int = 3
    ) -> QueryResult:
        """Get sample rows from a table.

        Args:
            table_name: Name of the table to sample
            dataset: The dataset definition
            limit: Maximum number of rows to return (default: 3)

        Returns:
            QueryResult with sample data
        """
        ...

    def get_backend_info(self, dataset: DatasetDefinition) -> str:
        """Get human-readable information about the current backend.

        Args:
            dataset: The active dataset definition

        Returns:
            Formatted string with backend details (type, connection info, etc.)
        """
        ...

    @property
    def name(self) -> str:
        """Get the backend name (e.g., 'duckdb', 'bigquery')."""
        ...


class BackendError(Exception):
    """Base exception for backend errors.

    Attributes:
        message: Human-readable error description
        backend: Name of the backend that raised the error
        recoverable: Whether the error might be resolved by retrying
    """

    def __init__(
        self, message: str, backend: str = "unknown", recoverable: bool = False
    ):
        self.message = message
        self.backend = backend
        self.recoverable = recoverable
        super().__init__(message)


class ConnectionError(BackendError):
    """Raised when the backend cannot connect to the database."""

    def __init__(self, message: str, backend: str = "unknown"):
        super().__init__(message, backend, recoverable=True)


class TableNotFoundError(BackendError):
    """Raised when a requested table does not exist."""

    def __init__(self, table_name: str, backend: str = "unknown"):
        message = f"Table '{table_name}' not found"
        super().__init__(message, backend, recoverable=False)
        self.table_name = table_name


class QueryExecutionError(BackendError):
    """Raised when a query fails to execute."""

    def __init__(self, message: str, sql: str, backend: str = "unknown"):
        super().__init__(message, backend, recoverable=False)
        self.sql = sql
