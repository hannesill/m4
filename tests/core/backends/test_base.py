"""Tests for m4.core.backends.base module.

Tests cover:
- QueryResult dataclass
- Backend exceptions (BackendError, ConnectionError, etc.)
- Backend protocol interface
"""

import pandas as pd

from m4.core.backends.base import (
    Backend,
    BackendError,
    ConnectionError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
    sanitize_error_message,
)


class TestQueryResult:
    """Test QueryResult dataclass."""

    def test_success_result(self):
        """Test creating a successful query result."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        result = QueryResult(dataframe=df, row_count=10)

        assert result.dataframe is not None
        assert len(result.dataframe) == 3
        assert result.row_count == 10
        assert result.truncated is False
        assert result.error is None
        assert result.success is True

    def test_truncated_result(self):
        """Test creating a truncated query result."""
        df = pd.DataFrame({"col": range(100)})
        result = QueryResult(dataframe=df, row_count=100, truncated=True)

        assert result.truncated is True
        assert result.success is True

    def test_error_result(self):
        """Test creating an error query result."""
        result = QueryResult(dataframe=None, error="Query failed")

        assert result.error == "Query failed"
        assert result.success is False

    def test_empty_result(self):
        """Test creating an empty query result."""
        result = QueryResult(dataframe=pd.DataFrame(), row_count=0)

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
                return QueryResult(dataframe=pd.DataFrame())

            def get_table_list(self, dataset):
                return []

            def get_table_info(self, table_name, dataset):
                return QueryResult(dataframe=pd.DataFrame())

            def get_sample_data(self, table_name, dataset, limit=3):
                return QueryResult(dataframe=pd.DataFrame())

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


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message function."""

    # --- DuckDB-style errors (existing patterns) ---

    def test_table_not_found(self):
        """DuckDB-style 'no such table' error."""
        err = Exception("Catalog Error: Table 'foo' not found")
        msg = sanitize_error_message(err, "duckdb")
        assert "Table not found" in msg

    def test_no_such_table(self):
        """DuckDB-style 'no such table' error."""
        err = Exception("no such table: patients")
        msg = sanitize_error_message(err, "duckdb")
        assert "Table not found" in msg

    def test_column_not_found(self):
        """Column not found error."""
        err = Exception("no such column: foobar")
        msg = sanitize_error_message(err, "duckdb")
        assert "Column not found" in msg

    def test_syntax_error(self):
        """SQL syntax error."""
        err = Exception("Parser Error: syntax error at or near 'FORM'")
        msg = sanitize_error_message(err, "duckdb")
        assert "syntax error" in msg.lower()

    def test_timeout(self):
        """Query timeout."""
        err = Exception("Query timed out after 300s")
        msg = sanitize_error_message(err, "duckdb")
        assert "timed out" in msg.lower()

    def test_connection_error(self):
        """Connection error."""
        err = Exception("connection refused")
        msg = sanitize_error_message(err, "duckdb")
        assert "Connection error" in msg

    # --- BigQuery-specific errors (new patterns) ---

    def test_bigquery_404_dataset_not_found(self):
        """BigQuery 404 when dataset doesn't exist."""
        err = Exception("404 Not Found: Dataset my-project:my_dataset was not found")
        msg = sanitize_error_message(err, "bigquery")
        assert "Resource not found" in msg

    def test_bigquery_404_project_not_found(self):
        """BigQuery 404 when project doesn't exist."""
        err = Exception("404 Not found: Project bad-project was not found")
        msg = sanitize_error_message(err, "bigquery")
        assert "Resource not found" in msg

    def test_bigquery_billing_error(self):
        """BigQuery billing not enabled."""
        err = Exception(
            "Access Denied: BigQuery BigQuery: Billing is not enabled for this project"
        )
        msg = sanitize_error_message(err, "bigquery")
        assert "Billing error" in msg

    def test_bigquery_403_forbidden(self):
        """BigQuery 403 Forbidden."""
        err = Exception("403 Forbidden: Access denied for user@example.com")
        msg = sanitize_error_message(err, "bigquery")
        assert "Permission denied" in msg

    def test_bigquery_permission_denied(self):
        """BigQuery access denied."""
        err = Exception("Access Denied: permission denied for dataset")
        msg = sanitize_error_message(err, "bigquery")
        assert "Permission denied" in msg

    def test_bigquery_quota_exceeded(self):
        """BigQuery quota exceeded."""
        err = Exception("Quota exceeded: Too many concurrent queries")
        msg = sanitize_error_message(err, "bigquery")
        assert "Quota exceeded" in msg

    def test_bigquery_rate_limit(self):
        """BigQuery rate limit."""
        err = Exception("Rate limit exceeded for API calls")
        msg = sanitize_error_message(err, "bigquery")
        assert "rate limited" in msg.lower() or "Quota exceeded" in msg

    # --- Generic fallback ---

    def test_generic_fallback_includes_error_type(self):
        """Generic fallback includes the exception type name."""
        err = ValueError("some unexpected internal error")
        msg = sanitize_error_message(err, "bigquery")
        assert "Query execution failed" in msg
        assert "ValueError" in msg

    def test_generic_fallback_for_unknown_exception(self):
        """Generic fallback for completely unknown errors."""

        class CustomBQError(Exception):
            pass

        err = CustomBQError("something went wrong")
        msg = sanitize_error_message(err, "bigquery")
        assert "Query execution failed" in msg
        assert "CustomBQError" in msg
