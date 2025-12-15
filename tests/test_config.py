from pathlib import Path

from m4.config import (
    get_dataset_parquet_root,
    get_default_database_path,
)
from m4.core.datasets import DatasetRegistry


def test_get_dataset_known():
    """Test that a known dataset can be retrieved from the registry."""
    ds = DatasetRegistry.get("mimic-iv-demo")
    assert ds is not None
    assert ds.default_duckdb_filename == "mimic_iv_demo.duckdb"


def test_get_dataset_unknown():
    """Test that an unknown dataset returns None."""
    assert DatasetRegistry.get("not-a-dataset") is None


def test_default_paths(tmp_path, monkeypatch):
    # Redirect default dirs to a temp location
    import m4.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "_DEFAULT_DATABASES_DIR", tmp_path / "dbs")
    monkeypatch.setattr(cfg_mod, "_DEFAULT_PARQUET_DIR", tmp_path / "parquet")
    db_path = get_default_database_path("mimic-iv-demo")
    raw_path = get_dataset_parquet_root("mimic-iv-demo")
    # They should be Path objects and exist
    assert isinstance(db_path, Path)
    assert db_path.parent.exists()
    assert isinstance(raw_path, Path)
    assert raw_path.exists()


def test_raw_path_includes_dataset_name(tmp_path, monkeypatch):
    import m4.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "_DEFAULT_PARQUET_DIR", tmp_path / "parquet")
    raw_path = get_dataset_parquet_root("mimic-iv-demo")
    assert "mimic-iv-demo" in str(raw_path)


def test_find_project_root_search(tmp_path, monkeypatch):
    from m4.config import _find_project_root_from_cwd

    # Case 1: No data dir -> returns cwd
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        assert _find_project_root_from_cwd() == tmp_path

    # Case 2: Data dir exists but empty (invalid) -> returns cwd
    data_dir = tmp_path / "m4_data"
    data_dir.mkdir()
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        assert _find_project_root_from_cwd() == tmp_path

    # Case 3: Valid data dir (has databases/) -> returns root
    (data_dir / "databases").mkdir()
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        assert _find_project_root_from_cwd() == tmp_path

    # Case 4: Valid data dir -> returns root from subdir
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    with monkeypatch.context() as m:
        m.chdir(subdir)
        assert _find_project_root_from_cwd() == tmp_path
