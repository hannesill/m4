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

import pytest

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

        names = {ds.name for ds in all_datasets}
        assert names >= {
            "mimic-iv-demo",
            "mimic-iv",
            "mimic-iv-note",
            "mimic-iv-ed-demo",
            "mimic-iv-ed",
            "eicu-demo",
            "eicu",
            "mimic-iii",
            "mimic-cxr-jpg",
        }
        assert all(DatasetRegistry.is_builtin(name) for name in names)

    def test_mimic_cxr_jpg_downloads_tables_and_says_where_its_images_are(self):
        DatasetRegistry.reset()
        ds = DatasetRegistry.get("mimic-cxr-jpg")

        assert ds.modalities == frozenset({Modality.TABULAR, Modality.IMAGING})
        assert ds.requires_authentication
        assert ds.dua_url == "https://physionet.org/content/mimic-cxr-jpg/"
        # The tables only: the images are half a terabyte
        assert ds.download_size_gb < 0.1
        assert ds.subdirectories_to_scan == []
        assert set(ds.table_names.values()) == {
            "metadata",
            "chexpert",
            "negbio",
            "split",
            "test_labels",
        }
        assert ds.primary_verification_table == "mimic_cxr.metadata"
        assert ds.images.table == "mimic_cxr.metadata"
        assert ds.images.view == "mimic_cxr.images"
        assert ds.images.id_column == "dicom_id"

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

    @pytest.mark.parametrize(
        ("demo", "full"), [("eicu-demo", "eicu"), ("mimic-iv-ed-demo", "mimic-iv-ed")]
    )
    def test_demo_uses_the_schemas_of_its_full_dataset(self, demo, full):
        """SQL written for the full dataset runs unchanged on its open demo."""
        DatasetRegistry.reset()
        demo_ds = DatasetRegistry.get(demo)
        full_ds = DatasetRegistry.get(full)
        assert demo_ds.schema_mapping == full_ds.schema_mapping
        assert demo_ds.primary_verification_table == full_ds.primary_verification_table
        assert set(demo_ds.bigquery_schema_mapping) == set(
            full_ds.bigquery_schema_mapping
        )
        assert demo_ds.requires_authentication is False
        assert full_ds.requires_authentication is True

    def test_new_builtin_schema_mappings(self):
        DatasetRegistry.reset()
        ed = DatasetRegistry.get("mimic-iv-ed")
        assert ed.schema_mapping == {"ed": "mimiciv_ed"}
        assert ed.subdirectories_to_scan == ["ed"]
        assert ed.primary_verification_table == "mimiciv_ed.edstays"
        assert ed.bigquery_schema_mapping == {"mimiciv_ed": "mimiciv_ed"}
        assert "mimic-iv" in ed.related_datasets

        eicu_demo = DatasetRegistry.get("eicu-demo")
        assert eicu_demo.bigquery_schema_mapping == {"eicu_crd": "eicu_crd_demo"}

        ed_demo = DatasetRegistry.get("mimic-iv-ed-demo")
        assert ed_demo.bigquery_project_id == "physionet-demo"

        mimic_iii = DatasetRegistry.get("mimic-iii")
        assert mimic_iii.schema_mapping == {"": "mimiciii_clinical"}
        assert mimic_iii.subdirectories_to_scan == []
        assert mimic_iii.primary_verification_table == "mimiciii_clinical.admissions"
        assert mimic_iii.bigquery_schema_mapping == {
            "mimiciii_clinical": "mimiciii_clinical"
        }
        assert mimic_iii.requires_authentication is True

    def test_builtins_describe_the_version_they_download(self):
        """Each built-in names the PhysioNet version its download address holds."""
        DatasetRegistry.reset()
        for ds in DatasetRegistry.list_all():
            assert ds.version, ds.name
            assert ds.file_listing_url.endswith(f"/{ds.version}/"), ds.name
            assert ds.title and ds.title != ds.name, ds.name
            assert ds.summary, ds.name
            assert ds.dataset_page_url.startswith("https://physionet.org/content/")
            # Open datasets show their file sizes publicly; credentialed ones not
            if not ds.requires_authentication:
                assert ds.download_size_gb and ds.download_size_gb > 0, ds.name


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

    def test_get_active_raises_removed_state_error(self):
        """get_active() raises DatasetError because global state was removed."""
        import pytest

        from m4.core.exceptions import DatasetError

        with pytest.raises(DatasetError, match=r"DatasetRegistry\.get_active"):
            DatasetRegistry.get_active()

    def test_get_active_ignores_legacy_config(self, monkeypatch):
        """get_active() does not route through legacy active dataset config."""
        import pytest

        import m4.config as cfg
        from m4.core.exceptions import DatasetError

        monkeypatch.setattr(cfg, "get_active_dataset", lambda: "no-such-dataset")

        with pytest.raises(DatasetError, match=r"DatasetRegistry\.get_active"):
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

    def test_custom_json_with_catalog_fields(self, tmp_path):
        """A custom file can describe itself the way built-ins do."""
        (tmp_path / "described.json").write_text(
            json.dumps(
                {
                    "name": "my-icu-extract",
                    "title": "My ICU extract",
                    "summary": "Adult ICU stays at one hospital.",
                    "version": "2024-06",
                    "download_size_gb": 1.5,
                }
            )
        )
        (tmp_path / "bare.json").write_text(json.dumps({"name": "bare-extract"}))

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)

        described = DatasetRegistry.get("my-icu-extract")
        assert described.title == "My ICU extract"
        assert described.summary == "Adult ICU stays at one hospital."
        assert described.version == "2024-06"
        assert described.download_size_gb == 1.5
        assert not DatasetRegistry.is_builtin("my-icu-extract")

        bare = DatasetRegistry.get("bare-extract")
        assert bare.title == "bare-extract"
        assert bare.summary is None
        assert bare.version is None
        assert bare.download_size_gb is None

        DatasetRegistry.reset()

    @pytest.mark.parametrize(
        "filename",
        ["..", "../parquet/eicu", "/tmp/elsewhere.duckdb", "sub/x.duckdb", "x.db"],
    )
    def test_custom_json_database_must_be_a_plain_file_name(
        self, tmp_path, caplog, filename
    ):
        """M4 removes the database by this name: it must not lead elsewhere."""
        (tmp_path / "odd.json").write_text(
            json.dumps({"name": "odd", "default_duckdb_filename": filename})
        )

        DatasetRegistry.reset()
        with caplog.at_level("WARNING", logger="m4.core.datasets"):
            DatasetRegistry.load_custom_datasets(tmp_path)

        assert DatasetRegistry.get("odd") is None
        assert "odd.json" in caplog.text
        DatasetRegistry.reset()

    def test_custom_json_with_images_and_table_names(self, tmp_path):
        (tmp_path / "scans.json").write_text(
            json.dumps(
                {
                    "name": "my-scans",
                    "modalities": ["TABULAR", "IMAGING"],
                    "schema_mapping": {"": "scans"},
                    "table_names": {"scan-list-v2": "scans"},
                    "images": {
                        "table": "scans.scans",
                        "view": "scans.images",
                        "id_column": "scan_id",
                        "path_template": "images/{patient_id}/{scan_id}.png",
                    },
                }
            )
        )

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)

        ds = DatasetRegistry.get("my-scans")
        assert Modality.IMAGING in ds.modalities
        assert ds.table_names == {"scan-list-v2": "scans"}
        assert ds.images.is_image_path("images/7/42.png")
        DatasetRegistry.reset()

    @pytest.mark.parametrize(
        "fields",
        [
            # Images without the modality, and the modality without images
            {
                "images": {
                    "table": "s.t",
                    "view": "s.v",
                    "id_column": "id",
                    "path_template": "{id}.png",
                }
            },
            {"modalities": ["TABULAR", "IMAGING"]},
            {"table_names": {"labs": "lab results"}},
            {
                "modalities": ["IMAGING"],
                "images": {"table": "s.t", "view": "s.v", "id_column": "id"},
            },
        ],
    )
    def test_custom_json_with_images_m4_cannot_use_is_skipped(
        self, tmp_path, caplog, fields
    ):
        (tmp_path / "odd.json").write_text(json.dumps({"name": "odd", **fields}))

        DatasetRegistry.reset()
        with caplog.at_level("WARNING", logger="m4.core.datasets"):
            DatasetRegistry.load_custom_datasets(tmp_path)

        assert DatasetRegistry.get("odd") is None
        assert "odd.json" in caplog.text
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

    @pytest.mark.parametrize(
        "name", ["mimic-iv", "MIMIC-IV", "eicu", "mimic-iv-ed", "mimic-iii"]
    )
    def test_custom_json_cannot_redefine_a_builtin_dataset(
        self, tmp_path, caplog, name
    ):
        """A file in the datasets folder must not change where a built-in
        dataset is downloaded from, or anything else about it."""
        DatasetRegistry.reset()
        builtin = DatasetRegistry.get(name)
        assert builtin.file_listing_url.startswith("https://physionet.org/files/")
        (tmp_path / "anything.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "file_listing_url": "https://example.test/collect/",
                    "requires_authentication": True,
                }
            )
        )

        with caplog.at_level("WARNING", logger="m4.core.datasets"):
            DatasetRegistry.load_custom_datasets(tmp_path)

        assert DatasetRegistry.get(name) is builtin
        assert "anything.json" in caplog.text
        assert "built-in" in caplog.text

        DatasetRegistry.reset()

    def test_custom_json_with_a_new_name_still_loads_next_to_an_ignored_one(
        self, tmp_path
    ):
        (tmp_path / "a-shadow.json").write_text(json.dumps({"name": "mimic-iv"}))
        (tmp_path / "b-new.json").write_text(json.dumps({"name": "my-cohort"}))

        DatasetRegistry.reset()
        DatasetRegistry.load_custom_datasets(tmp_path)

        assert DatasetRegistry.get("my-cohort") is not None
        assert DatasetRegistry.get("mimic-iv").requires_authentication is True

        DatasetRegistry.reset()


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
