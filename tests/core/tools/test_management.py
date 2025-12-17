"""Tests for management tools (list_datasets, set_dataset).

Tests cover:
- Tool invoke methods directly
- Edge cases and error conditions
- Backend warning messages
"""

from unittest.mock import patch

import pytest

from m4.core.datasets import DatasetDefinition
from m4.core.tools.management import (
    ListDatasetsInput,
    ListDatasetsTool,
    SetDatasetInput,
    SetDatasetTool,
)


@pytest.fixture
def mock_availability():
    """Mock dataset availability data."""
    return {
        "mimic-iv-demo": {
            "parquet_present": True,
            "db_present": True,
        },
        "mimic-iv": {
            "parquet_present": False,
            "db_present": False,
        },
    }


@pytest.fixture
def dummy_dataset():
    """Create a dummy dataset for passing to invoke (not actually used)."""
    return DatasetDefinition(
        name="dummy",
        modalities=set(),
    )


class TestListDatasetsTool:
    """Test ListDatasetsTool functionality."""

    def test_invoke_lists_available_datasets(self, mock_availability, dummy_dataset):
        """Test that invoke returns formatted dataset list."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv-demo",
            ):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_ds = DatasetDefinition(
                        name="test",
                        bigquery_dataset_ids=["test_ds"],
                    )
                    mock_reg.return_value = mock_ds

                    tool = ListDatasetsTool()
                    result = tool.invoke(dummy_dataset, ListDatasetsInput())

                    assert "mimic-iv-demo" in result.result.lower()
                    assert "mimic-iv" in result.result.lower()
                    assert "Active dataset: mimic-iv-demo" in result.result

    def test_invoke_shows_parquet_status(self, mock_availability, dummy_dataset):
        """Test that parquet availability is shown."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv-demo",
            ):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="test", bigquery_dataset_ids=[]
                    )

                    tool = ListDatasetsTool()
                    result = tool.invoke(dummy_dataset, ListDatasetsInput())

                    # Demo has parquet, full does not
                    assert "Local Parquet:" in result.result

    def test_invoke_shows_database_status(self, mock_availability, dummy_dataset):
        """Test that database availability is shown."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv-demo",
            ):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="test", bigquery_dataset_ids=[]
                    )

                    tool = ListDatasetsTool()
                    result = tool.invoke(dummy_dataset, ListDatasetsInput())

                    assert "Local Database:" in result.result

    def test_invoke_shows_bigquery_status(self, mock_availability, dummy_dataset):
        """Test that BigQuery support status is shown."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv-demo",
            ):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_ds = DatasetDefinition(
                        name="test",
                        bigquery_dataset_ids=["bq_dataset"],  # Has BigQuery
                    )
                    mock_reg.return_value = mock_ds

                    tool = ListDatasetsTool()
                    result = tool.invoke(dummy_dataset, ListDatasetsInput())

                    assert "BigQuery Support:" in result.result

    def test_invoke_handles_no_datasets(self, dummy_dataset):
        """Test handling when no datasets are available."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value={},
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value=None,
            ):
                tool = ListDatasetsTool()
                result = tool.invoke(dummy_dataset, ListDatasetsInput())

                assert "No datasets detected" in result.result

    def test_invoke_shows_backend_type(self, mock_availability, dummy_dataset):
        """Test that backend type is shown."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv-demo",
            ):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="test", bigquery_dataset_ids=[]
                    )
                    with patch.dict("os.environ", {"M4_BACKEND": "duckdb"}):
                        tool = ListDatasetsTool()
                        result = tool.invoke(dummy_dataset, ListDatasetsInput())

                        assert "Backend:" in result.result

    def test_is_compatible_always_true(self):
        """Test that management tools are always compatible."""
        # Empty capabilities dataset
        empty_ds = DatasetDefinition(
            name="empty",
            modalities=set(),
        )

        tool = ListDatasetsTool()
        assert tool.is_compatible(empty_ds) is True

    def test_required_modalities_empty(self):
        """Test that management tool has no required modalities."""
        tool = ListDatasetsTool()
        assert tool.required_modalities == frozenset()


class TestSetDatasetTool:
    """Test SetDatasetTool functionality."""

    def test_invoke_switches_to_valid_dataset(self, mock_availability, dummy_dataset):
        """Test successful dataset switch."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset") as mock_set:
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="mimic-iv-demo", bigquery_dataset_ids=[]
                    )

                    tool = SetDatasetTool()
                    params = SetDatasetInput(dataset_name="mimic-iv-demo")
                    result = tool.invoke(dummy_dataset, params)

                    mock_set.assert_called_once_with("mimic-iv-demo")
                    assert "switched to 'mimic-iv-demo'" in result.result

    def test_invoke_rejects_unknown_dataset(self, mock_availability, dummy_dataset):
        """Test rejection of unknown dataset."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset") as mock_set:
                tool = SetDatasetTool()
                params = SetDatasetInput(dataset_name="unknown-dataset")
                result = tool.invoke(dummy_dataset, params)

                mock_set.assert_not_called()
                assert "Error" in result.result
                assert "not found" in result.result

    def test_invoke_shows_supported_datasets_on_error(
        self, mock_availability, dummy_dataset
    ):
        """Test that error message lists supported datasets."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset"):
                tool = SetDatasetTool()
                params = SetDatasetInput(dataset_name="nonexistent")
                result = tool.invoke(dummy_dataset, params)

                assert "mimic-iv-demo" in result.result
                assert "mimic-iv" in result.result

    def test_invoke_warns_missing_db_for_duckdb(self, mock_availability, dummy_dataset):
        """Test warning when database file is missing for DuckDB backend."""
        # Modify availability: parquet present but db missing
        availability = {
            "mimic-iv-demo": {
                "parquet_present": True,
                "db_present": False,  # Missing!
            },
        }

        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset"):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="mimic-iv-demo", bigquery_dataset_ids=[]
                    )
                    with patch.dict("os.environ", {"M4_BACKEND": "duckdb"}):
                        tool = SetDatasetTool()
                        params = SetDatasetInput(dataset_name="mimic-iv-demo")
                        result = tool.invoke(dummy_dataset, params)

                        assert "Local database not found" in result.result
                        assert "initialization" in result.result.lower()

    def test_invoke_warns_no_bigquery_config(self, mock_availability, dummy_dataset):
        """Test warning when dataset lacks BigQuery config but using BigQuery backend."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset"):
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="mimic-iv-demo",
                        bigquery_dataset_ids=[],  # No BigQuery config
                    )
                    with patch.dict("os.environ", {"M4_BACKEND": "bigquery"}):
                        tool = SetDatasetTool()
                        params = SetDatasetInput(dataset_name="mimic-iv-demo")
                        result = tool.invoke(dummy_dataset, params)

                        assert "not configured for BigQuery" in result.result

    def test_invoke_case_insensitive(self, mock_availability, dummy_dataset):
        """Test that dataset name lookup is case-insensitive."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset") as mock_set:
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="mimic-iv-demo", bigquery_dataset_ids=[]
                    )

                    tool = SetDatasetTool()
                    params = SetDatasetInput(dataset_name="MIMIC-IV-DEMO")
                    tool.invoke(dummy_dataset, params)

                    # Should normalize to lowercase
                    mock_set.assert_called_once_with("mimic-iv-demo")

    def test_is_compatible_always_true(self):
        """Test that management tools are always compatible."""
        empty_ds = DatasetDefinition(
            name="empty",
            modalities=set(),
        )

        tool = SetDatasetTool()
        assert tool.is_compatible(empty_ds) is True


class TestManagementToolInputs:
    """Test management tool input dataclass models."""

    def test_list_datasets_input_no_fields(self):
        """Test that ListDatasetsInput has no required fields."""
        input_obj = ListDatasetsInput()
        # Should create successfully with no arguments
        assert input_obj is not None

    def test_set_dataset_input_requires_name(self):
        """Test that SetDatasetInput requires dataset_name."""
        input_obj = SetDatasetInput(dataset_name="test-ds")
        assert input_obj.dataset_name == "test-ds"


class TestManagementToolProtocol:
    """Test that management tools conform to the Tool protocol."""

    def test_list_datasets_has_required_attributes(self):
        """Test ListDatasetsTool has all required attributes."""
        tool = ListDatasetsTool()

        assert tool.name == "list_datasets"
        assert (
            "available" in tool.description.lower()
            or "list" in tool.description.lower()
        )
        assert tool.input_model == ListDatasetsInput
        assert isinstance(tool.required_modalities, frozenset)
        assert tool.supported_datasets is None  # Always available

    def test_set_dataset_has_required_attributes(self):
        """Test SetDatasetTool has all required attributes."""
        tool = SetDatasetTool()

        assert tool.name == "set_dataset"
        assert "switch" in tool.description.lower() or "set" in tool.description.lower()
        assert tool.input_model == SetDatasetInput
        assert isinstance(tool.required_modalities, frozenset)
        assert tool.supported_datasets is None  # Always available
