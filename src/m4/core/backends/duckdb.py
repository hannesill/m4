"""DuckDB backend implementation for local database queries.

This module provides the DuckDBBackend class that implements the Backend
protocol for executing queries against local DuckDB databases.
"""

import os
from pathlib import Path

import duckdb

from m4.config import get_default_database_path
from m4.core.backends.base import (
    BackendError,
    ConnectionError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)
from m4.core.datasets import DatasetDefinition


class DuckDBBackend:
    """Backend for executing queries against local DuckDB databases.

    This backend connects to DuckDB database files stored locally and
    executes SQL queries against them. It supports all standard SQL
    operations that DuckDB provides.

    Example:
        backend = DuckDBBackend()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        # Execute a query
        result = backend.execute_query(
            "SELECT * FROM hosp_patients LIMIT 5",
            mimic_demo
        )
        print(result.data)

        # Get table list
        tables = backend.get_table_list(mimic_demo)
    """

    def __init__(self, db_path_override: str | Path | None = None):
        """Initialize DuckDB backend.

        Args:
            db_path_override: Optional path to use instead of auto-detection.
                            If provided, this path is used for all queries
                            regardless of the dataset parameter.
        """
        self._db_path_override = (
            Path(db_path_override) if db_path_override else None
        )

    @property
    def name(self) -> str:
        """Get the backend name."""
        return "duckdb"

    def _get_db_path(self, dataset: DatasetDefinition) -> Path:
        """Get the database path for a dataset.

        Priority:
        1. Instance override (db_path_override)
        2. Environment variable M4_DB_PATH
        3. Default path based on dataset configuration

        Args:
            dataset: The dataset definition

        Returns:
            Path to the DuckDB database file

        Raises:
            ConnectionError: If no valid database path can be determined
        """
        # Priority 1: Instance override
        if self._db_path_override:
            return self._db_path_override

        # Priority 2: Environment variable
        env_path = os.getenv("M4_DB_PATH")
        if env_path:
            return Path(env_path)

        # Priority 3: Default based on dataset
        db_path = get_default_database_path(dataset.name)
        if not db_path:
            raise ConnectionError(
                f"Cannot determine database path for dataset '{dataset.name}'",
                backend=self.name,
            )

        return db_path

    def _connect(self, dataset: DatasetDefinition) -> duckdb.DuckDBPyConnection:
        """Create a connection to the DuckDB database.

        Args:
            dataset: The dataset definition

        Returns:
            DuckDB connection object

        Raises:
            ConnectionError: If the database file doesn't exist or can't be opened
        """
        db_path = self._get_db_path(dataset)

        if not db_path.exists():
            raise ConnectionError(
                f"Database file not found: {db_path}. "
                "Please initialize the dataset using 'm4 init'.",
                backend=self.name,
            )

        try:
            return duckdb.connect(str(db_path), read_only=True)
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to DuckDB: {e}",
                backend=self.name,
            )

    def execute_query(self, sql: str, dataset: DatasetDefinition) -> QueryResult:
        """Execute a SQL query against the dataset.

        Args:
            sql: SQL query string
            dataset: The dataset definition

        Returns:
            QueryResult with query output or error
        """
        try:
            conn = self._connect(dataset)
            try:
                df = conn.execute(sql).df()

                if df.empty:
                    return QueryResult(data="No results found", row_count=0)

                row_count = len(df)
                truncated = row_count > 50

                if truncated:
                    data = (
                        df.head(50).to_string(index=False)
                        + f"\n... ({row_count} total rows, showing first 50)"
                    )
                else:
                    data = df.to_string(index=False)

                return QueryResult(
                    data=data,
                    row_count=row_count,
                    truncated=truncated,
                )
            finally:
                conn.close()

        except ConnectionError:
            raise
        except Exception as e:
            error_msg = str(e).lower()

            # Provide specific error types
            if "no such table" in error_msg or ("table" in error_msg and "not found" in error_msg):
                # Try to extract table name from error
                return QueryResult(
                    data="",
                    error=f"Table not found: {e}",
                )

            return QueryResult(
                data="",
                error=str(e),
            )

    def get_table_list(self, dataset: DatasetDefinition) -> list[str]:
        """Get list of available tables in the dataset.

        Args:
            dataset: The dataset definition

        Returns:
            List of table names
        """
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY table_name
        """
        result = self.execute_query(query, dataset)

        if result.error:
            return []

        # Parse table names from the result
        tables = []
        for line in result.data.strip().split("\n"):
            line = line.strip()
            if line and line != "table_name":
                tables.append(line)

        return tables

    def get_table_info(
        self, table_name: str, dataset: DatasetDefinition
    ) -> QueryResult:
        """Get schema information for a specific table.

        Args:
            table_name: Name of the table to inspect
            dataset: The dataset definition

        Returns:
            QueryResult with column information
        """
        # Use PRAGMA table_info for DuckDB
        query = f"PRAGMA table_info('{table_name}')"

        try:
            result = self.execute_query(query, dataset)

            if result.error:
                # Check if it's a table not found error
                error_lower = result.error.lower()
                if "not found" in error_lower or "does not exist" in error_lower:
                    raise TableNotFoundError(table_name, backend=self.name)
                raise QueryExecutionError(result.error, query, backend=self.name)

            return result

        except BackendError:
            raise
        except Exception as e:
            return QueryResult(
                data="",
                error=f"Failed to get table info: {e}",
            )

    def get_sample_data(
        self, table_name: str, dataset: DatasetDefinition, limit: int = 3
    ) -> QueryResult:
        """Get sample rows from a table.

        Args:
            table_name: Name of the table to sample
            dataset: The dataset definition
            limit: Maximum number of rows to return

        Returns:
            QueryResult with sample data
        """
        # Sanitize limit
        limit = max(1, min(limit, 100))

        query = f"SELECT * FROM '{table_name}' LIMIT {limit}"
        return self.execute_query(query, dataset)

    def get_backend_info(self, dataset: DatasetDefinition) -> str:
        """Get human-readable information about the current backend.

        Args:
            dataset: The active dataset definition

        Returns:
            Formatted string with backend details
        """
        try:
            db_path = self._get_db_path(dataset)
        except ConnectionError:
            db_path = "unknown"

        return (
            f"**Current Backend:** DuckDB (local database)\n"
            f"**Active Dataset:** {dataset.name}\n"
            f"**Database Path:** {db_path}"
        )
