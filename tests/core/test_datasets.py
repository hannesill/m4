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
        )

        assert Modality.TABULAR in ds.modalities
        assert Modality.NOTES in ds.modalities

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

    def test_schema_mapping_defaults_to_empty(self):
        """Test that schema_mapping defaults to empty dict."""
        ds = DatasetDefinition(name="test-dataset")
        assert ds.schema_mapping == {}
        assert ds.bigquery_schema_mapping == {}


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

        assert len(all_datasets) >= 4
        names = [ds.name for ds in all_datasets]
        assert "mimic-iv-demo" in names
        assert "mimic-iv" in names
        assert "mimic-iv-note" in names
        assert "eicu" in names

    def test_mimic_demo_schema_mapping(self):
        """Test MIMIC-IV demo has correct schema mappings."""
        DatasetRegistry.reset()
        ds = DatasetRegistry.get("mimic-iv-demo")
        assert ds.schema_mapping == {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
        assert ds.bigquery_schema_mapping == {}
        assert ds.primary_verification_table == "mimiciv_hosp.admissions"

    def test_mimic_iv_schema_mapping(self):
        """Test MIMIC-IV has correct schema and BigQuery mappings."""
        DatasetRegistry.reset()
        ds = DatasetRegistry.get("mimic-iv")
        assert ds.schema_mapping == {
            "hosp": "mimiciv_hosp",
            "icu": "mimiciv_icu",
            "derived": "mimiciv_derived",
        }
        assert ds.bigquery_schema_mapping == {
            "mimiciv_hosp": "mimiciv_3_1_hosp",
            "mimiciv_icu": "mimiciv_3_1_icu",
            "mimiciv_derived": "mimiciv_derived",
        }
        assert ds.primary_verification_table == "mimiciv_hosp.admissions"
        assert "mimiciv_derived" in ds.bigquery_dataset_ids

    def test_mimic_iv_note_schema_mapping(self):
        """Test MIMIC-IV Note has correct schema mappings."""
        DatasetRegistry.reset()
        ds = DatasetRegistry.get("mimic-iv-note")
        assert ds.schema_mapping == {"note": "mimiciv_note"}
        assert ds.bigquery_schema_mapping == {"mimiciv_note": "mimiciv_note"}
        assert ds.primary_verification_table == "mimiciv_note.discharge"

    def test_eicu_schema_mapping(self):
        """Test eICU has correct schema mappings with empty-string key."""
        DatasetRegistry.reset()
        ds = DatasetRegistry.get("eicu")
        assert ds.schema_mapping == {"": "eicu_crd"}
        assert ds.bigquery_schema_mapping == {"eicu_crd": "eicu_crd"}
        assert ds.primary_verification_table == "eicu_crd.patient"


class TestDatasetRegistryEdgeCases:
    """Test registry edge cases that could cause silent data loss or crashes."""

    def test_register_overwrites_existing(self):
        """Registering a dataset with an existing name overwrites the old one.

        This is important because custom datasets could shadow built-in ones.
        """
        DatasetRegistry.reset()
        original = DatasetRegistry.get("mimic-iv-demo")
        assert original is not None

        replacement = DatasetDefinition(
            name="mimic-iv-demo",
            description="Overwritten",
            modalities=frozenset({Modality.NOTES}),
        )
        DatasetRegistry.register(replacement)

        retrieved = DatasetRegistry.get("mimic-iv-demo")
        assert retrieved.description == "Overwritten"
        assert Modality.NOTES in retrieved.modalities

        # Clean up
        DatasetRegistry.reset()

    def test_reset_restores_builtins(self):
        """reset() clears custom datasets and restores all built-ins."""
        DatasetRegistry.register(
            DatasetDefinition(name="ephemeral-custom", modalities=frozenset())
        )
        assert DatasetRegistry.get("ephemeral-custom") is not None

        DatasetRegistry.reset()
        assert DatasetRegistry.get("ephemeral-custom") is None
        assert DatasetRegistry.get("mimic-iv-demo") is not None
        assert DatasetRegistry.get("eicu") is not None

    def test_get_nonexistent_returns_none(self):
        """get() returns None for unknown dataset names."""
        DatasetRegistry.reset()
        assert DatasetRegistry.get("nonexistent-dataset-xyz") is None

    def test_get_active_no_config_raises(self, monkeypatch):
        """get_active() raises DatasetError when no dataset is configured."""
        import pytest

        import m4.config as cfg
        from m4.core.exceptions import DatasetError

        monkeypatch.setattr(cfg, "get_active_dataset", lambda: None)

        with pytest.raises(DatasetError, match="No active dataset"):
            DatasetRegistry.get_active()

    def test_get_active_unknown_dataset_raises(self, monkeypatch):
        """get_active() raises DatasetError when config points to unknown dataset."""
        import pytest

        import m4.config as cfg
        from m4.core.exceptions import DatasetError

        monkeypatch.setattr(cfg, "get_active_dataset", lambda: "no-such-dataset")

        with pytest.raises(DatasetError, match="not found in registry"):
            DatasetRegistry.get_active()

    def test_custom_json_oversized_file_skipped(self, tmp_path):
        """JSON files exceeding MAX_DATASET_FILE_SIZE are skipped."""
        from m4.core.datasets import MAX_DATASET_FILE_SIZE

        big_file = tmp_path / "huge.json"
        big_file.write_text("x" * (MAX_DATASET_FILE_SIZE + 1))

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)
        # The oversized file should not crash and should not register anything
        assert DatasetRegistry.get("huge") is None

    def test_custom_json_with_schema_mapping(self, tmp_path):
        """Custom JSON with schema_mapping fields loads correctly."""
        json_data = {
            "name": "custom-mapped",
            "schema_mapping": {"hosp": "custom_hosp"},
            "bigquery_schema_mapping": {"custom_hosp": "custom_bq_hosp"},
        }
        (tmp_path / "mapped.json").write_text(json.dumps(json_data))

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)

        ds = DatasetRegistry.get("custom-mapped")
        assert ds is not None
        assert ds.schema_mapping == {"hosp": "custom_hosp"}
        assert ds.bigquery_schema_mapping == {"custom_hosp": "custom_bq_hosp"}

        DatasetRegistry.reset()

    def test_load_custom_datasets_nonexistent_dir(self, tmp_path):
        """load_custom_datasets with nonexistent directory does not crash."""
        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path / "nonexistent")
        # Should not raise, just return silently
        assert DatasetRegistry.get("mimic-iv-demo") is not None

    def test_load_custom_datasets_malformed_json(self, tmp_path):
        """Malformed JSON files are skipped gracefully."""
        (tmp_path / "bad.json").write_text("{invalid json!!!}")

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)
        # Should not crash; malformed file is simply skipped
        assert DatasetRegistry.get("mimic-iv-demo") is not None


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
