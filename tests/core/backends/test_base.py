"""Tests for m4.core.backends.base module.

Tests cover:
- QueryResult dataclass
- Backend exceptions (BackendError, ConnectionError, etc.)
- Backend protocol interface
"""


from m4.core.backends.base import (
    Backend,
    BackendError,
    ConnectionError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)


class TestQueryResult:
    """Test QueryResult dataclass."""

    def test_success_result(self):
        """Test creating a successful query result."""
        result = QueryResult(data="test data", row_count=10)

        assert result.data == "test data"
        assert result.row_count == 10
        assert result.truncated is False
        assert result.error is None
        assert result.success is True

    def test_truncated_result(self):
        """Test creating a truncated query result."""
        result = QueryResult(data="test data", row_count=100, truncated=True)

        assert result.truncated is True
        assert result.success is True

    def test_error_result(self):
        """Test creating an error query result."""
        result = QueryResult(data="", error="Query failed")

        assert result.error == "Query failed"
        assert result.success is False

    def test_empty_result(self):
        """Test creating an empty query result."""
        result = QueryResult(data="No results found", row_count=0)

        assert result.row_count == 0
        assert result.success is True


class TestBackendErrors:
    """Test backend exception classes."""

    def test_backend_error(self):
        """Test base BackendError."""
        error = BackendError("test error", backend="duckdb")

        assert str(error) == "test error"
        assert error.message == "test error"
        assert error.backend == "duckdb"
        assert error.recoverable is False

    def test_backend_error_recoverable(self):
        """Test BackendError with recoverable flag."""
        error = BackendError("test error", backend="bigquery", recoverable=True)

        assert error.recoverable is True

    def test_connection_error(self):
        """Test ConnectionError (always recoverable)."""
        error = ConnectionError("Connection failed", backend="duckdb")

        assert str(error) == "Connection failed"
        assert error.recoverable is True  # Always recoverable

    def test_table_not_found_error(self):
        """Test TableNotFoundError."""
        error = TableNotFoundError("patients", backend="duckdb")

        assert "patients" in str(error)
        assert error.table_name == "patients"
        assert error.recoverable is False

    def test_query_execution_error(self):
        """Test QueryExecutionError."""
        error = QueryExecutionError(
            "Syntax error",
            sql="SELECT * FORM patients",  # typo in FROM
            backend="duckdb",
        )

        assert str(error) == "Syntax error"
        assert error.sql == "SELECT * FORM patients"
        assert error.recoverable is False


class TestBackendProtocol:
    """Test Backend protocol structure."""

    def test_backend_is_runtime_checkable(self):
        """Test that Backend protocol is runtime checkable."""

        class MockBackend:
            name = "mock"

            def execute_query(self, sql, dataset):
                return QueryResult(data="test")

            def get_table_list(self, dataset):
                return []

            def get_table_info(self, table_name, dataset):
                return QueryResult(data="")

            def get_sample_data(self, table_name, dataset, limit=3):
                return QueryResult(data="")

            def get_backend_info(self, dataset):
                return "Mock backend"

        mock = MockBackend()
        assert isinstance(mock, Backend)

    def test_incomplete_backend_not_recognized(self):
        """Test that incomplete backends are not recognized."""

        class IncompleteBackend:
            # Missing required methods
            name = "incomplete"

        backend = IncompleteBackend()
        assert not isinstance(backend, Backend)
