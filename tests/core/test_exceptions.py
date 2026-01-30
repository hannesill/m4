"""Tests for m4.core.exceptions module.

Verifies the exception hierarchy, constructor attributes, and
inheritance chains that the MCP server relies on for error handling.
A broken exception hierarchy would cause unhandled errors to crash
the MCP server instead of returning user-friendly messages.
"""

import pytest

from m4.core.exceptions import (
    BackendError,
    ConnectionError,
    DatasetError,
    M4Error,
    ModalityError,
    QueryError,
    QueryExecutionError,
    SecurityError,
    TableNotFoundError,
)


class TestM4ErrorHierarchy:
    """Verify the complete exception inheritance tree."""

    def test_all_exceptions_inherit_from_m4_error(self):
        """Every M4 exception must be catchable via M4Error."""
        exception_classes = [
            QueryError,
            SecurityError,
            DatasetError,
            ModalityError,
            BackendError,
            ConnectionError,
            TableNotFoundError,
            QueryExecutionError,
        ]
        for cls in exception_classes:
            assert issubclass(cls, M4Error), f"{cls.__name__} is not an M4Error"

    def test_backend_subclasses(self):
        """Backend-specific errors inherit from BackendError."""
        assert issubclass(ConnectionError, BackendError)
        assert issubclass(TableNotFoundError, BackendError)
        assert issubclass(QueryExecutionError, BackendError)


class TestQueryErrorAttributes:
    """Test QueryError stores its SQL context."""

    def test_with_sql(self):
        """QueryError stores the failing SQL."""
        err = QueryError("Column not found", sql="SELECT bad_col FROM t")
        assert str(err) == "Column not found"
        assert err.sql == "SELECT bad_col FROM t"

    def test_without_sql(self):
        """QueryError defaults sql to None."""
        err = QueryError("Some failure")
        assert err.sql is None


class TestSecurityErrorAttributes:
    """Test SecurityError stores the blocked query."""

    def test_with_query(self):
        """SecurityError stores the offending query."""
        err = SecurityError("Write not allowed", query="DROP TABLE x")
        assert str(err) == "Write not allowed"
        assert err.query == "DROP TABLE x"

    def test_without_query(self):
        """SecurityError defaults query to None."""
        err = SecurityError("Blocked")
        assert err.query is None


class TestDatasetErrorAttributes:
    """Test DatasetError stores the dataset name."""

    def test_with_dataset_name(self):
        """DatasetError stores the problematic dataset name."""
        err = DatasetError("Not found", dataset_name="bad-ds")
        assert str(err) == "Not found"
        assert err.dataset_name == "bad-ds"

    def test_without_dataset_name(self):
        """DatasetError defaults dataset_name to None."""
        err = DatasetError("Config error")
        assert err.dataset_name is None


class TestModalityErrorAttributes:
    """Test ModalityError stores compatibility details."""

    def test_full_attributes(self):
        """ModalityError stores tool name and modality sets."""
        err = ModalityError(
            "Incompatible",
            tool_name="search_notes",
            required_modalities={"NOTES"},
            available_modalities={"TABULAR"},
        )
        assert str(err) == "Incompatible"
        assert err.tool_name == "search_notes"
        assert err.required_modalities == {"NOTES"}
        assert err.available_modalities == {"TABULAR"}

    def test_defaults(self):
        """ModalityError defaults modality sets to empty."""
        err = ModalityError("Missing modality")
        assert err.tool_name is None
        assert err.required_modalities == set()
        assert err.available_modalities == set()


class TestBackendErrorAttributes:
    """Test BackendError and subclass attributes."""

    def test_backend_error_defaults(self):
        """BackendError defaults backend to 'unknown' and recoverable to False."""
        err = BackendError("Something failed")
        assert err.backend == "unknown"
        assert err.recoverable is False
        assert err.message == "Something failed"

    def test_connection_error_always_recoverable(self):
        """ConnectionError is always marked recoverable."""
        err = ConnectionError("Timeout", backend="duckdb")
        assert err.recoverable is True
        assert err.backend == "duckdb"

    def test_table_not_found_auto_message(self):
        """TableNotFoundError auto-generates message from table name."""
        err = TableNotFoundError("mimiciv_hosp.patients", backend="duckdb")
        assert "mimiciv_hosp.patients" in str(err)
        assert err.table_name == "mimiciv_hosp.patients"
        assert err.recoverable is False

    def test_query_execution_error_stores_sql(self):
        """QueryExecutionError stores the failed SQL."""
        err = QueryExecutionError(
            "Syntax error", sql="SELECT * FORM t", backend="bigquery"
        )
        assert err.sql == "SELECT * FORM t"
        assert err.backend == "bigquery"
        assert err.recoverable is False


class TestExceptionCatching:
    """Test that the exception hierarchy supports layered catch patterns."""

    def test_catch_backend_errors_separately(self):
        """BackendError subtypes can be caught specifically or generically."""
        with pytest.raises(BackendError):
            raise ConnectionError("timeout")

        with pytest.raises(BackendError):
            raise TableNotFoundError("t")

        with pytest.raises(BackendError):
            raise QueryExecutionError("fail", sql="SELECT 1")

    def test_catch_all_via_m4_error(self):
        """All exceptions can be caught via M4Error (MCP server pattern)."""
        errors = [
            QueryError("q"),
            SecurityError("s"),
            DatasetError("d"),
            ModalityError("m"),
            BackendError("b"),
            ConnectionError("c"),
            TableNotFoundError("t"),
            QueryExecutionError("e", sql="x"),
        ]
        for err in errors:
            with pytest.raises(M4Error):
                raise err
