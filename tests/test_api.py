"""Tests for M4 Python API.

Tests cover the public API functions exposed at the package level
for use in code execution environments like Claude Code.

The API now delegates to tool classes in m4.core.tools, so tests
mock at the backend level (m4.core.backends.get_backend) which is
where the tools access data.
"""

from unittest.mock import MagicMock, patch

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
from m4.core.tools import init_tools

# Patch at the point of use in tool modules, not where defined
TABULAR_BACKEND_PATCH = "m4.core.tools.tabular.get_backend"
NOTES_BACKEND_PATCH = "m4.core.tools.notes.get_backend"


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


class TestPackageLevelImports:
    """Test that all API functions are importable from m4 package."""

    def test_import_exceptions(self):
        """Test exception classes are importable."""
        assert issubclass(DatasetError, M4Error)
        assert issubclass(QueryError, M4Error)
        assert issubclass(ModalityError, M4Error)

    def test_import_dataset_functions(self):
        """Test dataset management functions are importable."""
        assert callable(list_datasets)
        assert callable(set_dataset)
        assert callable(get_active_dataset)

    def test_import_tabular_functions(self):
        """Test tabular data functions are importable."""
        assert callable(get_schema)
        assert callable(get_table_info)
        assert callable(execute_query)

    def test_import_notes_functions(self):
        """Test clinical notes functions are importable."""
        assert callable(search_notes)
        assert callable(get_note)
        assert callable(list_patient_notes)


class TestDatasetManagement:
    """Test dataset management API functions."""

    def test_list_datasets_returns_list(self):
        """Test list_datasets returns a list of strings."""
        datasets = list_datasets()
        assert isinstance(datasets, list)
        # Should have at least the built-in datasets
        assert len(datasets) > 0
        assert all(isinstance(d, str) for d in datasets)

    @patch("m4.api._set_active_dataset")
    def test_set_dataset_success(self, mock_set, mock_tabular_dataset):
        """Test setting a valid dataset."""
        result = set_dataset("test-tabular")
        assert "test-tabular" in result
        mock_set.assert_called_once_with("test-tabular")

    @patch("m4.api._set_active_dataset")
    def test_set_dataset_invalid_raises_error(self, mock_set):
        """Test setting invalid dataset raises DatasetError."""
        mock_set.side_effect = ValueError("Dataset not found")
        with pytest.raises(DatasetError) as exc_info:
            set_dataset("nonexistent-dataset")
        assert "Available datasets" in str(exc_info.value)

    @patch("m4.api._get_active_dataset")
    def test_get_active_dataset(self, mock_get):
        """Test getting the active dataset name."""
        mock_get.return_value = "mimic-iv"
        assert get_active_dataset() == "mimic-iv"

    @patch("m4.api._get_active_dataset")
    def test_get_active_dataset_none_raises_error(self, mock_get):
        """Test getting active dataset when none is set."""
        mock_get.side_effect = ValueError("No active dataset")
        with pytest.raises(DatasetError):
            get_active_dataset()


class TestTabularDataAPI:
    """Test tabular data API functions."""

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_get_schema(self, mock_get_active, mock_get_backend, mock_tabular_dataset):
        """Test get_schema returns table list."""
        mock_get_active.return_value = mock_tabular_dataset
        mock_backend = MagicMock()
        mock_backend.get_table_list.return_value = ["patients", "admissions"]
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_schema()

        assert "patients" in result
        assert "admissions" in result
        mock_backend.get_table_list.assert_called_once()

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_get_schema_empty(
        self, mock_get_active, mock_get_backend, mock_tabular_dataset
    ):
        """Test get_schema with no tables."""
        mock_get_active.return_value = mock_tabular_dataset
        mock_backend = MagicMock()
        mock_backend.get_table_list.return_value = []
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_schema()

        assert "No tables found" in result

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_get_table_info(
        self, mock_get_active, mock_get_backend, mock_tabular_dataset
    ):
        """Test get_table_info returns schema information."""
        mock_get_active.return_value = mock_tabular_dataset
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "subject_id | INTEGER"
        mock_backend.get_table_info.return_value = mock_result
        mock_backend.get_sample_data.return_value = MagicMock(
            success=True, data="1 | M"
        )
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_table_info("patients")

        assert "patients" in result
        assert "subject_id" in result
        assert "Sample Data" in result

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_execute_query_success(
        self, mock_get_active, mock_get_backend, mock_tabular_dataset
    ):
        """Test execute_query with valid SQL."""
        mock_get_active.return_value = mock_tabular_dataset
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "count\n100"
        mock_backend.execute_query.return_value = mock_result
        mock_get_backend.return_value = mock_backend

        result = execute_query("SELECT COUNT(*) FROM patients")

        assert "100" in result

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_execute_query_unsafe_raises_error(
        self, mock_get_active, mock_get_backend, mock_tabular_dataset
    ):
        """Test execute_query rejects unsafe SQL."""
        mock_get_active.return_value = mock_tabular_dataset
        with pytest.raises(QueryError) as exc_info:
            execute_query("DROP TABLE patients")
        # The tool returns "**Security Error:**" but API converts to exception message
        assert "SELECT" in str(exc_info.value) or "Only" in str(exc_info.value)

    @patch(TABULAR_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_execute_query_injection_blocked(
        self, mock_get_active, mock_get_backend, mock_tabular_dataset
    ):
        """Test execute_query blocks SQL injection."""
        mock_get_active.return_value = mock_tabular_dataset
        with pytest.raises(QueryError):
            execute_query("SELECT * FROM patients WHERE 1=1")


class TestClinicalNotesAPI:
    """Test clinical notes API functions."""

    @patch("m4.api.DatasetRegistry.get_active")
    def test_search_notes_requires_notes_modality(
        self, mock_get_active, mock_tabular_dataset
    ):
        """Test search_notes fails without NOTES modality."""
        mock_get_active.return_value = mock_tabular_dataset
        with pytest.raises(ModalityError) as exc_info:
            search_notes("pneumonia")
        assert "does not support clinical notes" in str(exc_info.value)

    @patch("m4.api.DatasetRegistry.get_active")
    def test_get_note_requires_notes_modality(
        self, mock_get_active, mock_tabular_dataset
    ):
        """Test get_note fails without NOTES modality."""
        mock_get_active.return_value = mock_tabular_dataset
        with pytest.raises(ModalityError):
            get_note("12345")

    @patch("m4.api.DatasetRegistry.get_active")
    def test_list_patient_notes_requires_notes_modality(
        self, mock_get_active, mock_tabular_dataset
    ):
        """Test list_patient_notes fails without NOTES modality."""
        mock_get_active.return_value = mock_tabular_dataset
        with pytest.raises(ModalityError):
            list_patient_notes(12345)

    @patch(NOTES_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_search_notes_success(
        self, mock_get_active, mock_get_backend, mock_notes_dataset
    ):
        """Test search_notes with valid notes dataset."""
        mock_get_active.return_value = mock_notes_dataset
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "note_id | snippet\n123 | found pneumonia"
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = search_notes("pneumonia", limit=3)

        assert "pneumonia" in result

    @patch(NOTES_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_search_notes_invalid_type(
        self, mock_get_active, mock_get_backend, mock_notes_dataset
    ):
        """Test search_notes with invalid note type."""
        mock_get_active.return_value = mock_notes_dataset
        mock_backend = MagicMock()
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = search_notes("test", note_type="invalid")
        assert "Error" in result

    @patch(NOTES_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_get_note_not_found(
        self, mock_get_active, mock_get_backend, mock_notes_dataset
    ):
        """Test get_note with non-existent note."""
        mock_get_active.return_value = mock_notes_dataset
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = ""  # Empty result
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = get_note("nonexistent")

        assert "not found" in result.lower()

    @patch(NOTES_BACKEND_PATCH)
    @patch("m4.api.DatasetRegistry.get_active")
    def test_list_patient_notes_success(
        self, mock_get_active, mock_get_backend, mock_notes_dataset
    ):
        """Test list_patient_notes with valid patient."""
        mock_get_active.return_value = mock_notes_dataset
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "note_id | note_type | note_length\n123 | discharge | 5000"
        mock_backend.execute_query.return_value = mock_result
        mock_backend.get_backend_info.return_value = "Backend: DuckDB"
        mock_get_backend.return_value = mock_backend

        result = list_patient_notes(12345)

        assert "12345" in result


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
