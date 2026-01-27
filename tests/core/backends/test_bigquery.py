"""Tests for m4.core.backends.bigquery module.

Tests cover:
- BigQueryBackend initialization
- Project ID resolution
- Query execution (mocked)
- Table operations (mocked)
- Error handling
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from m4.core.backends.base import ConnectionError
from m4.core.backends.bigquery import BigQueryBackend
from m4.core.datasets import DatasetDefinition, Modality


@pytest.fixture
def test_dataset():
    """Create a test dataset definition with BigQuery config."""
    return DatasetDefinition(
        name="test-bq-dataset",
        modalities={Modality.TABULAR},
        bigquery_project_id="test-project",
        bigquery_dataset_ids=["test_dataset_1", "test_dataset_2"],
    )


@pytest.fixture
def mock_bigquery():
    """Mock the BigQuery client and module."""
    with patch("m4.core.backends.bigquery.BigQueryBackend._get_client") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


class TestBigQueryBackendInit:
    """Test BigQueryBackend initialization."""

    def test_default_init(self):
        """Test default initialization."""
        backend = BigQueryBackend()

        assert backend.name == "bigquery"
        assert backend._project_id_override is None

    def test_init_with_project_override(self):
        """Test initialization with project ID override."""
        backend = BigQueryBackend(project_id_override="custom-project")

        assert backend._project_id_override == "custom-project"


class TestBigQueryProjectResolution:
    """Test project ID resolution."""

    def test_override_takes_priority(self, test_dataset):
        """Test that project override takes highest priority."""
        backend = BigQueryBackend(project_id_override="override-project")

        project_id = backend._get_project_id(test_dataset)

        assert project_id == "override-project"

    def test_env_var_takes_second_priority(self, test_dataset):
        """Test that M4_PROJECT_ID env var takes second priority."""
        with patch.dict(os.environ, {"M4_PROJECT_ID": "env-project"}):
            backend = BigQueryBackend()  # No override

            project_id = backend._get_project_id(test_dataset)

            assert project_id == "env-project"

    def test_dataset_config_used_as_fallback(self, test_dataset):
        """Test that dataset config is used when no override."""
        # Clear env var if set
        env_backup = os.environ.pop("M4_PROJECT_ID", None)
        try:
            backend = BigQueryBackend()

            project_id = backend._get_project_id(test_dataset)

            assert project_id == "test-project"
        finally:
            if env_backup:
                os.environ["M4_PROJECT_ID"] = env_backup

    def test_default_project_when_no_config(self):
        """Test default project when dataset has no config."""
        dataset = DatasetDefinition(
            name="no-bq-dataset",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
        )

        env_backup = os.environ.pop("M4_PROJECT_ID", None)
        try:
            backend = BigQueryBackend()

            project_id = backend._get_project_id(dataset)

            assert project_id == "physionet-data"  # Default
        finally:
            if env_backup:
                os.environ["M4_PROJECT_ID"] = env_backup


class TestBigQueryClientCaching:
    """Test BigQuery client caching."""

    def test_client_cached(self):
        """Test that client is cached for same project."""
        with patch.dict("sys.modules", {"google.cloud.bigquery": MagicMock()}):
            backend = BigQueryBackend()

            # First call creates client
            mock_bq = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client

            with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
                with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                    # Manually set up cache to simulate behavior
                    backend._client_cache = {
                        "client": mock_client,
                    }

                    # Second call should use cache
                    client = backend._get_client()

                    assert client == mock_client
                    # Client should not be created again
                    mock_bq.Client.assert_not_called()


class TestBigQueryQueryExecution:
    """Test query execution with mocked BigQuery."""

    def test_successful_query(self, test_dataset, mock_bigquery):
        """Test executing a successful query."""
        import pandas as pd

        # Set up mock to return a DataFrame
        mock_df = pd.DataFrame({"id": [1, 2, 3], "value": ["a", "b", "c"]})
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery
                }

                result = backend.execute_query("SELECT * FROM test", test_dataset)

                assert result.success is True
                assert result.row_count == 3
                assert result.dataframe is not None
                assert "id" in result.dataframe.columns

    def test_empty_result(self, test_dataset, mock_bigquery):
        """Test query returning empty results."""
        import pandas as pd

        # Set up mock to return empty DataFrame
        mock_df = pd.DataFrame()
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery
                }

                result = backend.execute_query("SELECT * FROM empty", test_dataset)

                assert result.success is True
                assert result.dataframe is not None
                assert result.dataframe.empty
                assert result.row_count == 0


class TestBigQueryTableOperations:
    """Test table listing and info operations."""

    def test_get_table_list_empty_config(self):
        """Test table list when no BigQuery datasets configured."""
        dataset = DatasetDefinition(
            name="no-bq",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
        )

        backend = BigQueryBackend()
        tables = backend.get_table_list(dataset)

        assert tables == []

    def test_get_table_info_qualified_name(self, test_dataset, mock_bigquery):
        """Test getting table info with fully qualified name."""
        import pandas as pd

        # Mock column info result
        mock_df = pd.DataFrame(
            {
                "column_name": ["id", "name"],
                "data_type": ["INT64", "STRING"],
                "is_nullable": ["NO", "YES"],
            }
        )
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery
                }

                result = backend.get_table_info(
                    "`test-project.test_dataset.patients`", test_dataset
                )

                assert result.success is True
                assert result.dataframe is not None
                assert "column_name" in result.dataframe.columns

    def test_get_table_info_invalid_qualified_name(self, test_dataset):
        """Test error handling for invalid qualified name."""
        backend = BigQueryBackend()

        result = backend.get_table_info("invalid.name", test_dataset)

        assert result.success is False
        assert "Invalid" in result.error


class TestBigQueryBackendInfo:
    """Test backend info generation."""

    def test_backend_info(self, test_dataset):
        """Test getting backend info."""
        backend = BigQueryBackend()

        info = backend.get_backend_info(test_dataset)

        assert "BigQuery" in info
        assert test_dataset.name in info
        assert "test-project" in info
        assert "test_dataset_1" in info

    def test_backend_info_no_datasets(self):
        """Test backend info when no datasets configured."""
        dataset = DatasetDefinition(
            name="empty-bq",
            bigquery_project_id="test-project",
            bigquery_dataset_ids=[],
        )

        backend = BigQueryBackend()
        info = backend.get_backend_info(dataset)

        assert "BigQuery" in info
        assert "none configured" in info


class TestBigQueryConnectionError:
    """Test connection error handling."""

    def test_missing_bigquery_package(self, test_dataset):
        """Test error when _get_client raises ConnectionError."""
        backend = BigQueryBackend()

        # Clear cache to force new client creation
        backend._client_cache = {"client": None, "project_id": None}

        # Mock _get_client to raise ConnectionError
        with patch.object(
            backend,
            "_get_client",
            side_effect=ConnectionError(
                "BigQuery dependencies not found", backend="bigquery"
            ),
        ):
            with pytest.raises(ConnectionError) as exc_info:
                backend.execute_query("SELECT 1", test_dataset)

            assert "dependencies" in str(exc_info.value).lower()
