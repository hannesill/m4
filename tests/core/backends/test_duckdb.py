"""Tests for m4.core.backends.duckdb module.

Tests cover:
- DuckDBBackend initialization
- Database path resolution
- Query execution (mocked)
- Table listing
- Error handling
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from m4.core.backends.base import ConnectionError, TableNotFoundError
from m4.core.backends.duckdb import DuckDBBackend
from m4.core.datasets import Capability, DatasetDefinition, Modality


@pytest.fixture
def test_dataset():
    """Create a test dataset definition."""
    return DatasetDefinition(
        name="test-dataset",
        modalities={Modality.TABULAR},
        capabilities={Capability.ICU_STAYS, Capability.LAB_RESULTS},
        default_duckdb_filename="test_dataset.duckdb",
    )


@pytest.fixture
def temp_db(test_dataset):
    """Create a temporary DuckDB database for testing."""
    import duckdb

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        # Create a minimal test database
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE patients (
                subject_id INTEGER PRIMARY KEY,
                gender VARCHAR,
                anchor_age INTEGER
            )
        """
        )
        conn.execute(
            """
            INSERT INTO patients VALUES
            (1, 'M', 65),
            (2, 'F', 42),
            (3, 'M', 55)
        """
        )
        conn.close()

        yield db_path


class TestDuckDBBackendInit:
    """Test DuckDBBackend initialization."""

    def test_default_init(self):
        """Test default initialization."""
        backend = DuckDBBackend()

        assert backend.name == "duckdb"
        assert backend._db_path_override is None

    def test_init_with_path_override(self, temp_db):
        """Test initialization with path override."""
        backend = DuckDBBackend(db_path_override=temp_db)

        assert backend._db_path_override == temp_db


class TestDuckDBPathResolution:
    """Test database path resolution."""

    def test_path_override_takes_priority(self, test_dataset, temp_db):
        """Test that path override takes highest priority."""
        backend = DuckDBBackend(db_path_override=temp_db)
        path = backend._get_db_path(test_dataset)

        assert path == temp_db

    def test_env_var_takes_second_priority(self, test_dataset, temp_db):
        """Test that M4_DB_PATH env var takes second priority."""
        with patch.dict(os.environ, {"M4_DB_PATH": str(temp_db)}):
            backend = DuckDBBackend()  # No override
            path = backend._get_db_path(test_dataset)

            assert path == temp_db

    def test_dataset_config_used_as_fallback(self, test_dataset):
        """Test that dataset config is used when no override."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove M4_DB_PATH if set
            env_backup = os.environ.pop("M4_DB_PATH", None)
            try:
                backend = DuckDBBackend()

                with patch(
                    "m4.core.backends.duckdb.get_default_database_path"
                ) as mock_get_path:
                    mock_get_path.return_value = Path("/mock/path/test.duckdb")
                    path = backend._get_db_path(test_dataset)

                    assert path == Path("/mock/path/test.duckdb")
                    mock_get_path.assert_called_once_with(test_dataset.name)
            finally:
                if env_backup:
                    os.environ["M4_DB_PATH"] = env_backup


class TestDuckDBQueryExecution:
    """Test query execution."""

    def test_successful_query(self, test_dataset, temp_db):
        """Test executing a successful query."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query("SELECT * FROM patients", test_dataset)

        assert result.success is True
        assert result.error is None
        assert result.row_count == 3
        assert "subject_id" in result.data
        assert "gender" in result.data

    def test_query_with_limit(self, test_dataset, temp_db):
        """Test query with LIMIT clause."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query("SELECT * FROM patients LIMIT 1", test_dataset)

        assert result.success is True
        assert result.row_count == 1

    def test_empty_result(self, test_dataset, temp_db):
        """Test query returning no results."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query(
            "SELECT * FROM patients WHERE subject_id = 999", test_dataset
        )

        assert result.success is True
        assert result.data == "No results found"
        assert result.row_count == 0

    def test_table_not_found(self, test_dataset, temp_db):
        """Test query against non-existent table."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query("SELECT * FROM nonexistent_table", test_dataset)

        assert result.success is False
        assert result.error is not None

    def test_connection_error_missing_db(self, test_dataset):
        """Test connection error when database file doesn't exist."""
        backend = DuckDBBackend(db_path_override=Path("/nonexistent/path/db.duckdb"))

        with pytest.raises(ConnectionError) as exc_info:
            backend.execute_query("SELECT 1", test_dataset)

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.backend == "duckdb"


class TestDuckDBTableOperations:
    """Test table listing and info operations."""

    def test_get_table_list(self, test_dataset, temp_db):
        """Test listing tables."""
        backend = DuckDBBackend(db_path_override=temp_db)

        tables = backend.get_table_list(test_dataset)

        assert "patients" in tables

    def test_get_table_info(self, test_dataset, temp_db):
        """Test getting table schema info."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.get_table_info("patients", test_dataset)

        assert result.success is True
        # PRAGMA table_info returns column metadata
        assert "subject_id" in result.data or "name" in result.data

    def test_get_table_info_not_found(self, test_dataset, temp_db):
        """Test getting info for non-existent table."""
        backend = DuckDBBackend(db_path_override=temp_db)

        # Should raise or return error
        with pytest.raises(TableNotFoundError):
            backend.get_table_info("nonexistent_table", test_dataset)

    def test_get_sample_data(self, test_dataset, temp_db):
        """Test getting sample data from table."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.get_sample_data("patients", test_dataset, limit=2)

        assert result.success is True
        # Should return at most 2 rows
        assert result.row_count <= 2


class TestDuckDBBackendInfo:
    """Test backend info generation."""

    def test_backend_info(self, test_dataset, temp_db):
        """Test getting backend info."""
        backend = DuckDBBackend(db_path_override=temp_db)

        info = backend.get_backend_info(test_dataset)

        assert "DuckDB" in info
        assert test_dataset.name in info
        assert str(temp_db) in info

    def test_backend_info_missing_db(self, test_dataset):
        """Test backend info when database path can't be determined."""
        backend = DuckDBBackend()

        with patch(
            "m4.core.backends.duckdb.get_default_database_path"
        ) as mock_get_path:
            mock_get_path.return_value = None

            info = backend.get_backend_info(test_dataset)

            assert "DuckDB" in info
            assert "unknown" in info


class TestDuckDBResultTruncation:
    """Test result truncation for large result sets."""

    def test_large_result_truncated(self, test_dataset):
        """Test that large results are truncated."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "large_test.duckdb"

            # Create a database with many rows
            conn = duckdb.connect(str(db_path))
            conn.execute("CREATE TABLE big_table (id INTEGER, value VARCHAR)")

            # Insert 100 rows
            for i in range(100):
                conn.execute(f"INSERT INTO big_table VALUES ({i}, 'value_{i}')")
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            result = backend.execute_query("SELECT * FROM big_table", test_dataset)

            assert result.success is True
            assert result.row_count == 100
            assert result.truncated is True
            assert "showing first 50" in result.data.lower()


class TestDuckDBEdgeCases:
    """Test edge cases and boundary conditions for DuckDB backend."""

    def test_execute_query_with_null_values(self, test_dataset):
        """Test handling of NULL values in results."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nulls.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE with_nulls (
                    id INTEGER,
                    name VARCHAR,
                    value FLOAT
                )
            """
            )
            conn.execute(
                """
                INSERT INTO with_nulls VALUES
                (1, 'test', NULL),
                (2, NULL, 3.14),
                (NULL, 'another', 2.71)
            """
            )
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            result = backend.execute_query("SELECT * FROM with_nulls", test_dataset)

            assert result.success is True
            assert result.row_count == 3
            # NULL values should be represented in output
            assert (
                "None" in result.data or "NaN" in result.data or "<NA>" in result.data
            )

    def test_execute_query_with_unicode(self, test_dataset):
        """Test handling of unicode characters."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "unicode.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute("CREATE TABLE unicode_test (name VARCHAR)")
            conn.execute("INSERT INTO unicode_test VALUES ('Test'), (''), ('Emoji')")
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            result = backend.execute_query("SELECT * FROM unicode_test", test_dataset)

            assert result.success is True
            assert result.row_count == 3

    def test_execute_query_with_very_long_string(self, test_dataset):
        """Test handling of very long string values."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "longstring.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute("CREATE TABLE long_strings (content VARCHAR)")

            long_string = "A" * 10000  # 10KB string
            conn.execute(f"INSERT INTO long_strings VALUES ('{long_string}')")
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            result = backend.execute_query(
                "SELECT LENGTH(content) as len FROM long_strings", test_dataset
            )

            assert result.success is True
            assert "10000" in result.data

    def test_execute_query_with_special_column_names(self, test_dataset):
        """Test handling of column names with special characters."""
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "special.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE special_cols (
                    "column with spaces" INTEGER,
                    "column-with-dashes" INTEGER,
                    normal_column INTEGER
                )
            """
            )
            conn.execute(
                """
                INSERT INTO special_cols VALUES (1, 2, 3)
            """
            )
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            result = backend.execute_query("SELECT * FROM special_cols", test_dataset)

            assert result.success is True
            assert result.row_count == 1

    def test_get_sample_data_limit_sanitization(self, test_dataset, temp_db):
        """Test that limit is properly sanitized for sample data."""
        backend = DuckDBBackend(db_path_override=temp_db)

        # Test negative limit (should be clamped to 1)
        result = backend.get_sample_data("patients", test_dataset, limit=-5)
        assert result.row_count <= 1

        # Test excessive limit (should be clamped to 100)
        result = backend.get_sample_data("patients", test_dataset, limit=1000)
        assert result.row_count <= 100

    def test_get_table_list_empty_database(self, test_dataset):
        """Test get_table_list on database with no tables.

        Note: The implementation returns ['No results found'] when there
        are no tables, rather than an empty list. This is intentional
        for user-friendly messaging.
        """
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.close()

            backend = DuckDBBackend(db_path_override=db_path)
            tables = backend.get_table_list(test_dataset)

            # Implementation returns message rather than empty list
            assert tables == ["No results found"] or tables == []

    def test_concurrent_read_operations(self, test_dataset, temp_db):
        """Test that concurrent read operations work correctly."""
        import concurrent.futures

        backend = DuckDBBackend(db_path_override=temp_db)

        def execute_query():
            return backend.execute_query("SELECT * FROM patients", test_dataset)

        # Run 5 concurrent queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(execute_query) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed
        for result in results:
            assert result.success is True
            assert result.row_count == 3

    def test_query_with_aggregate_functions(self, test_dataset, temp_db):
        """Test queries with aggregate functions."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query(
            "SELECT COUNT(*) as cnt, AVG(anchor_age) as avg_age FROM patients",
            test_dataset,
        )

        assert result.success is True
        assert "cnt" in result.data or "count" in result.data.lower()

    def test_query_with_window_functions(self, test_dataset, temp_db):
        """Test queries with window functions."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query(
            """
            SELECT
                subject_id,
                gender,
                ROW_NUMBER() OVER (ORDER BY subject_id) as row_num
            FROM patients
            """,
            test_dataset,
        )

        assert result.success is True
        assert "row_num" in result.data

    def test_query_syntax_error(self, test_dataset, temp_db):
        """Test handling of SQL syntax errors."""
        backend = DuckDBBackend(db_path_override=temp_db)

        result = backend.execute_query(
            "SELCT * FROM patients",  # Typo in SELECT
            test_dataset,
        )

        assert result.success is False
        assert result.error is not None
