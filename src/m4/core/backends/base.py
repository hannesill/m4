"""Backend protocol and base types for query execution.

This module defines the abstract Backend protocol that all database backends
must implement. This enables clean separation between the tool layer and
the actual database implementations (DuckDB, BigQuery, etc.).
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from m4.core.datasets import DatasetDefinition


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
