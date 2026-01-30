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

from m4.core.backends.base import ConnectionError, QueryResult, TableNotFoundError
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

        mock_client = MagicMock()
        backend._client_cache = {
            "client": mock_client,
            "project_id": None,
        }

        # Mock get_bigquery_project_id to return None so cache lookup succeeds
        with patch("m4.config.get_bigquery_project_id", return_value=None):
            with patch.dict("sys.modules", {"google.cloud.bigquery": MagicMock()}):
                client = backend._get_client()

                assert client is mock_client


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


class TestBigQueryCanonicalTranslationEdgeCases:
    """Test SQL translation edge cases for canonical-to-BigQuery conversion."""

    def test_translate_cte_query(self, test_dataset):
        """Test CTE query: schema.table is translated, CTE alias is not."""
        backend = BigQueryBackend()
        sql = (
            "WITH cohort AS ("
            "SELECT * FROM test_schema_1.patients WHERE age > 18"
            ") SELECT * FROM cohort"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert "`test-project.test_dataset_1.patients`" in result
        # CTE alias "cohort" after FROM should not be backtick-wrapped
        assert "FROM cohort" in result
        assert "`cohort`" not in result

    def test_translate_subquery(self, test_dataset):
        """Test subquery: inner table reference is translated."""
        backend = BigQueryBackend()
        sql = "SELECT * FROM (SELECT subject_id FROM test_schema_1.patients) sub"

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert "`test-project.test_dataset_1.patients`" in result

    def test_translate_window_function(self, test_dataset):
        """Test window function query: table reference is translated."""
        backend = BigQueryBackend()
        sql = (
            "SELECT *, ROW_NUMBER() OVER (PARTITION BY subject_id) "
            "FROM test_schema_1.patients"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert "`test-project.test_dataset_1.patients`" in result

    def test_translate_multiple_occurrences_same_table(self, test_dataset):
        """Test self-join: both occurrences of same table are translated."""
        backend = BigQueryBackend()
        sql = (
            "SELECT a.* FROM test_schema_1.patients a "
            "JOIN test_schema_1.patients b "
            "ON a.subject_id = b.subject_id"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        # Count occurrences of the translated name
        translated = "`test-project.test_dataset_1.patients`"
        assert result.count(translated) == 2

    def test_translate_cross_schema_join(self, test_dataset):
        """Test cross-schema join: both schemas correctly translated."""
        backend = BigQueryBackend()
        sql = (
            "SELECT p.*, a.* FROM test_schema_1.patients p "
            "JOIN test_schema_2.admissions a "
            "ON p.subject_id = a.subject_id"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        assert "`test-project.test_dataset_1.patients`" in result
        assert "`test-project.test_dataset_2.admissions`" in result

    def test_translate_preserves_whitespace_and_newlines(self, test_dataset):
        """Test multi-line SQL: formatting preserved, only schema.table changed."""
        backend = BigQueryBackend()
        sql = (
            "SELECT *\n"
            "FROM test_schema_1.patients\n"
            "WHERE subject_id = 123\n"
            "ORDER BY subject_id"
        )

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        # Table reference translated
        assert "`test-project.test_dataset_1.patients`" in result
        # Newlines preserved
        assert "\n" in result
        assert result.startswith("SELECT *\n")
        assert result.endswith("ORDER BY subject_id")

    def test_translate_no_partial_match(self, test_dataset):
        """Test that partial schema name matches are NOT translated."""
        backend = BigQueryBackend()
        sql = "SELECT * FROM my_test_schema_1.patients"

        result = backend._translate_canonical_to_bq(sql, test_dataset)

        # Should NOT be translated because "my_" prefix prevents match
        assert result == sql
        assert "`" not in result


class TestBigQueryQueryExecutionGaps:
    """Test execute_query edge cases and missing code paths."""

    def test_query_truncation_flag(self, test_dataset, mock_bigquery):
        """Test that result.truncated is True when rows > 50."""
        import pandas as pd

        mock_df = pd.DataFrame({"id": range(51)})
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery,
                    "project_id": None,
                }

                result = backend.execute_query("SELECT * FROM test", test_dataset)

                assert result.truncated is True
                assert result.row_count == 51

    def test_query_no_truncation_at_50(self, test_dataset, mock_bigquery):
        """Test that result.truncated is False when rows == 50."""
        import pandas as pd

        mock_df = pd.DataFrame({"id": range(50)})
        mock_query_job = MagicMock()
        mock_query_job.to_dataframe.return_value = mock_df
        mock_bigquery.query.return_value = mock_query_job

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery,
                    "project_id": None,
                }

                result = backend.execute_query("SELECT * FROM test", test_dataset)

                assert result.truncated is False
                assert result.row_count == 50

    def test_dataset_without_bigquery_returns_error(self):
        """Test query against dataset with no BigQuery config."""
        dataset = DatasetDefinition(
            name="no-bq",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
        )

        backend = BigQueryBackend()
        result = backend.execute_query("SELECT 1", dataset)

        assert result.success is False
        assert "not available in BigQuery" in result.error

    def test_generic_exception_returns_sanitized_error(
        self, test_dataset, mock_bigquery
    ):
        """Test that generic exceptions are sanitized in error output."""
        mock_bigquery.query.side_effect = RuntimeError(
            "internal path /opt/secret/data.db"
        )

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                backend = BigQueryBackend()
                backend._client_cache = {
                    "client": mock_bigquery,
                    "project_id": None,
                }

                result = backend.execute_query("SELECT * FROM test", test_dataset)

                assert result.success is False
                assert result.error is not None
                assert "RuntimeError" in result.error

    def test_connection_error_reraised_not_caught(self, test_dataset):
        """Test that ConnectionError propagates and is not caught."""
        backend = BigQueryBackend()

        with patch.dict("sys.modules", {"google.cloud": MagicMock()}):
            mock_bq = MagicMock()
            with patch.dict("sys.modules", {"google.cloud.bigquery": mock_bq}):
                with patch.object(
                    backend,
                    "_get_client",
                    side_effect=ConnectionError(
                        "connection failed", backend="bigquery"
                    ),
                ):
                    with pytest.raises(ConnectionError):
                        backend.execute_query("SELECT * FROM test", test_dataset)


class TestBigQueryTableInfoGaps:
    """Test get_table_info edge cases and missing code paths."""

    def test_get_table_info_simple_name_searches_all_datasets(self, test_dataset):
        """Test simple name searches all datasets, returns first hit."""
        import pandas as pd

        backend = BigQueryBackend()

        empty_df = pd.DataFrame(columns=["column_name", "data_type", "is_nullable"])
        columns_df = pd.DataFrame(
            {
                "column_name": ["id", "name"],
                "data_type": ["INT64", "STRING"],
                "is_nullable": ["NO", "YES"],
            }
        )

        # First call returns empty (dataset_1), second returns data (dataset_2)
        call_count = 0

        def mock_execute(sql, dataset):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(dataframe=empty_df, row_count=0)
            return QueryResult(dataframe=columns_df, row_count=2)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            result = backend.get_table_info("patients", test_dataset)

            assert result.success is True
            assert result.dataframe is not None
            assert len(result.dataframe) == 2
            # Both datasets were searched
            assert call_count == 2

    def test_get_table_info_simple_name_not_found_raises(self, test_dataset):
        """Test simple name raises TableNotFoundError when not found."""
        import pandas as pd

        backend = BigQueryBackend()

        empty_df = pd.DataFrame(columns=["column_name", "data_type", "is_nullable"])

        def mock_execute(sql, dataset):
            return QueryResult(dataframe=empty_df, row_count=0)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            with pytest.raises(TableNotFoundError):
                backend.get_table_info("nonexistent", test_dataset)

    def test_get_table_info_canonical_format_maps_schema(self, test_dataset):
        """Test canonical schema.table maps schema to BQ dataset ID."""
        import pandas as pd

        backend = BigQueryBackend()

        columns_df = pd.DataFrame(
            {
                "column_name": ["id"],
                "data_type": ["INT64"],
                "is_nullable": ["NO"],
            }
        )

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            return QueryResult(dataframe=columns_df, row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            result = backend.get_table_info("test_schema_1.patients", test_dataset)

            assert result.success is True
            # SQL should reference the mapped BQ dataset ID
            assert "test_dataset_1" in captured_sql[0]
            assert "patients" in captured_sql[0]

    def test_get_table_info_legacy_3part_format(self, test_dataset):
        """Test legacy project.dataset.table format (no backticks)."""
        import pandas as pd

        backend = BigQueryBackend()

        columns_df = pd.DataFrame(
            {
                "column_name": ["id"],
                "data_type": ["INT64"],
                "is_nullable": ["NO"],
            }
        )

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            return QueryResult(dataframe=columns_df, row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            result = backend.get_table_info("myproject.mydataset.mytable", test_dataset)

            assert result.success is True
            assert "myproject" in captured_sql[0]
            assert "mydataset" in captured_sql[0]
            assert "mytable" in captured_sql[0]

    def test_get_table_info_backtick_2part_rejected(self, test_dataset):
        """Test backtick name with only 2 parts returns error."""
        backend = BigQueryBackend()

        result = backend.get_table_info("`project.table`", test_dataset)

        assert result.success is False
        assert "Invalid qualified table name" in result.error


class TestBigQuerySampleDataGaps:
    """Test get_sample_data edge cases and missing code paths."""

    def test_limit_clamped_to_minimum_1(self, test_dataset):
        """Test that limit=0 is clamped to 1."""
        backend = BigQueryBackend()

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            import pandas as pd

            return QueryResult(dataframe=pd.DataFrame({"id": [1]}), row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            backend.get_sample_data("test_schema_1.patients", test_dataset, limit=0)

            assert "LIMIT 1" in captured_sql[0]

    def test_limit_clamped_to_maximum_100(self, test_dataset):
        """Test that limit=500 is clamped to 100."""
        backend = BigQueryBackend()

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            import pandas as pd

            return QueryResult(dataframe=pd.DataFrame({"id": [1]}), row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            backend.get_sample_data("test_schema_1.patients", test_dataset, limit=500)

            assert "LIMIT 100" in captured_sql[0]

    def test_simple_name_searches_all_datasets(self, test_dataset):
        """Test simple name falls through datasets until success."""
        import pandas as pd

        backend = BigQueryBackend()

        call_count = 0

        def mock_execute(sql, dataset):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(dataframe=None, error="not found")
            return QueryResult(dataframe=pd.DataFrame({"id": [1]}), row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            result = backend.get_sample_data("patients", test_dataset)

            assert result.success is True
            assert call_count == 2

    def test_simple_name_not_found_returns_error(self, test_dataset):
        """Test simple name returns error when not found in any dataset."""
        backend = BigQueryBackend()

        def mock_execute(sql, dataset):
            return QueryResult(dataframe=None, error="not found")

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            result = backend.get_sample_data("nonexistent", test_dataset)

            assert result.success is False
            assert "not found in any configured dataset" in result.error

    def test_backtick_wrapped_name_passthrough(self, test_dataset):
        """Test backtick-wrapped name is used as-is."""
        backend = BigQueryBackend()

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            import pandas as pd

            return QueryResult(dataframe=pd.DataFrame({"id": [1]}), row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            backend.get_sample_data("`project.dataset.table`", test_dataset)

            assert "`project.dataset.table`" in captured_sql[0]

    def test_legacy_3part_name(self, test_dataset):
        """Test 3-part dotted name is wrapped in backticks."""
        backend = BigQueryBackend()

        captured_sql = []

        def mock_execute(sql, dataset):
            captured_sql.append(sql)
            import pandas as pd

            return QueryResult(dataframe=pd.DataFrame({"id": [1]}), row_count=1)

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            backend.get_sample_data("project.dataset.table", test_dataset)

            assert "`project.dataset.table`" in captured_sql[0]


class TestBigQueryTableListGaps:
    """Test get_table_list edge cases and missing code paths."""

    def test_partial_failure_skips_errored_dataset(self, test_dataset):
        """Test that a failed dataset is skipped without crashing."""
        import pandas as pd

        backend = BigQueryBackend()

        call_count = 0

        def mock_execute(sql, dataset):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(
                    dataframe=pd.DataFrame({"table_name": ["patients", "admissions"]}),
                    row_count=2,
                )
            return QueryResult(dataframe=None, error="access denied")

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            tables = backend.get_table_list(test_dataset)

            # Only tables from first dataset returned
            assert len(tables) == 2
            assert "test_schema_1.patients" in tables
            assert "test_schema_1.admissions" in tables

    def test_tables_are_sorted(self, test_dataset):
        """Test that returned table list is sorted alphabetically."""
        import pandas as pd

        backend = BigQueryBackend()

        call_count = 0

        def mock_execute(sql, dataset):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(
                    dataframe=pd.DataFrame({"table_name": ["zebra", "apple"]}),
                    row_count=2,
                )
            return QueryResult(
                dataframe=pd.DataFrame({"table_name": ["banana"]}),
                row_count=1,
            )

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            tables = backend.get_table_list(test_dataset)

            assert tables == sorted(tables)

    def test_duplicate_table_names_across_datasets(self, test_dataset):
        """Test tables with same name in different schemas get prefixed."""
        import pandas as pd

        backend = BigQueryBackend()

        call_count = 0

        def mock_execute(sql, dataset):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(
                    dataframe=pd.DataFrame({"table_name": ["patients"]}),
                    row_count=1,
                )
            return QueryResult(
                dataframe=pd.DataFrame({"table_name": ["patients"]}),
                row_count=1,
            )

        with patch.object(backend, "execute_query", side_effect=mock_execute):
            tables = backend.get_table_list(test_dataset)

            assert "test_schema_1.patients" in tables
            assert "test_schema_2.patients" in tables
            assert len(tables) == 2


class TestBigQueryClientInit:
    """Test BigQuery client initialization edge cases."""

    def test_import_error_raises_connection_error(self):
        """Test ImportError when google-cloud-bigquery not installed."""
        backend = BigQueryBackend()
        backend._client_cache = {"client": None, "project_id": None}

        # Remove google.cloud.bigquery from modules to trigger ImportError
        with patch.dict(
            "sys.modules",
            {"google.cloud": None, "google.cloud.bigquery": None},
        ):
            with pytest.raises(ConnectionError) as exc_info:
                backend._get_client()

            assert "dependencies not found" in str(exc_info.value).lower()

    def test_client_creation_failure_raises_connection_error(self):
        """Test that client creation failure raises ConnectionError."""
        mock_bq_module = MagicMock()
        mock_bq_module.Client.side_effect = Exception(
            "DefaultCredentialsError: Could not find credentials"
        )

        mock_google_cloud = MagicMock()
        mock_google_cloud.bigquery = mock_bq_module

        backend = BigQueryBackend()
        backend._client_cache = {"client": None, "project_id": None}

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.cloud": mock_google_cloud,
                "google.cloud.bigquery": mock_bq_module,
            },
        ):
            with patch("m4.config.get_bigquery_project_id", return_value="proj"):
                with pytest.raises(ConnectionError) as exc_info:
                    backend._get_client()

                assert "Failed to initialize" in str(exc_info.value)

    def test_cache_invalidated_when_project_changes(self):
        """Test new client created when project ID changes."""
        mock_bq_module = MagicMock()
        old_client = MagicMock()
        new_client = MagicMock()
        mock_bq_module.Client.return_value = new_client

        mock_google_cloud = MagicMock()
        mock_google_cloud.bigquery = mock_bq_module

        backend = BigQueryBackend()
        # Pre-populate cache with old project
        backend._client_cache = {
            "client": old_client,
            "project_id": "old",
        }

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.cloud": mock_google_cloud,
                "google.cloud.bigquery": mock_bq_module,
            },
        ):
            with patch("m4.config.get_bigquery_project_id", return_value="new"):
                client = backend._get_client()

                assert client is new_client
                assert client is not old_client
                mock_bq_module.Client.assert_called_once_with(project="new")

    def test_client_created_without_project_when_none(self):
        """Test Client() called without project= when project is None."""
        mock_bq_module = MagicMock()
        mock_client = MagicMock()
        mock_bq_module.Client.return_value = mock_client

        mock_google_cloud = MagicMock()
        mock_google_cloud.bigquery = mock_bq_module

        backend = BigQueryBackend()
        backend._client_cache = {"client": None, "project_id": None}

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.cloud": mock_google_cloud,
                "google.cloud.bigquery": mock_bq_module,
            },
        ):
            with patch("m4.config.get_bigquery_project_id", return_value=None):
                client = backend._get_client()

                assert client is mock_client
                mock_bq_module.Client.assert_called_once_with()

    def test_client_created_with_project_when_set(self):
        """Test Client(project=...) called when project is set."""
        mock_bq_module = MagicMock()
        mock_client = MagicMock()
        mock_bq_module.Client.return_value = mock_client

        mock_google_cloud = MagicMock()
        mock_google_cloud.bigquery = mock_bq_module

        backend = BigQueryBackend()
        backend._client_cache = {"client": None, "project_id": None}

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.cloud": mock_google_cloud,
                "google.cloud.bigquery": mock_bq_module,
            },
        ):
            with patch(
                "m4.config.get_bigquery_project_id",
                return_value="my-project",
            ):
                client = backend._get_client()

                assert client is mock_client
                mock_bq_module.Client.assert_called_once_with(project="my-project")
