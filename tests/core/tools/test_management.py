"""Tests for management tools (list_datasets, set_dataset).

Tests cover:
- Tool invoke methods directly
- Edge cases and error conditions
- Backend warning messages
- Derived table info in list_datasets

Note: Tools now return native types (dict) instead of ToolOutput.
"""

from unittest.mock import patch

import pytest

from m4.core.datasets import DatasetDefinition
from m4.core.exceptions import DatasetError
from m4.core.tools.management import (
    ListDatasetsInput,
    ListDatasetsTool,
    SetDatasetInput,
    SetDatasetTool,
)

# All ListDatasetsTool tests disable derived lookups by default.
# Tests that specifically verify derived behavior override this.
_NO_DERIVED = patch("m4.core.tools.management.has_derived_support", return_value=False)


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
        """Test that invoke returns dict with dataset info."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=mock_availability,
            ),
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

                    # Result is now a dict
                    assert "mimic-iv-demo" in result["datasets"]
                    assert "mimic-iv" in result["datasets"]
                    assert result["active_dataset"] == "mimic-iv-demo"

    def test_invoke_shows_parquet_status(self, mock_availability, dummy_dataset):
        """Test that parquet availability is included."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=mock_availability,
            ),
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
                    assert (
                        result["datasets"]["mimic-iv-demo"]["parquet_present"] is True
                    )
                    assert result["datasets"]["mimic-iv"]["parquet_present"] is False

    def test_invoke_shows_database_status(self, mock_availability, dummy_dataset):
        """Test that database availability is included."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=mock_availability,
            ),
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

                    assert result["datasets"]["mimic-iv-demo"]["db_present"] is True
                    assert result["datasets"]["mimic-iv"]["db_present"] is False

    def test_invoke_shows_bigquery_status(self, mock_availability, dummy_dataset):
        """Test that BigQuery support status is included."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=mock_availability,
            ),
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

                    # Should include bigquery_support field
                    assert "bigquery_support" in result["datasets"]["mimic-iv-demo"]

    def test_invoke_handles_no_datasets(self, dummy_dataset):
        """Test handling when no datasets are available."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value={},
            ),
        ):
            with patch(
                "m4.core.tools.management.get_active_dataset",
                return_value=None,
            ):
                tool = ListDatasetsTool()
                result = tool.invoke(dummy_dataset, ListDatasetsInput())

                assert result["datasets"] == {}

    def test_invoke_shows_backend_type(self, mock_availability, dummy_dataset):
        """Test that backend type is included."""
        with (
            _NO_DERIVED,
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=mock_availability,
            ),
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

                        assert result["backend"] == "duckdb"

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
                    with patch(
                        "m4.core.tools.management.get_active_backend",
                        return_value="duckdb",
                    ):
                        tool = SetDatasetTool()
                        params = SetDatasetInput(dataset_name="mimic-iv-demo")
                        result = tool.invoke(dummy_dataset, params)

                        mock_set.assert_called_once_with("mimic-iv-demo")
                        assert result["dataset_name"] == "mimic-iv-demo"

    def test_invoke_rejects_unknown_dataset(self, mock_availability, dummy_dataset):
        """Test rejection of unknown dataset raises DatasetError."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset") as mock_set:
                tool = SetDatasetTool()
                params = SetDatasetInput(dataset_name="unknown-dataset")

                with pytest.raises(DatasetError) as exc_info:
                    tool.invoke(dummy_dataset, params)

                mock_set.assert_not_called()
                assert "not found" in str(exc_info.value)

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

                with pytest.raises(DatasetError) as exc_info:
                    tool.invoke(dummy_dataset, params)

                assert "mimic-iv-demo" in str(exc_info.value)
                assert "mimic-iv" in str(exc_info.value)

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

                        assert "Local database not found" in result["warnings"][0]

    def test_invoke_blocks_no_bigquery_config(self, mock_availability, dummy_dataset):
        """Test that switching to a dataset without BigQuery config is blocked."""
        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.set_active_dataset") as mock_set:
                with patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg:
                    mock_reg.return_value = DatasetDefinition(
                        name="mimic-iv-demo",
                        bigquery_dataset_ids=[],  # No BigQuery config
                    )
                    with patch.dict("os.environ", {"M4_BACKEND": "bigquery"}):
                        tool = SetDatasetTool()
                        params = SetDatasetInput(dataset_name="mimic-iv-demo")

                        with pytest.raises(DatasetError) as exc_info:
                            tool.invoke(dummy_dataset, params)

                        mock_set.assert_not_called()
                        assert "not available on the BigQuery backend" in str(
                            exc_info.value
                        )

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
                    with patch(
                        "m4.core.tools.management.get_active_backend",
                        return_value="duckdb",
                    ):
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


class TestListDatasetsDerivedInfo:
    """Test derived table info in list_datasets results."""

    def test_derived_info_for_supported_dataset_duckdb(self, dummy_dataset):
        """Test that derived info is populated for datasets with derived support."""
        availability = {
            "mimic-iv": {
                "parquet_present": True,
                "db_present": True,
                "db_path": "/tmp/mimic_iv.duckdb",
            },
        }

        with (
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=availability,
            ),
            patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv",
            ),
            patch(
                "m4.core.tools.management.get_active_backend",
                return_value="duckdb",
            ),
            patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg,
            patch(
                "m4.core.tools.management.has_derived_support",
                return_value=True,
            ),
            patch(
                "m4.core.tools.management.list_builtins",
                return_value=["age", "sofa", "sepsis3"],
            ),
            patch(
                "m4.core.tools.management.get_derived_table_count",
                return_value=2,
            ),
        ):
            mock_reg.return_value = DatasetDefinition(
                name="mimic-iv", bigquery_dataset_ids=["mimiciv_hosp"]
            )

            tool = ListDatasetsTool()
            result = tool.invoke(dummy_dataset, ListDatasetsInput())

            derived = result["datasets"]["mimic-iv"]["derived"]
            assert derived is not None
            assert derived["supported"] is True
            assert derived["total"] == 3
            assert derived["materialized"] == 2

    def test_derived_info_duckdb_no_db(self, dummy_dataset):
        """Test derived info when DuckDB database doesn't exist yet."""
        availability = {
            "mimic-iv": {
                "parquet_present": True,
                "db_present": False,
                "db_path": "",
            },
        }

        with (
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=availability,
            ),
            patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv",
            ),
            patch(
                "m4.core.tools.management.get_active_backend",
                return_value="duckdb",
            ),
            patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg,
            patch(
                "m4.core.tools.management.has_derived_support",
                return_value=True,
            ),
            patch(
                "m4.core.tools.management.list_builtins",
                return_value=["age", "sofa"],
            ),
            patch(
                "m4.core.tools.management.get_derived_table_count",
            ) as mock_count,
        ):
            mock_reg.return_value = DatasetDefinition(
                name="mimic-iv", bigquery_dataset_ids=[]
            )

            tool = ListDatasetsTool()
            result = tool.invoke(dummy_dataset, ListDatasetsInput())

            derived = result["datasets"]["mimic-iv"]["derived"]
            assert derived["materialized"] == 0
            mock_count.assert_not_called()

    def test_derived_info_bigquery_backend(self, dummy_dataset):
        """Test derived info on BigQuery (materialized is None)."""
        availability = {
            "mimic-iv": {
                "parquet_present": False,
                "db_present": False,
                "db_path": "",
            },
        }

        with (
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=availability,
            ),
            patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="mimic-iv",
            ),
            patch(
                "m4.core.tools.management.get_active_backend",
                return_value="bigquery",
            ),
            patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg,
            patch(
                "m4.core.tools.management.has_derived_support",
                return_value=True,
            ),
            patch(
                "m4.core.tools.management.list_builtins",
                return_value=["age", "sofa", "sepsis3"],
            ),
        ):
            mock_reg.return_value = DatasetDefinition(
                name="mimic-iv", bigquery_dataset_ids=["mimiciv_hosp"]
            )

            tool = ListDatasetsTool()
            result = tool.invoke(dummy_dataset, ListDatasetsInput())

            derived = result["datasets"]["mimic-iv"]["derived"]
            assert derived["supported"] is True
            assert derived["total"] == 3
            assert derived["materialized"] is None

    def test_no_derived_info_for_unsupported_dataset(self, dummy_dataset):
        """Test that derived is None for datasets without derived support."""
        availability = {
            "eicu": {
                "parquet_present": True,
                "db_present": True,
                "db_path": "/tmp/eicu.duckdb",
            },
        }

        with (
            patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value=availability,
            ),
            patch(
                "m4.core.tools.management.get_active_dataset",
                return_value="eicu",
            ),
            patch(
                "m4.core.tools.management.get_active_backend",
                return_value="duckdb",
            ),
            patch("m4.core.tools.management.DatasetRegistry.get") as mock_reg,
            patch(
                "m4.core.tools.management.has_derived_support",
                return_value=False,
            ),
        ):
            mock_reg.return_value = DatasetDefinition(
                name="eicu", bigquery_dataset_ids=["eicu_crd"]
            )

            tool = ListDatasetsTool()
            result = tool.invoke(dummy_dataset, ListDatasetsInput())

            assert result["datasets"]["eicu"]["derived"] is None
