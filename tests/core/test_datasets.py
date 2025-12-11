"""Tests for m4.core.datasets module.

Tests cover:
- Modality and Capability enums
- Enhanced DatasetDefinition with capabilities
- Backward compatibility auto-population
- DatasetRegistry with enhanced datasets
"""

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
        assert Modality.NOTES
        assert Modality.IMAGING
        assert Modality.WAVEFORM

    def test_capability_enum_values(self):
        """Test that all expected capabilities are defined."""
        # Core capabilities
        assert Capability.COHORT_QUERY
        assert Capability.SCHEMA_INTROSPECTION

        # Tabular capabilities
        assert Capability.ICU_STAYS
        assert Capability.LAB_RESULTS
        assert Capability.DEMOGRAPHIC_STATS
        assert Capability.MEDICATIONS
        assert Capability.PROCEDURES
        assert Capability.DIAGNOSES

        # Future capabilities
        assert Capability.CLINICAL_NOTES
        assert Capability.IMAGE_RETRIEVAL
        assert Capability.WAVEFORM_QUERY


class TestDatasetDefinition:
    """Test enhanced DatasetDefinition."""

    def test_dataset_definition_with_capabilities(self):
        """Test creating dataset with explicit capabilities."""
        ds = DatasetDefinition(
            name="test-dataset",
            modalities={Modality.TABULAR},
            capabilities={Capability.ICU_STAYS, Capability.LAB_RESULTS},
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

    def test_backward_compatibility_auto_populate_mimic(self):
        """Test that MIMIC tags auto-populate capabilities."""
        ds = DatasetDefinition(
            name="test-mimic",
            tags=["mimic", "clinical"],
        )

        # Should auto-populate modalities
        assert Modality.TABULAR in ds.modalities

        # Should auto-populate common capabilities
        assert Capability.ICU_STAYS in ds.capabilities
        assert Capability.LAB_RESULTS in ds.capabilities
        assert Capability.DEMOGRAPHIC_STATS in ds.capabilities
        assert Capability.COHORT_QUERY in ds.capabilities

    def test_backward_compatibility_auto_populate_mimic_full(self):
        """Test that MIMIC full tags include notes capability."""
        ds = DatasetDefinition(
            name="test-mimic-full",
            tags=["mimic", "clinical", "full"],
        )

        # Should include notes modality
        assert Modality.NOTES in ds.modalities

        # Should include notes capability
        assert Capability.CLINICAL_NOTES in ds.capabilities

    def test_explicit_capabilities_override_auto_populate(self):
        """Test that explicit capabilities are not overridden."""
        ds = DatasetDefinition(
            name="test-dataset",
            tags=["mimic"],  # Would trigger auto-populate
            capabilities={Capability.ICU_STAYS},  # But we set explicit
        )

        # Should only have explicitly set capability
        assert Capability.ICU_STAYS in ds.capabilities
        # Should NOT have auto-populated capabilities
        assert len(ds.capabilities) == 1


class TestDatasetRegistry:
    """Test DatasetRegistry with enhanced datasets."""

    def test_registry_builtin_datasets(self):
        """Test that built-in datasets are registered."""
        DatasetRegistry.reset()

        mimic_demo = DatasetRegistry.get("mimic-iv-demo")
        assert mimic_demo is not None
        assert mimic_demo.name == "mimic-iv-demo"

        mimic_full = DatasetRegistry.get("mimic-iv-full")
        assert mimic_full is not None
        assert mimic_full.name == "mimic-iv-full"

    def test_mimic_demo_capabilities(self):
        """Test that MIMIC demo has expected capabilities."""
        DatasetRegistry.reset()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        assert Modality.TABULAR in mimic_demo.modalities
        assert Capability.ICU_STAYS in mimic_demo.capabilities
        assert Capability.LAB_RESULTS in mimic_demo.capabilities
        assert Capability.DEMOGRAPHIC_STATS in mimic_demo.capabilities

        # Demo should NOT have notes
        assert Modality.NOTES not in mimic_demo.modalities
        assert Capability.CLINICAL_NOTES not in mimic_demo.capabilities

    def test_mimic_full_capabilities(self):
        """Test that MIMIC full has extended capabilities."""
        DatasetRegistry.reset()
        mimic_full = DatasetRegistry.get("mimic-iv-full")

        assert Modality.TABULAR in mimic_full.modalities
        assert Modality.NOTES in mimic_full.modalities

        # Should have all tabular capabilities
        assert Capability.ICU_STAYS in mimic_full.capabilities
        assert Capability.LAB_RESULTS in mimic_full.capabilities
        assert Capability.MEDICATIONS in mimic_full.capabilities

        # Should have notes capability
        assert Capability.CLINICAL_NOTES in mimic_full.capabilities

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
            modalities={Modality.TABULAR},
            capabilities={Capability.LAB_RESULTS},
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

        assert len(all_datasets) >= 2  # At least mimic-demo and mimic-full
        names = [ds.name for ds in all_datasets]
        assert "mimic-iv-demo" in names
        assert "mimic-iv-full" in names
