"""Tests for M4 Python API.

Tests cover the public API functions exposed at the package level
for use in code execution environments like Claude Code.

The API now returns native Python types (dict, DataFrame) instead
of formatted strings. Tools raise exceptions for errors.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from m4 import (
    DatasetError,
    M4Error,
    ModalityError,
    QueryError,
    execute_query,
    get_active_dataset,
    get_note,
    get_schema,
    get_table_info,
    list_datasets,
    list_patient_notes,
    search_notes,
    set_dataset,
)
from m4.core.datasets import DatasetDefinition, DatasetRegistry, Modality
from m4.core.exceptions import SecurityError
from m4.core.tools import init_tools

# Patch at the client backend factory boundary.
TABULAR_BACKEND_PATCH = "m4.client.get_backend"
NOTES_BACKEND_PATCH = "m4.client.get_backend"


@pytest.fixture(autouse=True)
def ensure_tools_initialized():
    """Ensure tools are initialized before each test."""
    init_tools()
    yield


@pytest.fixture
def mock_tabular_dataset():
    """Create a mock dataset with TABULAR modality."""
    dataset = DatasetDefinition(
        name="test-tabular",
        modalities=frozenset({Modality.TABULAR}),
    )
    DatasetRegistry.register(dataset)
    yield dataset
    DatasetRegistry._registry.pop("test-tabular", None)


@pytest.fixture
def mock_notes_dataset():
    """Create a mock dataset with NOTES modality."""
    dataset = DatasetDefinition(
        name="test-notes",
        modalities=frozenset({Modality.NOTES}),
    )
    DatasetRegistry.register(dataset)
    yield dataset
    DatasetRegistry._registry.pop("test-notes", None)


class TestDatasetManagement:
    """Test dataset management API functions."""

    def test_list_datasets_returns_list(self):
        """Test list_datasets returns a list of strings."""
        datasets = list_datasets()
        assert isinstance(datasets, list)
        # Should have at least the built-in datasets
        assert len(datasets) > 0
        assert all(isinstance(d, str) for d in datasets)

    def test_set_dataset_raises_migration_error(self, mock_tabular_dataset):
        """set_dataset is retained only as migration guidance."""
        with pytest.raises(DatasetError) as exc_info:
            set_dataset("test-tabular")
        assert "no longer supported" in str(exc_info.value)
        assert "M4Client(dataset=" in str(exc_info.value)

    def test_get_active_dataset_raises_migration_error(self):
        """get_active_dataset is retained only as migration guidance."""
        with pytest.raises(DatasetError) as exc_info:
            get_active_dataset()
        assert "no longer supported" in str(exc_info.value)
        assert "dataset explicitly" in str(exc_info.value)


class TestTabularDataAPI:
    """Test tabular data API functions."""

    @patch(TABULAR_BACKEND_PATCH)
    def test_get_schema(self, mock_get_backend, mock_tabular_dataset):
        """Test get_schema returns dict with tables."""
        mock_backend = MagicMock()
        mock_backend.get_table_list.return_value = [
            "mimiciv_hosp.patients",
            "mimiciv_hosp.admissions",
        ]
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_schema(dataset="test-tabular")

        # Result is now a dict with 'tables' key
        assert isinstance(result, dict)
        assert "mimiciv_hosp.patients" in result["tables"]
        assert "mimiciv_hosp.admissions" in result["tables"]
        mock_backend.get_table_list.assert_called_once()

    @patch(TABULAR_BACKEND_PATCH)
    def test_get_schema_empty(self, mock_get_backend, mock_tabular_dataset):
        """Test get_schema with no tables."""
        mock_backend = MagicMock()
        mock_backend.get_table_list.return_value = []
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_schema(dataset="test-tabular")

        assert result["tables"] == []

    @patch(TABULAR_BACKEND_PATCH)
    def test_get_table_info(self, mock_get_backend, mock_tabular_dataset):
        """Test get_table_info returns dict with schema DataFrame."""
        mock_backend = MagicMock()
        schema_df = pd.DataFrame({"name": ["subject_id"], "type": ["INTEGER"]})
        sample_df = pd.DataFrame({"subject_id": [1], "gender": ["M"]})

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.dataframe = schema_df
        mock_backend.get_table_info.return_value = mock_result

        mock_sample_result = MagicMock()
        mock_sample_result.success = True
        mock_sample_result.dataframe = sample_df
        mock_backend.get_sample_data.return_value = mock_sample_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_table_info("patients", dataset="test-tabular")

        # Result is now a dict
        assert isinstance(result, dict)
        assert result["table_name"] == "patients"
        assert isinstance(result["schema"], pd.DataFrame)
        assert isinstance(result["sample"], pd.DataFrame)

    @patch(TABULAR_BACKEND_PATCH)
    def test_execute_query_success(self, mock_get_backend, mock_tabular_dataset):
        """Test execute_query returns DataFrame."""
        mock_backend = MagicMock()
        result_df = pd.DataFrame({"count": [100]})
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.dataframe = result_df
        mock_backend.execute_query.return_value = mock_result
        mock_get_backend.return_value = mock_backend

        result = execute_query("SELECT COUNT(*) FROM patients", dataset="test-tabular")

        assert isinstance(result, pd.DataFrame)
        assert result["count"].iloc[0] == 100

    @patch(TABULAR_BACKEND_PATCH)
    def test_execute_query_unsafe_raises_error(
        self, mock_get_backend, mock_tabular_dataset
    ):
        """Test execute_query raises SecurityError for unsafe SQL."""
        with pytest.raises(SecurityError):
            execute_query("DROP TABLE patients", dataset="test-tabular")

    @patch(TABULAR_BACKEND_PATCH)
    def test_execute_query_injection_blocked(
        self, mock_get_backend, mock_tabular_dataset
    ):
        """Test execute_query raises SecurityError for SQL injection."""
        with pytest.raises(SecurityError):
            execute_query("SELECT * FROM patients WHERE 1=1", dataset="test-tabular")


class TestClinicalNotesAPI:
    """Test clinical notes API functions."""

    def test_search_notes_requires_notes_modality(self, mock_tabular_dataset):
        """Test search_notes fails without NOTES modality."""
        with pytest.raises(ModalityError) as exc_info:
            search_notes("pneumonia", dataset="test-tabular")
        assert "not available for dataset" in str(exc_info.value)

    def test_get_note_requires_notes_modality(self, mock_tabular_dataset):
        """Test get_note fails without NOTES modality."""
        with pytest.raises(ModalityError):
            get_note("12345", dataset="test-tabular")

    def test_list_patient_notes_requires_notes_modality(self, mock_tabular_dataset):
        """Test list_patient_notes fails without NOTES modality."""
        with pytest.raises(ModalityError):
            list_patient_notes(12345, dataset="test-tabular")

    @patch(NOTES_BACKEND_PATCH)
    def test_search_notes_success(self, mock_get_backend, mock_notes_dataset):
        """Test search_notes returns dict with results."""
        mock_backend = MagicMock()
        result_df = pd.DataFrame({"note_id": ["123"], "snippet": ["found pneumonia"]})
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.dataframe = result_df
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = search_notes("pneumonia", dataset="test-notes", limit=3)

        # Result is now a dict with query and results
        assert isinstance(result, dict)
        assert result["query"] == "pneumonia"
        assert "results" in result

    @patch(NOTES_BACKEND_PATCH)
    def test_search_notes_invalid_type(self, mock_get_backend, mock_notes_dataset):
        """Test search_notes raises QueryError for invalid note type."""
        mock_backend = MagicMock()
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        with pytest.raises(QueryError):
            search_notes("test", dataset="test-notes", note_type="invalid")

    @patch(NOTES_BACKEND_PATCH)
    def test_get_note_not_found(self, mock_get_backend, mock_notes_dataset):
        """Test get_note raises QueryError for non-existent note."""
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.dataframe = pd.DataFrame()  # Empty DataFrame
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        with pytest.raises(QueryError) as exc_info:
            get_note("nonexistent", dataset="test-notes")

        assert "not found" in str(exc_info.value).lower()

    @patch(NOTES_BACKEND_PATCH)
    def test_list_patient_notes_success(self, mock_get_backend, mock_notes_dataset):
        """Test list_patient_notes returns dict with notes metadata."""
        mock_backend = MagicMock()
        result_df = pd.DataFrame(
            {"note_id": ["123"], "note_type": ["discharge"], "note_length": [5000]}
        )
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.dataframe = result_df
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = list_patient_notes(12345, dataset="test-notes")

        # Result is now a dict with subject_id and notes
        assert isinstance(result, dict)
        assert result["subject_id"] == 12345
        assert "notes" in result


class TestExceptionHierarchy:
    """Test the exception class hierarchy."""

    def test_m4_error_is_base(self):
        """Test M4Error is the base exception."""
        assert issubclass(DatasetError, M4Error)
        assert issubclass(QueryError, M4Error)
        assert issubclass(ModalityError, M4Error)

    def test_exceptions_are_catchable_as_base(self):
        """Test all exceptions can be caught as M4Error."""
        with pytest.raises(M4Error):
            raise DatasetError("test")

        with pytest.raises(M4Error):
            raise QueryError("test")

        with pytest.raises(M4Error):
            raise ModalityError("test")
