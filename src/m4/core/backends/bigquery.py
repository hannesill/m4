"""BigQuery backend implementation for cloud database queries.

This module provides the BigQueryBackend class that implements the Backend
protocol for executing queries against Google BigQuery datasets.
"""

import os
from typing import Any

from m4.core.backends.base import (
    ConnectionError,
    QueryResult,
    TableNotFoundError,
)
from m4.core.datasets import DatasetDefinition


class BigQueryBackend:
    """Backend for executing queries against Google BigQuery.

    This backend connects to BigQuery and executes SQL queries against
    cloud-hosted medical datasets like MIMIC-IV on PhysioNet.

    Example:
        backend = BigQueryBackend()
        mimic_full = DatasetRegistry.get("mimic-iv-full")

        # Execute a query
        result = backend.execute_query(
            "SELECT * FROM `physionet-data.mimiciv_3_1_hosp.patients` LIMIT 5",
            mimic_full
        )
        print(result.data)

    Note:
        Requires the google-cloud-bigquery package to be installed.
        Users must have valid Google Cloud credentials configured.
    """

    def __init__(self, project_id_override: str | None = None):
        """Initialize BigQuery backend.

        Args:
            project_id_override: Optional project ID to use instead of auto-detection.
                               If provided, this project is used for all queries.
        """
        self._project_id_override = project_id_override
        self._client_cache: dict[str, Any] = {"client": None, "project_id": None}

    @property
    def name(self) -> str:
        """Get the backend name."""
        return "bigquery"

    def _get_project_id(self, dataset: DatasetDefinition) -> str:
        """Get the BigQuery project ID for a dataset.

        Priority:
        1. Instance override (project_id_override)
        2. Environment variable M4_PROJECT_ID
        3. Dataset configuration
        4. Default: physionet-data

        Args:
            dataset: The dataset definition

        Returns:
            BigQuery project ID
        """
        # Priority 1: Instance override
        if self._project_id_override:
            return self._project_id_override

        # Priority 2: Environment variable
        env_project = os.getenv("M4_PROJECT_ID")
        if env_project:
            return env_project

        # Priority 3: Dataset configuration
        if dataset.bigquery_project_id:
            return dataset.bigquery_project_id

        # Priority 4: Default
        return "physionet-data"

    def _get_client(self, dataset: DatasetDefinition) -> tuple[Any, str]:
        """Get or create a BigQuery client.

        Clients are cached per project ID to avoid re-initialization overhead.

        Args:
            dataset: The dataset definition

        Returns:
            Tuple of (BigQuery client, project ID)

        Raises:
            ConnectionError: If BigQuery dependencies are not installed
                           or connection fails
        """
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ConnectionError(
                "BigQuery dependencies not found. "
                "Install with: pip install google-cloud-bigquery",
                backend=self.name,
            )

        project_id = self._get_project_id(dataset)

        # Check cache
        if (
            self._client_cache["client"] is not None
            and self._client_cache["project_id"] == project_id
        ):
            return self._client_cache["client"], project_id

        # Create new client
        try:
            client = bigquery.Client(project=project_id)
            self._client_cache["client"] = client
            self._client_cache["project_id"] = project_id
            return client, project_id
        except Exception as e:
            raise ConnectionError(
                f"Failed to initialize BigQuery client for project {project_id}: {e}",
                backend=self.name,
            )

    def execute_query(self, sql: str, dataset: DatasetDefinition) -> QueryResult:
        """Execute a SQL query against BigQuery.

        Args:
            sql: SQL query string
            dataset: The dataset definition

        Returns:
            QueryResult with query output or error
        """
        try:
            from google.cloud import bigquery as bq

            client, _ = self._get_client(dataset)

            job_config = bq.QueryJobConfig()
            query_job = client.query(sql, job_config=job_config)
            df = query_job.to_dataframe()

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

        except ConnectionError:
            raise
        except Exception as e:
            error_msg = str(e).lower()

            # Provide specific error types
            if "not found" in error_msg and ("table" in error_msg or "dataset" in error_msg):
                return QueryResult(
                    data="",
                    error=f"Table or dataset not found: {e}",
                )

            return QueryResult(
                data="",
                error=str(e),
            )

    def get_table_list(self, dataset: DatasetDefinition) -> list[str]:
        """Get list of available tables in the dataset.

        Returns fully qualified table names suitable for direct use in queries.

        Args:
            dataset: The dataset definition

        Returns:
            List of fully qualified table names (e.g., `project.dataset.table`)
        """
        if not dataset.bigquery_dataset_ids:
            return []

        project_id = self._get_project_id(dataset)
        tables = []

        for dataset_id in dataset.bigquery_dataset_ids:
            query = f"""
            SELECT CONCAT('`{project_id}.{dataset_id}.', table_name, '`') as table_name
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
            """
            result = self.execute_query(query, dataset)

            if result.error:
                continue

            # Parse table names from the result
            for line in result.data.strip().split("\n"):
                line = line.strip()
                if line and line != "table_name":
                    tables.append(line)

        return sorted(tables)

    def get_table_info(
        self, table_name: str, dataset: DatasetDefinition
    ) -> QueryResult:
        """Get schema information for a specific table.

        Args:
            table_name: Name of the table (simple or fully qualified)
            dataset: The dataset definition

        Returns:
            QueryResult with column information
        """
        # Handle both simple and qualified table names
        is_qualified = "." in table_name

        if is_qualified:
            # Parse qualified name: `project.dataset.table` or project.dataset.table
            clean_name = table_name.strip("`")
            parts = clean_name.split(".")

            if len(parts) != 3:
                return QueryResult(
                    data="",
                    error=(
                        f"Invalid qualified table name: {table_name}. "
                        "Expected format: project.dataset.table"
                    ),
                )

            project_id = parts[0]
            dataset_id = parts[1]
            simple_name = parts[2]

            query = f"""
            SELECT column_name, data_type, is_nullable
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{simple_name}'
            ORDER BY ordinal_position
            """

            result = self.execute_query(query, dataset)
            if result.error or "No results found" in result.data:
                raise TableNotFoundError(table_name, backend=self.name)
            return result

        # Simple table name - search in configured datasets
        if not dataset.bigquery_dataset_ids:
            return QueryResult(
                data="",
                error="No BigQuery datasets configured for this dataset",
            )

        project_id = self._get_project_id(dataset)

        for dataset_id in dataset.bigquery_dataset_ids:
            query = f"""
            SELECT column_name, data_type, is_nullable
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
            """

            result = self.execute_query(query, dataset)
            if not result.error and "No results found" not in result.data:
                return result

        raise TableNotFoundError(table_name, backend=self.name)

    def get_sample_data(
        self, table_name: str, dataset: DatasetDefinition, limit: int = 3
    ) -> QueryResult:
        """Get sample rows from a table.

        Args:
            table_name: Name of the table (simple or fully qualified)
            dataset: The dataset definition
            limit: Maximum number of rows to return

        Returns:
            QueryResult with sample data
        """
        # Sanitize limit
        limit = max(1, min(limit, 100))

        # Handle qualified vs simple names
        is_qualified = "." in table_name

        if is_qualified:
            clean_name = table_name.strip("`")
            full_name = f"`{clean_name}`"
            query = f"SELECT * FROM {full_name} LIMIT {limit}"
            return self.execute_query(query, dataset)

        # Simple name - find in configured datasets
        if not dataset.bigquery_dataset_ids:
            return QueryResult(
                data="",
                error="No BigQuery datasets configured for this dataset",
            )

        project_id = self._get_project_id(dataset)

        for dataset_id in dataset.bigquery_dataset_ids:
            full_name = f"`{project_id}.{dataset_id}.{table_name}`"
            query = f"SELECT * FROM {full_name} LIMIT {limit}"

            result = self.execute_query(query, dataset)
            if not result.error:
                return result

        return QueryResult(
            data="",
            error=f"Table '{table_name}' not found in any configured dataset",
        )

    def get_backend_info(self, dataset: DatasetDefinition) -> str:
        """Get human-readable information about the current backend.

        Args:
            dataset: The active dataset definition

        Returns:
            Formatted string with backend details
        """
        project_id = self._get_project_id(dataset)
        dataset_ids = ", ".join(dataset.bigquery_dataset_ids) if dataset.bigquery_dataset_ids else "none configured"

        return (
            f"**Current Backend:** BigQuery (cloud database)\n"
            f"**Active Dataset:** {dataset.name}\n"
            f"**Project ID:** {project_id}\n"
            f"**Dataset IDs:** {dataset_ids}"
        )
