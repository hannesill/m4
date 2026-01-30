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
        bigquery_schema_mapping={
            "test_schema_1": "test_dataset_1",
            "test_schema_2": "test_dataset_2",
        },
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
                        "project_id": None,
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
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

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
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

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
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

                result = backend.get_table_info(
                    "`test-project.test_dataset.patients`", test_dataset
                )

                assert result.success is True
                assert result.dataframe is not None
                assert "column_name" in result.dataframe.columns

    def test_get_table_info_invalid_qualified_name(self, test_dataset):
        """Test error handling for invalid qualified name (too many parts)."""
        backend = BigQueryBackend()

        result = backend.get_table_info("a.b.c.d", test_dataset)

        assert result.success is False
        assert "Invalid" in result.error


class TestBigQueryCanonicalTranslation:
    """Test canonical schema.table to BigQuery name translation."""

    def test_translate_canonical_to_bq(self, test_dataset):
        """Test translating canonical schema.table to BQ fully-qualified name."""
        backend = BigQueryBackend()
        sql = "SELECT * FROM test_schema_1.patients LIMIT 10"

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert result == (
            "SELECT * FROM `test-project.test_dataset_1.patients` LIMIT 10"
        )

    def test_translate_multiple_tables(self, test_dataset):
        """Test translating multiple canonical references in one query."""
        backend = BigQueryBackend()
        sql = (
            "SELECT * FROM test_schema_1.patients p "
            "JOIN test_schema_2.admissions a ON p.id = a.patient_id"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert "`test-project.test_dataset_1.patients`" in result
        assert "`test-project.test_dataset_2.admissions`" in result

    def test_translate_backticks_passthrough(self, test_dataset):
        """Test that backtick-wrapped names pass through untouched."""
        backend = BigQueryBackend()
        sql = "SELECT * FROM `test-project.test_dataset_1.patients` LIMIT 10"

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert result == sql

    def test_translate_empty_mapping(self):
        """Test that empty mapping returns SQL unchanged."""
        dataset = DatasetDefinition(
            name="no-mapping",
            bigquery_project_id="test-project",
            bigquery_dataset_ids=["ds1"],
            bigquery_schema_mapping={},
        )
        backend = BigQueryBackend()
        sql = "SELECT * FROM some_schema.patients"

        result = backend._translate_canonical_to_bq(sql, dataset)

        assert result == sql

    def test_translate_canonical_mimiciv_example(self):
        """Test with realistic MIMIC-IV schema mapping."""
        dataset = DatasetDefinition(
            name="mimic-iv-test",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_hosp"],
            bigquery_schema_mapping={"mimiciv_hosp": "mimiciv_hosp"},
        )
        backend = BigQueryBackend()
        sql = "SELECT * FROM mimiciv_hosp.patients WHERE subject_id = 123"

        result = backend._translate_canonical_to_bq(sql, dataset)

        assert result == (
            "SELECT * FROM `physionet-data.mimiciv_hosp.patients` "
            "WHERE subject_id = 123"
        )


class TestBigQueryCanonicalTableOperations:
    """Test table operations with canonical schema.table format."""

    def test_get_table_list_canonical_format(self, test_dataset, mock_bigquery):
        """Test that get_table_list returns canonical schema.table format."""
        import pandas as pd

        # Mock returns table names for each dataset
        mock_df_1 = pd.DataFrame({"table_name": ["patients", "admissions"]})
        mock_df_2 = pd.DataFrame({"table_name": ["vitals"]})

        mock_job_1 = MagicMock()
        mock_job_1.to_dataframe.return_value = mock_df_1
        mock_job_2 = MagicMock()
        mock_job_2.to_dataframe.return_value = mock_df_2

        mock_bigquery.query.side_effect = [mock_job_1, mock_job_2]

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

                tables = backend.get_table_list(test_dataset)

                assert "test_schema_1.admissions" in tables
                assert "test_schema_1.patients" in tables
                assert "test_schema_2.vitals" in tables
                # Verify NO backtick-wrapped names
                assert not any("`" in t for t in tables)

    def test_get_table_list_fallback_no_mapping(self, mock_bigquery):
        """Test get_table_list falls back to dataset ID when no reverse mapping."""
        import pandas as pd

        dataset = DatasetDefinition(
            name="no-mapping",
            bigquery_project_id="test-project",
            bigquery_dataset_ids=["raw_dataset"],
            bigquery_schema_mapping={},
        )

        mock_df = pd.DataFrame({"table_name": ["patients"]})
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

                tables = backend.get_table_list(dataset)

                # Falls back to BQ dataset ID as schema name
                assert "raw_dataset.patients" in tables

    def test_get_table_info_canonical_format(self, test_dataset, mock_bigquery):
        """Test get_table_info accepts canonical schema.table format."""
        import pandas as pd

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
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

                result = backend.get_table_info("test_schema_1.patients", test_dataset)

                assert result.success is True
                assert result.dataframe is not None

                # Verify the query used the translated BQ dataset ID
                call_args = mock_bigquery.query.call_args
                executed_sql = call_args[0][0]
                assert "test_dataset_1" in executed_sql
                assert "patients" in executed_sql

    def test_get_sample_data_canonical_format(self, test_dataset, mock_bigquery):
        """Test get_sample_data accepts canonical schema.table format."""
        import pandas as pd

        mock_df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {"client": mock_bigquery, "project_id": None}

                result = backend.get_sample_data("test_schema_1.patients", test_dataset)

                assert result.success is True

                # Verify the query used the translated BQ name
                call_args = mock_bigquery.query.call_args
                executed_sql = call_args[0][0]
                assert "`test-project.test_dataset_1.patients`" in executed_sql

    def test_get_sample_data_invalid_name(self, test_dataset):
        """Test get_sample_data with too many dot-separated parts."""
        backend = BigQueryBackend()

        result = backend.get_sample_data("a.b.c.d", test_dataset)

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
