"""Tests for m4.core.datasets module.

Tests cover:
- Modality and Capability enums
- DatasetDefinition with capabilities
- DatasetRegistry with enhanced datasets
- JSON loading with modalities and capabilities
"""

import json
import tempfile
from pathlib import Path

from m4.core.datasets import (
    Capability,
    DatasetDefinition,
    DatasetRegistry,
    Modality,
)


class TestEnums:
    """Test Modality and Capability enums."""

    def test_modality_enum_values(self):
        """Test that all expected modalities are defined."""
        assert Modality.TABULAR
        # Currently only TABULAR is defined
        # NOTES, IMAGING, WAVEFORM are planned for future versions

    def test_capability_enum_values(self):
        """Test that all expected capabilities are defined."""
        # Core capabilities
        assert Capability.COHORT_QUERY
        assert Capability.SCHEMA_INTROSPECTION

        # Tabular capabilities
        assert Capability.ICU_STAYS
        assert Capability.LAB_RESULTS
        assert Capability.DEMOGRAPHIC_STATS
        # Future capabilities (MEDICATIONS, PROCEDURES, DIAGNOSES, CLINICAL_NOTES,
        # IMAGE_RETRIEVAL, WAVEFORM_QUERY) are planned for future versions


class TestDatasetDefinition:
    """Test DatasetDefinition."""

    def test_dataset_definition_with_capabilities(self):
        """Test creating dataset with explicit capabilities."""
        ds = DatasetDefinition(
            name="test-dataset",
            modalities=frozenset({Modality.TABULAR}),
            capabilities=frozenset({Capability.ICU_STAYS, Capability.LAB_RESULTS}),
            table_mappings={"icustays": "icu_icustays"},
        )

        assert Modality.TABULAR in ds.modalities
        assert Capability.ICU_STAYS in ds.capabilities
        assert Capability.LAB_RESULTS in ds.capabilities
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

    def test_capabilities_are_immutable(self):
        """Test that capabilities are immutable frozensets."""
        ds = DatasetDefinition(
            name="test-dataset",
            capabilities=frozenset({Capability.ICU_STAYS}),
        )
        assert isinstance(ds.capabilities, frozenset)


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

    def test_mimic_demo_capabilities(self):
        """Test that MIMIC demo has expected capabilities."""
        DatasetRegistry.reset()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        assert Modality.TABULAR in mimic_demo.modalities
        assert Capability.ICU_STAYS in mimic_demo.capabilities
        assert Capability.LAB_RESULTS in mimic_demo.capabilities
        assert Capability.DEMOGRAPHIC_STATS in mimic_demo.capabilities

        # Demo has only tabular capabilities, not multi-modal
        # NOTES modality is planned for future versions

    def test_mimic_full_capabilities(self):
        """Test that MIMIC full has extended capabilities."""
        DatasetRegistry.reset()
        mimic_iv = DatasetRegistry.get("mimic-iv")

        assert Modality.TABULAR in mimic_iv.modalities
        # NOTES modality is planned for future versions

        # Should have core tabular capabilities
        assert Capability.ICU_STAYS in mimic_iv.capabilities
        assert Capability.LAB_RESULTS in mimic_iv.capabilities
        assert Capability.DEMOGRAPHIC_STATS in mimic_iv.capabilities
        # MEDICATIONS, PROCEDURES, DIAGNOSES capabilities are planned for future versions
        # CLINICAL_NOTES capability is planned for future versions

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
            capabilities=frozenset({Capability.LAB_RESULTS}),
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
    """Test JSON loading with modalities and capabilities."""

    def test_json_loading_with_modalities_and_capabilities(self):
        """Test loading dataset with explicit modalities and capabilities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-json-dataset",
                "description": "Test dataset from JSON",
                "modalities": ["TABULAR"],
                "capabilities": ["COHORT_QUERY", "ICU_STAYS", "LAB_RESULTS"],
            }
            json_path = Path(tmpdir) / "test.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-json-dataset")
            assert ds is not None
            assert Modality.TABULAR in ds.modalities
            assert Capability.COHORT_QUERY in ds.capabilities
            assert Capability.ICU_STAYS in ds.capabilities
            assert Capability.LAB_RESULTS in ds.capabilities

    def test_json_loading_defaults_when_not_specified(self):
        """Test that default modalities/capabilities are applied when not in JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-minimal-dataset",
                "description": "Minimal dataset without modalities/capabilities",
            }
            json_path = Path(tmpdir) / "minimal.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-minimal-dataset")
            assert ds is not None
            # Default modality: TABULAR
            assert Modality.TABULAR in ds.modalities
            # Default capabilities: COHORT_QUERY, SCHEMA_INTROSPECTION
            assert Capability.COHORT_QUERY in ds.capabilities
            assert Capability.SCHEMA_INTROSPECTION in ds.capabilities

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

    def test_json_loading_invalid_capability(self):
        """Test that invalid capability names are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-invalid-capability",
                "modalities": ["TABULAR"],
                "capabilities": ["INVALID_CAPABILITY"],
            }
            json_path = Path(tmpdir) / "invalid.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            # Should not be registered due to invalid capability
            ds = DatasetRegistry.get("test-invalid-capability")
            assert ds is None

    def test_json_loading_all_capabilities(self):
        """Test loading dataset with all available capabilities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "name": "test-full-capabilities",
                "modalities": ["TABULAR"],
                "capabilities": [
                    "COHORT_QUERY",
                    "SCHEMA_INTROSPECTION",
                    "ICU_STAYS",
                    "LAB_RESULTS",
                    "DEMOGRAPHIC_STATS",
                ],
            }
            json_path = Path(tmpdir) / "full.json"
            json_path.write_text(json.dumps(json_data))

            DatasetRegistry.reset()
            DatasetRegistry.load_custom_datasets(Path(tmpdir))

            ds = DatasetRegistry.get("test-full-capabilities")
            assert ds is not None
            assert len(ds.capabilities) == 5
            assert Capability.COHORT_QUERY in ds.capabilities
            assert Capability.SCHEMA_INTROSPECTION in ds.capabilities
            assert Capability.ICU_STAYS in ds.capabilities
            assert Capability.LAB_RESULTS in ds.capabilities
            assert Capability.DEMOGRAPHIC_STATS in ds.capabilities
