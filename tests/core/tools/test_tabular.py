"""Tests for tabular data tools.

Tests cover:
- Tool invoke methods directly
- Error handling for invalid inputs
"""

from unittest.mock import MagicMock, patch

import pytest

from m4.core.backends.base import QueryResult
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    ExecuteQueryTool,
    GetDatabaseSchemaInput,
    GetDatabaseSchemaTool,
    GetTableInfoInput,
    GetTableInfoTool,
)


@pytest.fixture
def mock_dataset():
    """Create a mock dataset with TABULAR modality."""
    return DatasetDefinition(
        name="test-dataset",
        modalities={Modality.TABULAR},
        table_mappings={},
    )


@pytest.fixture
def mock_backend():
    """Create a mock backend for testing."""
    backend = MagicMock()
    backend.name = "mock"
    backend.get_backend_info.return_value = "Mock backend info"
    return backend


class TestGetDatabaseSchemaTool:
    """Test GetDatabaseSchemaTool functionality."""

    def test_invoke_returns_table_list(self, mock_dataset, mock_backend):
        """Test that invoke returns formatted table list."""
        mock_backend.get_table_list.return_value = [
            "patients",
            "admissions",
            "icustays",
        ]

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetDatabaseSchemaTool()
            result = tool.invoke(mock_dataset, GetDatabaseSchemaInput())

            assert "patients" in result.result
            assert "admissions" in result.result
            assert "icustays" in result.result
            assert "Mock backend info" in result.result

    def test_invoke_handles_empty_table_list(self, mock_dataset, mock_backend):
        """Test handling when no tables are found."""
        mock_backend.get_table_list.return_value = []

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetDatabaseSchemaTool()
            result = tool.invoke(mock_dataset, GetDatabaseSchemaInput())

            assert "No tables found" in result.result

    def test_invoke_handles_backend_error(self, mock_dataset, mock_backend):
        """Test error handling when backend raises exception."""
        mock_backend.get_table_list.side_effect = Exception("Connection failed")

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetDatabaseSchemaTool()
            result = tool.invoke(mock_dataset, GetDatabaseSchemaInput())

            assert "Error" in result.result
            assert "Connection failed" in result.result

    def test_is_compatible_with_tabular_dataset(self, mock_dataset):
        """Test compatibility check with tabular dataset."""
        tool = GetDatabaseSchemaTool()
        assert tool.is_compatible(mock_dataset) is True

    def test_is_not_compatible_without_tabular_modality(self):
        """Test incompatibility without TABULAR modality."""
        dataset = DatasetDefinition(
            name="notes-only-dataset",
            modalities={Modality.NOTES},
        )
        tool = GetDatabaseSchemaTool()
        assert tool.is_compatible(dataset) is False


class TestGetTableInfoTool:
    """Test GetTableInfoTool functionality."""

    def test_invoke_returns_schema_and_sample(self, mock_dataset, mock_backend):
        """Test that invoke returns both schema and sample data."""
        mock_backend.get_table_info.return_value = QueryResult(
            data="cid|name|type\n0|subject_id|INTEGER\n1|gender|VARCHAR",
            row_count=2,
        )
        mock_backend.get_sample_data.return_value = QueryResult(
            data="subject_id|gender\n1|M\n2|F",
            row_count=2,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetTableInfoTool()
            params = GetTableInfoInput(table_name="patients", show_sample=True)
            result = tool.invoke(mock_dataset, params)

            assert "patients" in result.result
            assert "subject_id" in result.result
            assert "Sample Data" in result.result

    def test_invoke_without_sample(self, mock_dataset, mock_backend):
        """Test invoke with show_sample=False."""
        mock_backend.get_table_info.return_value = QueryResult(
            data="cid|name|type\n0|subject_id|INTEGER",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetTableInfoTool()
            params = GetTableInfoInput(table_name="patients", show_sample=False)
            result = tool.invoke(mock_dataset, params)

            assert "patients" in result.result
            assert "Sample Data" not in result.result
            mock_backend.get_sample_data.assert_not_called()

    def test_invoke_handles_schema_error(self, mock_dataset, mock_backend):
        """Test error handling when schema lookup fails."""
        mock_backend.get_table_info.return_value = QueryResult(
            data="",
            error="Table not found",
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetTableInfoTool()
            params = GetTableInfoInput(table_name="nonexistent")
            result = tool.invoke(mock_dataset, params)

            assert "Table not found" in result.result


class TestExecuteQueryTool:
    """Test ExecuteQueryTool functionality."""

    def test_invoke_executes_safe_query(self, mock_dataset, mock_backend):
        """Test executing a safe SELECT query."""
        mock_backend.execute_query.return_value = QueryResult(
            data="subject_id|gender\n1|M\n2|F",
            row_count=2,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = ExecuteQueryTool()
            params = ExecuteQueryInput(sql_query="SELECT * FROM patients LIMIT 10")
            result = tool.invoke(mock_dataset, params)

            assert "subject_id" in result.result
            mock_backend.execute_query.assert_called_once()

    def test_invoke_blocks_unsafe_query(self, mock_dataset, mock_backend):
        """Test that unsafe queries are blocked before reaching backend."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = ExecuteQueryTool()
            params = ExecuteQueryInput(sql_query="DROP TABLE patients")
            result = tool.invoke(mock_dataset, params)

            assert "Security Error" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_invoke_blocks_injection_pattern(self, mock_dataset, mock_backend):
        """Test that SQL injection patterns are blocked."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = ExecuteQueryTool()
            params = ExecuteQueryInput(sql_query="SELECT * FROM patients WHERE 1=1")
            result = tool.invoke(mock_dataset, params)

            assert "Security Error" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_invoke_handles_query_error(self, mock_dataset, mock_backend):
        """Test handling of query execution errors."""
        mock_backend.execute_query.return_value = QueryResult(
            data="",
            error="Column not found: age",
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = ExecuteQueryTool()
            params = ExecuteQueryInput(sql_query="SELECT age FROM patients")
            result = tool.invoke(mock_dataset, params)

            assert "Error" in result.result
            assert "get_table_info" in result.result  # Guidance provided


class TestToolInputModels:
    """Test tool input dataclass models."""

    def test_execute_query_input_requires_sql(self):
        """Test that ExecuteQueryInput requires sql_query."""
        input_obj = ExecuteQueryInput(sql_query="SELECT 1")
        assert input_obj.sql_query == "SELECT 1"

    def test_get_table_info_input_defaults(self):
        """Test GetTableInfoInput default values."""
        input_obj = GetTableInfoInput(table_name="test")
        assert input_obj.table_name == "test"
        assert input_obj.show_sample is True  # Default


class TestToolProtocolConformance:
    """Test that all tabular tools conform to the Tool protocol."""

    def test_all_tools_have_required_attributes(self):
        """Test that all tools have required protocol attributes."""
        tools = [
            GetDatabaseSchemaTool(),
            GetTableInfoTool(),
            ExecuteQueryTool(),
        ]

        for tool in tools:
            # Required attributes
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_model")
            assert hasattr(tool, "output_model")
            assert hasattr(tool, "required_modalities")
            assert hasattr(tool, "supported_datasets")

            # Required methods
            assert hasattr(tool, "invoke")
            assert hasattr(tool, "is_compatible")

            # Verify frozenset types for immutability
            assert isinstance(tool.required_modalities, frozenset)

    def test_all_tools_require_tabular_modality(self):
        """Test that all tabular tools require TABULAR modality."""
        tools = [
            GetDatabaseSchemaTool(),
            GetTableInfoTool(),
            ExecuteQueryTool(),
        ]

        for tool in tools:
            assert Modality.TABULAR in tool.required_modalities
