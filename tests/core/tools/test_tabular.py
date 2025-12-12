"""Tests for tabular data tools.

Tests cover:
- Tool invoke methods directly
- Table mapping resolution
- Limit validation
- Error handling for invalid inputs
"""

from unittest.mock import MagicMock, patch

import pytest

from m4.core.backends.base import QueryResult
from m4.core.datasets import Capability, DatasetDefinition, Modality
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    ExecuteQueryTool,
    GetDatabaseSchemaInput,
    GetDatabaseSchemaTool,
    GetICUStaysInput,
    GetICUStaysTool,
    GetLabResultsInput,
    GetLabResultsTool,
    GetRaceDistributionInput,
    GetRaceDistributionTool,
    GetTableInfoInput,
    GetTableInfoTool,
)


@pytest.fixture
def mock_dataset():
    """Create a mock dataset with standard capabilities."""
    return DatasetDefinition(
        name="test-dataset",
        modalities={Modality.TABULAR},
        capabilities={
            Capability.COHORT_QUERY,
            Capability.SCHEMA_INTROSPECTION,
            Capability.ICU_STAYS,
            Capability.LAB_RESULTS,
            Capability.DEMOGRAPHIC_STATS,
        },
        table_mappings={
            "icustays": "icu_icustays",
            "labevents": "hosp_labevents",
            "admissions": "hosp_admissions",
        },
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

    def test_is_not_compatible_without_schema_capability(self):
        """Test incompatibility without schema introspection capability."""
        dataset = DatasetDefinition(
            name="limited-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.COHORT_QUERY},  # Missing SCHEMA_INTROSPECTION
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


class TestGetICUStaysTool:
    """Test GetICUStaysTool functionality."""

    def test_invoke_uses_table_mapping(self, mock_dataset, mock_backend):
        """Test that tool uses dataset table_mappings for table name."""
        mock_backend.execute_query.return_value = QueryResult(
            data="stay_id|subject_id\n1|100\n2|200",
            row_count=2,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            tool.invoke(mock_dataset, params)

            # Should use mapped table name "icu_icustays"
            call_args = mock_backend.execute_query.call_args[0][0]
            assert "icu_icustays" in call_args

    def test_invoke_with_patient_id_filter(self, mock_dataset, mock_backend):
        """Test filtering by patient_id."""
        mock_backend.execute_query.return_value = QueryResult(
            data="stay_id|subject_id\n1|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(patient_id=100, limit=10)
            tool.invoke(mock_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "subject_id = 100" in call_args

    def test_invoke_validates_limit(self, mock_dataset, mock_backend):
        """Test that invalid limits are rejected."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=0)  # Invalid
            result = tool.invoke(mock_dataset, params)

            assert "Invalid limit" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_invoke_validates_negative_limit(self, mock_dataset, mock_backend):
        """Test that negative limits are rejected."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=-5)
            result = tool.invoke(mock_dataset, params)

            assert "Invalid limit" in result.result

    def test_invoke_validates_excessive_limit(self, mock_dataset, mock_backend):
        """Test that excessive limits are rejected."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10000)
            result = tool.invoke(mock_dataset, params)

            assert "Invalid limit" in result.result

    def test_invoke_formats_convenience_error(self, mock_dataset, mock_backend):
        """Test that backend errors include guidance for convenience tools."""
        mock_backend.execute_query.return_value = QueryResult(
            data="",
            error="Table not found: icustays",
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            result = tool.invoke(mock_dataset, params)

            assert "Convenience function failed" in result.result
            assert "get_database_schema()" in result.result

    def test_fallback_table_name_without_mapping(self):
        """Test fallback when table_mappings is empty."""
        dataset = DatasetDefinition(
            name="no-mappings",
            modalities={Modality.TABULAR},
            capabilities={Capability.ICU_STAYS},
            table_mappings={},  # Empty mappings
        )

        mock_backend = MagicMock()
        mock_backend.execute_query.return_value = QueryResult(data="test", row_count=1)

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            tool.invoke(dataset, params)

            # Should fallback to "icustays"
            call_args = mock_backend.execute_query.call_args[0][0]
            assert "icustays" in call_args


class TestGetLabResultsTool:
    """Test GetLabResultsTool functionality."""

    def test_invoke_uses_table_mapping(self, mock_dataset, mock_backend):
        """Test that tool uses dataset table_mappings for table name."""
        mock_backend.execute_query.return_value = QueryResult(
            data="itemid|value\n50912|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetLabResultsTool()
            params = GetLabResultsInput(limit=20)
            tool.invoke(mock_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "hosp_labevents" in call_args

    def test_invoke_with_patient_filter(self, mock_dataset, mock_backend):
        """Test filtering by patient_id."""
        mock_backend.execute_query.return_value = QueryResult(
            data="itemid|value\n50912|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetLabResultsTool()
            params = GetLabResultsInput(patient_id=12345, limit=20)
            tool.invoke(mock_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "subject_id = 12345" in call_args


class TestGetRaceDistributionTool:
    """Test GetRaceDistributionTool functionality."""

    def test_invoke_executes_aggregate_query(self, mock_dataset, mock_backend):
        """Test that tool executes proper aggregate query."""
        mock_backend.execute_query.return_value = QueryResult(
            data="race|count\nWHITE|500\nBLACK|200",
            row_count=2,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetRaceDistributionTool()
            params = GetRaceDistributionInput(limit=10)
            tool.invoke(mock_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "GROUP BY race" in call_args
            assert "COUNT(*)" in call_args
            assert "hosp_admissions" in call_args

    def test_is_compatible_requires_demographic_stats(self):
        """Test that tool requires DEMOGRAPHIC_STATS capability."""
        limited_dataset = DatasetDefinition(
            name="limited",
            modalities={Modality.TABULAR},
            capabilities={Capability.COHORT_QUERY},  # Missing DEMOGRAPHIC_STATS
        )

        tool = GetRaceDistributionTool()
        assert tool.is_compatible(limited_dataset) is False


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

    def test_get_icu_stays_input_defaults(self):
        """Test GetICUStaysInput default values."""
        input_obj = GetICUStaysInput()
        assert input_obj.patient_id is None
        assert input_obj.limit == 10

    def test_get_lab_results_input_defaults(self):
        """Test GetLabResultsInput default values."""
        input_obj = GetLabResultsInput()
        assert input_obj.patient_id is None
        assert input_obj.limit == 20

    def test_get_race_distribution_input_defaults(self):
        """Test GetRaceDistributionInput default values."""
        input_obj = GetRaceDistributionInput()
        assert input_obj.limit == 10


class TestToolProtocolConformance:
    """Test that all tabular tools conform to the Tool protocol."""

    def test_all_tools_have_required_attributes(self):
        """Test that all tools have required protocol attributes."""
        tools = [
            GetDatabaseSchemaTool(),
            GetTableInfoTool(),
            ExecuteQueryTool(),
            GetICUStaysTool(),
            GetLabResultsTool(),
            GetRaceDistributionTool(),
        ]

        for tool in tools:
            # Required attributes
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_model")
            assert hasattr(tool, "output_model")
            assert hasattr(tool, "required_modalities")
            assert hasattr(tool, "required_capabilities")
            assert hasattr(tool, "supported_datasets")

            # Required methods
            assert hasattr(tool, "invoke")
            assert hasattr(tool, "is_compatible")

            # Verify frozenset types for immutability
            assert isinstance(tool.required_modalities, frozenset)
            assert isinstance(tool.required_capabilities, frozenset)

    def test_all_tools_require_tabular_modality(self):
        """Test that all tabular tools require TABULAR modality."""
        tools = [
            GetDatabaseSchemaTool(),
            GetTableInfoTool(),
            ExecuteQueryTool(),
            GetICUStaysTool(),
            GetLabResultsTool(),
            GetRaceDistributionTool(),
        ]

        for tool in tools:
            assert Modality.TABULAR in tool.required_modalities


class TestSQLInjectionPatientIdFix:
    """Tests for Phase 1 Security Fix 1.2: SQL Injection via patient_id.

    These tests verify that patient_id parameters are properly validated
    to prevent SQL injection attacks.
    """

    def test_icu_stays_rejects_invalid_patient_id(self, mock_dataset, mock_backend):
        """Test GetICUStaysTool rejects non-integer patient_id."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            # Simulate a string patient_id that can't be converted to int
            params = GetICUStaysInput()
            # We need to bypass dataclass validation by testing with malicious input
            # In practice, the input model enforces int | None, but we test the validation
            params.patient_id = "1 OR 1=1"  # type: ignore
            result = tool.invoke(mock_dataset, params)

            assert "Invalid patient_id" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_icu_stays_valid_patient_id_passes(self, mock_dataset, mock_backend):
        """Test GetICUStaysTool passes valid integer patient_id."""
        mock_backend.execute_query.return_value = QueryResult(
            data="stay_id|subject_id\n1|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(patient_id=100, limit=10)
            tool.invoke(mock_dataset, params)

            # Verify the query was executed with sanitized patient_id
            call_args = mock_backend.execute_query.call_args[0][0]
            assert "subject_id = 100" in call_args

    def test_lab_results_rejects_invalid_patient_id(self, mock_dataset, mock_backend):
        """Test GetLabResultsTool rejects non-integer patient_id."""
        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetLabResultsTool()
            params = GetLabResultsInput()
            params.patient_id = "1; DROP TABLE patients"  # type: ignore
            result = tool.invoke(mock_dataset, params)

            assert "Invalid patient_id" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_lab_results_valid_patient_id_passes(self, mock_dataset, mock_backend):
        """Test GetLabResultsTool passes valid integer patient_id."""
        mock_backend.execute_query.return_value = QueryResult(
            data="itemid|value\n50912|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetLabResultsTool()
            params = GetLabResultsInput(patient_id=12345, limit=20)
            tool.invoke(mock_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "subject_id = 12345" in call_args


class TestSQLInjectionTableNameFix:
    """Tests for Phase 1 Security Fix 1.3: SQL Injection via Table Mappings.

    These tests verify that table names from dataset configuration are
    properly validated to prevent SQL injection attacks.
    """

    def test_icu_stays_rejects_malicious_table_name(self, mock_backend):
        """Test GetICUStaysTool rejects malicious table name from mapping."""
        malicious_dataset = DatasetDefinition(
            name="malicious-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.ICU_STAYS},
            table_mappings={
                "icustays": "icustays; DROP TABLE patients; --",  # SQL injection attempt
            },
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            result = tool.invoke(malicious_dataset, params)

            assert "Invalid table name" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_lab_results_rejects_malicious_table_name(self, mock_backend):
        """Test GetLabResultsTool rejects malicious table name from mapping."""
        malicious_dataset = DatasetDefinition(
            name="malicious-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.LAB_RESULTS},
            table_mappings={
                "labevents": "labevents UNION SELECT * FROM passwords",  # SQL injection
            },
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetLabResultsTool()
            params = GetLabResultsInput(limit=20)
            result = tool.invoke(malicious_dataset, params)

            assert "Invalid table name" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_race_distribution_rejects_malicious_table_name(self, mock_backend):
        """Test GetRaceDistributionTool rejects malicious table name."""
        malicious_dataset = DatasetDefinition(
            name="malicious-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.DEMOGRAPHIC_STATS},
            table_mappings={
                "admissions": "admissions/**/WHERE 1=1--",  # SQL injection with comment
            },
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetRaceDistributionTool()
            params = GetRaceDistributionInput(limit=10)
            result = tool.invoke(malicious_dataset, params)

            assert "Invalid table name" in result.result
            mock_backend.execute_query.assert_not_called()

    def test_valid_table_mapping_passes(self, mock_dataset, mock_backend):
        """Test that valid table mappings pass validation."""
        mock_backend.execute_query.return_value = QueryResult(
            data="stay_id|subject_id\n1|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            tool.invoke(mock_dataset, params)

            # Should use the valid mapped table name
            call_args = mock_backend.execute_query.call_args[0][0]
            assert "icu_icustays" in call_args
            mock_backend.execute_query.assert_called_once()

    def test_table_name_with_underscores_passes(self, mock_backend):
        """Test that table names with underscores are valid."""
        valid_dataset = DatasetDefinition(
            name="valid-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.ICU_STAYS},
            table_mappings={
                "icustays": "hosp_icu_stays_2024",  # Valid with underscores and numbers
            },
        )

        mock_backend.execute_query.return_value = QueryResult(
            data="stay_id|subject_id\n1|100",
            row_count=1,
        )

        with patch("m4.core.tools.tabular.get_backend", return_value=mock_backend):
            tool = GetICUStaysTool()
            params = GetICUStaysInput(limit=10)
            tool.invoke(valid_dataset, params)

            call_args = mock_backend.execute_query.call_args[0][0]
            assert "hosp_icu_stays_2024" in call_args
