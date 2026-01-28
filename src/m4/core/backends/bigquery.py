"""BigQuery backend implementation for cloud database queries.

This module provides the BigQueryBackend class that implements the Backend
protocol for executing queries against Google BigQuery datasets.
"""

import os
import re
from typing import Any

from m4.core.backends.base import (
    ConnectionError,
    QueryResult,
    TableNotFoundError,
    sanitize_error_message,
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

        NOTE: This is NOT the project_id of the user (the one billed for the queries),
        but rather the project_id that hosts the dataset.

        Priority:
        1. Instance override (project_id_override)
        2. Dataset configuration
        3. Default: physionet-data

        Args:
            dataset: The dataset definition

        Returns:
            BigQuery project ID
        """
        # Priority 1: Instance override
        if self._project_id_override:
            return self._project_id_override

        # Priority 2: Dataset configuration
        if dataset.bigquery_project_id:
            return dataset.bigquery_project_id

        # Priority 3: Default
        return "physionet-data"

    def _get_client(self) -> Any:
        """Get or create a BigQuery client.

        Clients are cached to avoid re-initialization overhead.

        Returns:
            BigQuery client

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

        project_id = os.getenv("M4_PROJECT_ID", None)

        # Check cache
        if (
            self._client_cache["client"] is not None
            and self._client_cache["project_id"] == project_id
        ):
            return self._client_cache["client"]

        # Create new client
        # We initialize the client without it to allow for ambient credential detection
        # (gcloud default project), as the project_id is the billing project rather than
        # the target project.

        try:
            if project_id:
                client = bigquery.Client(project=project_id)
            else:
                client = bigquery.Client()
            # Use the resolved project ID for caching, even if client is project-agnostic
            self._client_cache["client"] = client
            self._client_cache["project_id"] = project_id
            return client
        except Exception as e:
            raise ConnectionError(
                f"Failed to initialize BigQuery client: {e}",
                backend=self.name,
            )

    def _translate_canonical_to_bq(self, sql: str, dataset: DatasetDefinition) -> str:
        """Translate canonical schema.table names to fully-qualified BigQuery names.

        For each entry in dataset.bigquery_schema_mapping, replaces canonical
        schema.table references with backtick-wrapped `project.bq_dataset.table`.
        Names already wrapped in backticks are left untouched.

        Args:
            sql: SQL string potentially containing canonical schema.table references
            dataset: The dataset definition with bigquery_schema_mapping

        Returns:
            SQL string with canonical names replaced by BigQuery fully-qualified names
        """
        if not dataset.bigquery_schema_mapping:
            return sql

        project_id = self._get_project_id(dataset)

        for canonical_schema, bq_dataset_id in dataset.bigquery_schema_mapping.items():
            pattern = rf"(?<![.\w`]){re.escape(canonical_schema)}\.(\w+)"
            replacement = rf"`{project_id}.{bq_dataset_id}.\1`"
            sql = re.sub(pattern, replacement, sql)

        return sql

    def execute_query(self, sql: str, dataset: DatasetDefinition) -> QueryResult:
        """Execute a SQL query against BigQuery.

        Args:
            sql: SQL query string
            dataset: The dataset definition

        Returns:
            QueryResult with query output as native DataFrame
        """
        sql = self._translate_canonical_to_bq(sql, dataset)
        try:
            import pandas as pd
            from google.cloud import bigquery as bq

            client = self._get_client()

            job_config = bq.QueryJobConfig()
            query_job = client.query(sql, job_config=job_config)
            df = query_job.to_dataframe()

            if df.empty:
                return QueryResult(dataframe=pd.DataFrame(), row_count=0)

            row_count = len(df)
            truncated = row_count > 50

            return QueryResult(
                dataframe=df,
                row_count=row_count,
                truncated=truncated,
            )

        except ConnectionError:
            raise
        except Exception as e:
            # Use sanitized error message to avoid exposing internal details
            return QueryResult(
                dataframe=None,
                error=sanitize_error_message(e, self.name),
            )

    def get_table_list(self, dataset: DatasetDefinition) -> list[str]:
        """Get list of available tables in the dataset.

        Returns canonical schema.table names (e.g., mimiciv_hosp.patients).

        Args:
            dataset: The dataset definition

        Returns:
            List of canonical table names in schema.table format
        """
        if not dataset.bigquery_dataset_ids:
            return []

        project_id = self._get_project_id(dataset)
        tables = []

        # Build reverse mapping: bq_dataset_id -> canonical_schema
        reverse_mapping = {v: k for k, v in dataset.bigquery_schema_mapping.items()}

        for dataset_id in dataset.bigquery_dataset_ids:
            query = f"""
            SELECT table_name
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
            """
            result = self.execute_query(query, dataset)

            if result.error or result.dataframe is None:
                continue

            # Map BQ dataset ID to canonical schema, fall back to dataset ID
            canonical_schema = reverse_mapping.get(dataset_id, dataset_id)

            for table in result.dataframe["table_name"].tolist():
                tables.append(f"{canonical_schema}.{table}")

        return sorted(tables)

    def get_table_info(
        self, table_name: str, dataset: DatasetDefinition
    ) -> QueryResult:
        """Get schema information for a specific table.

        Args:
            table_name: Name of the table. Accepts:
                - Canonical format: schema.table (e.g., mimiciv_hosp.patients)
                - Backtick-wrapped BQ format: `project.dataset.table`
                - Simple name: table (searches all configured datasets)
            dataset: The dataset definition

        Returns:
            QueryResult with column information as DataFrame
        """
        has_backticks = "`" in table_name
        has_dot = "." in table_name

        if has_backticks or has_dot:
            # Qualified name - parse components
            if has_backticks:
                # Backtick-wrapped BQ format: `project.dataset.table`
                clean_name = table_name.strip("`")
                parts = clean_name.split(".")
                if len(parts) != 3:
                    return QueryResult(
                        dataframe=None,
                        error=(
                            f"Invalid qualified table name: {table_name}. "
                            "Expected format: `project.dataset.table`"
                        ),
                    )
                project_id, dataset_id, simple_name = parts
            else:
                parts = table_name.split(".")
                if len(parts) == 2:
                    # Canonical format: schema.table
                    canonical_schema, simple_name = parts
                    project_id = self._get_project_id(dataset)
                    dataset_id = dataset.bigquery_schema_mapping.get(
                        canonical_schema, canonical_schema
                    )
                elif len(parts) == 3:
                    # Legacy 3-part: project.dataset.table
                    project_id, dataset_id, simple_name = parts
                else:
                    return QueryResult(
                        dataframe=None,
                        error=(
                            f"Invalid table name: {table_name}. "
                            "Expected format: schema.table or "
                            "`project.dataset.table`"
                        ),
                    )

            query = f"""
            SELECT column_name, data_type, is_nullable
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{simple_name}'
            ORDER BY ordinal_position
            """

            result = self.execute_query(query, dataset)
            if result.error or result.dataframe is None or result.dataframe.empty:
                raise TableNotFoundError(table_name, backend=self.name)
            return result

        # Simple table name - search in configured datasets
        if not dataset.bigquery_dataset_ids:
            return QueryResult(
                dataframe=None,
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
            if (
                not result.error
                and result.dataframe is not None
                and not result.dataframe.empty
            ):
                return result

        raise TableNotFoundError(table_name, backend=self.name)

    def get_sample_data(
        self, table_name: str, dataset: DatasetDefinition, limit: int = 3
    ) -> QueryResult:
        """Get sample rows from a table.

        Args:
            table_name: Name of the table. Accepts:
                - Canonical format: schema.table (e.g., mimiciv_hosp.patients)
                - Backtick-wrapped BQ format: `project.dataset.table`
                - Simple name: table (searches all configured datasets)
            dataset: The dataset definition
            limit: Maximum number of rows to return

        Returns:
            QueryResult with sample data as DataFrame
        """
        # Sanitize limit
        limit = max(1, min(limit, 100))

        has_backticks = "`" in table_name
        has_dot = "." in table_name

        if has_backticks or has_dot:
            if has_backticks:
                # Backtick-wrapped BQ format
                clean_name = table_name.strip("`")
                full_name = f"`{clean_name}`"
            else:
                parts = table_name.split(".")
                if len(parts) == 2:
                    # Canonical format: schema.table
                    canonical_schema, simple_name = parts
                    project_id = self._get_project_id(dataset)
                    bq_dataset_id = dataset.bigquery_schema_mapping.get(
                        canonical_schema, canonical_schema
                    )
                    full_name = f"`{project_id}.{bq_dataset_id}.{simple_name}`"
                elif len(parts) == 3:
                    # Legacy 3-part: project.dataset.table
                    full_name = f"`{'.'.join(parts)}`"
                else:
                    return QueryResult(
                        dataframe=None,
                        error=(
                            f"Invalid table name: {table_name}. "
                            "Expected format: schema.table or "
                            "`project.dataset.table`"
                        ),
                    )

            query = f"SELECT * FROM {full_name} LIMIT {limit}"
            return self.execute_query(query, dataset)

        # Simple name - find in configured datasets
        if not dataset.bigquery_dataset_ids:
            return QueryResult(
                dataframe=None,
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
            dataframe=None,
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
        dataset_ids = (
            ", ".join(dataset.bigquery_dataset_ids)
            if dataset.bigquery_dataset_ids
            else "none configured"
        )

        return (
            f"**Current Backend:** BigQuery (cloud database)\n"
            f"**Active Dataset:** {dataset.name}\n"
            f"**Project ID:** {project_id}\n"
            f"**Dataset IDs:** {dataset_ids}"
        )
