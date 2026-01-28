from pathlib import Path

import pytest

from m4.config import (
    VALID_BACKENDS,
    get_active_backend,
    get_dataset_parquet_root,
    get_default_database_path,
    set_active_backend,
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


# ----------------------------------------------------------------
# Backend configuration tests
# ----------------------------------------------------------------


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Fixture that isolates config file access to a temp directory."""
    import m4.config as cfg_mod

    data_dir = tmp_path / "m4_data"
    data_dir.mkdir()

    monkeypatch.setattr(cfg_mod, "_PROJECT_DATA_DIR", data_dir)
    monkeypatch.setattr(cfg_mod, "_DEFAULT_DATABASES_DIR", data_dir / "databases")
    monkeypatch.setattr(cfg_mod, "_DEFAULT_PARQUET_DIR", data_dir / "parquet")
    monkeypatch.setattr(cfg_mod, "_RUNTIME_CONFIG_PATH", data_dir / "config.json")
    monkeypatch.setattr(cfg_mod, "_CUSTOM_DATASETS_DIR", data_dir / "datasets")

    return data_dir / "config.json"


class TestGetActiveBackend:
    """Tests for get_active_backend function."""

    def test_default_is_duckdb(self, isolated_config, monkeypatch):
        """Default backend is duckdb when nothing is configured."""
        # Clear any env var
        monkeypatch.delenv("M4_BACKEND", raising=False)

        assert get_active_backend() == "duckdb"

    def test_env_var_takes_priority(self, isolated_config, monkeypatch):
        """M4_BACKEND env var takes priority over config file."""
        isolated_config.write_text('{"backend": "duckdb"}')
        monkeypatch.setenv("M4_BACKEND", "bigquery")

        assert get_active_backend() == "bigquery"

    def test_env_var_case_insensitive(self, isolated_config, monkeypatch):
        """M4_BACKEND env var is case-insensitive."""
        monkeypatch.setenv("M4_BACKEND", "BIGQUERY")

        assert get_active_backend() == "bigquery"

    def test_config_file_used_when_no_env(self, isolated_config, monkeypatch):
        """Config file setting is used when no env var is set."""
        isolated_config.write_text('{"backend": "bigquery"}')
        monkeypatch.delenv("M4_BACKEND", raising=False)

        assert get_active_backend() == "bigquery"

    def test_config_file_case_insensitive(self, isolated_config, monkeypatch):
        """Config file backend setting is case-insensitive."""
        isolated_config.write_text('{"backend": "DUCKDB"}')
        monkeypatch.delenv("M4_BACKEND", raising=False)

        assert get_active_backend() == "duckdb"


class TestSetActiveBackend:
    """Tests for set_active_backend function."""

    def test_set_duckdb(self, isolated_config):
        """Can set backend to duckdb."""
        import json

        set_active_backend("duckdb")

        saved = json.loads(isolated_config.read_text())
        assert saved["backend"] == "duckdb"

    def test_set_bigquery(self, isolated_config):
        """Can set backend to bigquery."""
        import json

        set_active_backend("bigquery")

        saved = json.loads(isolated_config.read_text())
        assert saved["backend"] == "bigquery"

    def test_case_insensitive(self, isolated_config):
        """Backend choice is case-insensitive."""
        import json

        set_active_backend("BIGQUERY")

        saved = json.loads(isolated_config.read_text())
        assert saved["backend"] == "bigquery"

    def test_invalid_backend_raises_error(self, isolated_config):
        """Invalid backend raises ValueError."""
        with pytest.raises(ValueError, match="backend must be one of"):
            set_active_backend("invalid")

    def test_preserves_other_config(self, isolated_config):
        """Setting backend preserves other config values."""
        import json

        isolated_config.write_text('{"dataset": "mimic-iv", "other": "value"}')

        set_active_backend("bigquery")

        saved = json.loads(isolated_config.read_text())
        assert saved["backend"] == "bigquery"
        assert saved["dataset"] == "mimic-iv"
        assert saved["other"] == "value"


class TestValidBackends:
    """Tests for VALID_BACKENDS constant."""

    def test_contains_expected_backends(self):
        """VALID_BACKENDS contains duckdb and bigquery."""
        assert "duckdb" in VALID_BACKENDS
        assert "bigquery" in VALID_BACKENDS

    def test_is_frozen(self):
        """VALID_BACKENDS is a set (immutable pattern)."""
        assert isinstance(VALID_BACKENDS, set)
