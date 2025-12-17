"""Tests for m4.core.datasets module.

Tests cover:
- Modality enum
- DatasetDefinition with modalities
- DatasetRegistry with enhanced datasets
- JSON loading with modalities
"""

import json
import tempfile
from pathlib import Path

from m4.core.datasets import (
    DatasetDefinition,
    DatasetRegistry,
    Modality,
)


class TestEnums:
    """Test Modality enum."""

    def test_modality_enum_values(self):
        """Test that all expected modalities are defined."""
        assert Modality.TABULAR
        assert Modality.NOTES


class TestDatasetDefinition:
    """Test DatasetDefinition."""

    def test_dataset_definition_with_modalities(self):
        """Test creating dataset with explicit modalities."""
        ds = DatasetDefinition(
            name="test-dataset",
            modalities=frozenset({Modality.TABULAR, Modality.NOTES}),
            table_mappings={"icustays": "icu_icustays"},
        )

        assert Modality.TABULAR in ds.modalities
        assert Modality.NOTES in ds.modalities
        assert ds.table_mappings["icustays"] == "icu_icustays"

    def test_default_duckdb_filename_generation(self):
        """Test that default DuckDB filename is auto-generated."""
        ds = DatasetDefinition(name="my-test-dataset")
        assert ds.default_duckdb_filename == "my_test_dataset.duckdb"

    def test_custom_duckdb_filename(self):
        """Test setting custom DuckDB filename."""
        ds = DatasetDefinition(
            name="test-dataset",
            default_duckdb_filename="custom.duckdb",
        )
        assert ds.default_duckdb_filename == "custom.duckdb"

    def test_modalities_are_immutable(self):
        """Test that modalities are immutable frozensets."""
        ds = DatasetDefinition(
            name="test-dataset",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert isinstance(ds.modalities, frozenset)


class TestDatasetRegistry:
    """Test DatasetRegistry with enhanced datasets."""

    def test_registry_builtin_datasets(self):
        """Test that built-in datasets are registered."""
        DatasetRegistry.reset()

        mimic_demo = DatasetRegistry.get("mimic-iv-demo")
        assert mimic_demo is not None
        assert mimic_demo.name == "mimic-iv-demo"

        mimic_iv = DatasetRegistry.get("mimic-iv")
        assert mimic_iv is not None
        assert mimic_iv.name == "mimic-iv"

    def test_mimic_demo_modalities(self):
        """Test that MIMIC demo has expected modalities."""
        DatasetRegistry.reset()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        assert Modality.TABULAR in mimic_demo.modalities

    def test_mimic_full_modalities(self):
        """Test that MIMIC full has expected modalities."""
        DatasetRegistry.reset()
        mimic_iv = DatasetRegistry.get("mimic-iv")

        assert Modality.TABULAR in mimic_iv.modalities

    def test_mimic_demo_table_mappings(self):
        """Test that MIMIC demo has table mappings."""
        DatasetRegistry.reset()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        assert "icustays" in mimic_demo.table_mappings
        assert mimic_demo.table_mappings["icustays"] == "icu_icustays"
        assert "labevents" in mimic_demo.table_mappings
        assert mimic_demo.table_mappings["labevents"] == "hosp_labevents"

    def test_register_custom_dataset(self):
        """Test registering a custom dataset."""
        custom_ds = DatasetDefinition(
            name="custom-dataset",
            modalities=frozenset({Modality.TABULAR}),
        )

        DatasetRegistry.register(custom_ds)

        retrieved = DatasetRegistry.get("custom-dataset")
        assert retrieved is not None
        assert retrieved.name == "custom-dataset"

    def test_case_insensitive_lookup(self):
        """Test that dataset lookup is case-insensitive."""
        DatasetRegistry.reset()

        # All should work
        assert DatasetRegistry.get("mimic-iv-demo") is not None
        assert DatasetRegistry.get("MIMIC-IV-DEMO") is not None
        assert DatasetRegistry.get("Mimic-Iv-Demo") is not None

    def test_list_all_datasets(self):
        """Test listing all datasets."""
        DatasetRegistry.reset()
        all_datasets = DatasetRegistry.list_all()

        assert len(all_datasets) >= 3  # At least mimic-demo, mimic-iv, and eicu
        names = [ds.name for ds in all_datasets]
        assert "mimic-iv-demo" in names
        assert "mimic-iv" in names
        assert "eicu" in names


class TestJSONLoading:
    """Test JSON loading with modalities."""

    def test_json_loading_with_modalities(self):
        """Test loading dataset with explicit modalities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-json-dataset",
                "description": "Test dataset from JSON",
                "modalities": ["TABULAR", "NOTES"],
            }
            json_path = Path(tmpdir) / "test.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-json-dataset")
            assert ds is not None
            assert Modality.TABULAR in ds.modalities
            assert Modality.NOTES in ds.modalities

    def test_json_loading_defaults_when_not_specified(self):
        """Test that default modalities are applied when not in JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-minimal-dataset",
                "description": "Minimal dataset without modalities",
            }
            json_path = Path(tmpdir) / "minimal.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-minimal-dataset")
            assert ds is not None
            # Default modality: TABULAR
            assert Modality.TABULAR in ds.modalities

    def test_json_loading_invalid_modality(self):
        """Test that invalid modality names are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-invalid-modality",
                "modalities": ["INVALID_MODALITY"],
            }
            json_path = Path(tmpdir) / "invalid.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            # Should not be registered due to invalid modality
            ds = DatasetRegistry.get("test-invalid-modality")
            assert ds is None

    def test_json_loading_all_modalities(self):
        """Test loading dataset with all available modalities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-full-modalities",
                "modalities": ["TABULAR", "NOTES"],
            }
            json_path = Path(tmpdir) / "full.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-full-modalities")
            assert ds is not None
            assert len(ds.modalities) == 2
            assert Modality.TABULAR in ds.modalities
            assert Modality.NOTES in ds.modalities
