"""Tests for m4.core.serialization module.

This module is the sole serialization layer between tool return values
and MCP string output. A bug here silently corrupts all user-visible
output, making these tests critical.

Tests cover:
- serialize_for_mcp() dispatch for all supported types
- DataFrame serialization with truncation
- List serialization (flat and nested dicts)
- Dict serialization with nested structures
- Edge cases: empty containers, None, primitives
"""

import pandas as pd
import pytest

from m4.core.serialization import serialize_for_mcp


class TestSerializeForMCPDispatch:
    """Test that serialize_for_mcp correctly dispatches by type."""

    def test_none_returns_success_message(self):
        """None input produces a success message (side-effect operations)."""
        result = serialize_for_mcp(None)
        assert result == "Operation completed successfully."

    def test_string_passes_through(self):
        """Plain strings are returned as-is via str()."""
        result = serialize_for_mcp("hello world")
        assert result == "hello world"

    def test_integer_converts_to_string(self):
        """Integers are converted to string representation."""
        result = serialize_for_mcp(42)
        assert result == "42"

    def test_float_converts_to_string(self):
        """Floats are converted to string representation."""
        result = serialize_for_mcp(3.14)
        assert result == "3.14"

    def test_bool_converts_to_string(self):
        """Booleans are converted to string representation."""
        result = serialize_for_mcp(True)
        assert result == "True"


class TestSerializeDataFrame:
    """Test DataFrame serialization with truncation behavior."""

    def test_empty_dataframe_returns_no_results(self):
        """Empty DataFrame produces 'No results found' message."""
        df = pd.DataFrame()
        result = serialize_for_mcp(df)
        assert result == "No results found"

    def test_small_dataframe_serializes_fully(self):
        """Small DataFrames are serialized without truncation."""
        df = pd.DataFrame({"col_a": [1, 2, 3], "col_b": ["x", "y", "z"]})
        result = serialize_for_mcp(df)
        assert "col_a" in result
        assert "col_b" in result
        assert "1" in result
        assert "z" in result
        assert "total rows" not in result  # No truncation message

    def test_large_dataframe_truncated(self):
        """DataFrames exceeding max_rows are truncated with count message."""
        df = pd.DataFrame({"id": range(100)})
        result = serialize_for_mcp(df, max_rows=10)
        assert "100 total rows" in result
        assert "showing first 10" in result

    def test_exact_max_rows_not_truncated(self):
        """DataFrames at exactly max_rows are not truncated."""
        df = pd.DataFrame({"id": range(50)})
        result = serialize_for_mcp(df, max_rows=50)
        assert "total rows" not in result

    def test_dataframe_with_single_row(self):
        """Single-row DataFrames serialize correctly."""
        df = pd.DataFrame({"count": [42]})
        result = serialize_for_mcp(df)
        assert "42" in result
        assert "count" in result


class TestSerializeList:
    """Test list serialization."""

    def test_empty_list(self):
        """Empty list produces '(empty list)' message."""
        result = serialize_for_mcp([])
        assert result == "(empty list)"

    def test_flat_list_of_strings(self):
        """List of strings is joined with newlines."""
        result = serialize_for_mcp(["table_a", "table_b", "table_c"])
        assert "table_a" in result
        assert "table_b" in result
        assert "table_c" in result

    def test_list_of_dicts_uses_table_format(self):
        """List of dicts is formatted as a table.

        Requires the optional 'tabulate' dependency for DataFrame.to_markdown().
        This test also documents that missing 'tabulate' would crash serialization.
        """
        pytest.importorskip("tabulate")
        items = [
            {"name": "patients", "rows": 100},
            {"name": "admissions", "rows": 200},
        ]
        result = serialize_for_mcp(items)
        assert "patients" in result
        assert "admissions" in result
        assert "100" in result

    def test_list_of_integers(self):
        """List of integers is joined with newlines."""
        result = serialize_for_mcp([1, 2, 3])
        assert "1" in result
        assert "2" in result
        assert "3" in result


class TestSerializeDict:
    """Test dict serialization."""

    def test_empty_dict(self):
        """Empty dict produces '(empty)' message."""
        result = serialize_for_mcp({})
        assert result == "(empty)"

    def test_flat_dict(self):
        """Flat dict is formatted as key-value pairs."""
        data = {"backend": "duckdb", "tables": 5}
        result = serialize_for_mcp(data)
        assert "**backend:**" in result
        assert "duckdb" in result
        assert "**tables:**" in result
        assert "5" in result

    def test_nested_dict(self):
        """Nested dict indents sub-keys."""
        data = {
            "dataset": {"name": "mimic-iv", "version": "2.2"},
        }
        result = serialize_for_mcp(data)
        assert "**dataset:**" in result
        assert "name: mimic-iv" in result
        assert "version: 2.2" in result

    def test_dict_with_list_value(self):
        """Dict with list value joins list items."""
        data = {"tables": ["patients", "admissions"]}
        result = serialize_for_mcp(data)
        assert "patients" in result
        assert "admissions" in result
