"""Tests for dynamic dataset switching functionality.

This module tests that dataset switching works correctly through the
config system and is properly reflected in the backends.
"""

import pytest

import m4.config as config_mod
from m4.config import get_active_dataset, set_active_dataset
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError


def test_dynamic_dataset_switching(tmp_path, monkeypatch):
    """Test that dataset switching works correctly."""
    # Setup mock data dir
    data_dir = tmp_path / "m4_data"
    data_dir.mkdir()

    # Patch config module to use our temp data dir
    monkeypatch.setattr(config_mod, "_PROJECT_DATA_DIR", data_dir)
    monkeypatch.setattr(config_mod, "_DEFAULT_DATABASES_DIR", data_dir / "databases")
    monkeypatch.setattr(config_mod, "_DEFAULT_PARQUET_DIR", data_dir / "parquet")
    monkeypatch.setattr(config_mod, "_RUNTIME_CONFIG_PATH", data_dir / "config.json")
    monkeypatch.setattr(config_mod, "_CUSTOM_DATASETS_DIR", data_dir / "datasets")

    # Ensure dirs exist
    (data_dir / "databases").mkdir()
    (data_dir / "parquet").mkdir()
    (data_dir / "datasets").mkdir()

    # 1. Start with no active dataset
    monkeypatch.setenv("M4_BACKEND", "duckdb")
    monkeypatch.delenv("M4_DB_PATH", raising=False)

    # Ensure config is empty/default
    if (data_dir / "config.json").exists():
        (data_dir / "config.json").unlink()

    # With no active dataset configured, DatasetRegistry.get_active() raises DatasetError
    with pytest.raises(DatasetError):
        DatasetRegistry.get_active()

    # 2. Set active dataset to something else (simulating 'm4 use')
    set_active_dataset("mimic-iv")

    # Verify config file was written
    assert (data_dir / "config.json").exists()

    # Verify DatasetRegistry.get_active() picks it up
    ds_def = DatasetRegistry.get_active()
    assert ds_def.name == "mimic-iv"

    # Verify get_active_dataset reflects the change
    assert get_active_dataset() == "mimic-iv"

    # 3. Verify dataset definition has correct properties
    full_ds = DatasetRegistry.get("mimic-iv")
    assert full_ds is not None
    assert full_ds.requires_authentication is True

    demo_ds = DatasetRegistry.get("mimic-iv-demo")
    assert demo_ds is not None
    assert demo_ds.requires_authentication is False

    # 4. Switch back to demo
    set_active_dataset("mimic-iv-demo")
    ds_def = DatasetRegistry.get_active()
    assert ds_def.name == "mimic-iv-demo"
