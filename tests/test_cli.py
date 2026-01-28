import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from m4.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def inject_version(monkeypatch):
    # Patch __version__ in the console module where print_logo imports it
    monkeypatch.setattr("m4.__version__", "0.0.1")


def test_help_shows_app_name():
    result = runner.invoke(app, ["--help"])
    # exit code 0 for successful help display
    assert result.exit_code == 0
    # help output contains the app name
    assert "M4 CLI" in result.stdout


def test_version_option_exits_zero_and_shows_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    # Now displays logo with version
    assert "v0.0.1" in result.stdout


def test_unknown_command_reports_error():
    result = runner.invoke(app, ["not-a-cmd"])
    # unknown command should fail
    assert result.exit_code != 0
    # Check both stdout and stderr since error messages might go to either depending on environment
    error_message = "No such command 'not-a-cmd'"
    assert (
        error_message in result.stdout
        or (hasattr(result, "stderr") and error_message in result.stderr)
        or error_message in result.output
    )


@patch("m4.cli.init_duckdb_from_parquet")
@patch("m4.cli.verify_table_rowcount")
def test_init_command_duckdb_custom_path(mock_rowcount, mock_init):
    """Test that m4 init --db-path uses custom database path override and DuckDB flow."""
    mock_init.return_value = True
    mock_rowcount.return_value = 100

    with tempfile.TemporaryDirectory() as temp_dir:
        custom_db_path = Path(temp_dir) / "custom_mimic.duckdb"
        resolved_custom_db_path = custom_db_path.resolve()
        # Also ensure a deterministic parquet path exists for the dataset discovery.
        with patch("m4.cli.get_dataset_parquet_root") as mock_parquet_root:
            repo_root = Path(__file__).resolve().parents[1]
            mock_parquet_root.return_value = repo_root / "m4_data/parquet/mimic-iv-demo"
            with patch.object(Path, "exists", return_value=True):
                result = runner.invoke(
                    app, ["init", "mimic-iv-demo", "--db-path", str(custom_db_path)]
                )

        assert result.exit_code == 0
        # With Rich panels, paths may be split across lines, check for parts of filename
        # The filename "custom_mimic.duckdb" may be wrapped as "custom_mimi" + "c.duckdb"
        assert "custom_mimi" in result.stdout and ".duckdb" in result.stdout
        # Now uses "Database:" instead of "DuckDB path:"
        assert "Database:" in result.stdout

        # initializer should be called with the resolved path
        mock_init.assert_called_once_with(
            dataset_name="mimic-iv-demo", db_target_path=resolved_custom_db_path
        )
        # verification query should be attempted
        mock_rowcount.assert_called()


def test_config_validation_bigquery_with_db_path():
    """Test that bigquery backend rejects db-path parameter."""
    result = runner.invoke(
        app, ["config", "claude", "--backend", "bigquery", "--db-path", "/test/path"]
    )
    # should fail when db-path is provided with bigquery
    assert result.exit_code == 1
    assert "db-path can only be used with --backend duckdb" in result.output


def test_config_validation_bigquery_requires_project_id():
    """Test that bigquery backend requires project-id parameter."""
    result = runner.invoke(app, ["config", "claude", "--backend", "bigquery"])
    # missing project-id should fail for bigquery backend
    assert result.exit_code == 1
    assert "project-id is required when using --backend bigquery" in result.output


def test_config_validation_duckdb_with_project_id():
    """Test that duckdb backend rejects project-id parameter."""
    result = runner.invoke(
        app, ["config", "claude", "--backend", "duckdb", "--project-id", "test"]
    )
    # should fail when project-id is provided with duckdb
    assert result.exit_code == 1
    # Check output - error messages from typer usually go to stdout
    assert "project-id can only be used with --backend bigquery" in result.output


@patch("subprocess.run")
def test_config_claude_success(mock_subprocess):
    """Test successful Claude Desktop configuration."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])
    assert result.exit_code == 0
    assert "Claude Desktop configuration completed" in result.stdout

    mock_subprocess.assert_called_once()
    call_args = mock_subprocess.call_args[0][0]
    # correct script should be invoked
    assert "setup_claude_desktop.py" in call_args[1]


@patch("subprocess.run")
def test_config_universal_quick_mode(mock_subprocess):
    """Test universal config generator in quick mode."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "--quick"])
    assert result.exit_code == 0
    assert "Generating M4 MCP configuration" in result.stdout

    mock_subprocess.assert_called_once()
    call_args = mock_subprocess.call_args[0][0]
    assert "dynamic_mcp_config.py" in call_args[1]
    assert "--quick" in call_args


@patch("subprocess.run")
def test_config_script_failure(mock_subprocess):
    """Test error handling when config script fails."""
    mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd")

    result = runner.invoke(app, ["config", "claude"])
    # command should return failure exit code when subprocess fails
    assert result.exit_code == 1
    # Just verify that the command failed with the right exit code
    # The specific error message may vary


@patch("subprocess.run")
@patch("m4.cli.get_default_database_path")
@patch("m4.cli.get_active_dataset")
def test_config_claude_infers_db_path_demo(
    mock_active, mock_get_default, mock_subprocess
):
    mock_active.return_value = None  # unset -> default to demo
    mock_get_default.return_value = Path("/tmp/inferred-demo.duckdb")
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])
    assert result.exit_code == 0

    # subprocess run should NOT be called with inferred --db-path (dynamic resolution)
    call_args = mock_subprocess.call_args[0][0]
    assert "--db-path" not in call_args


@patch("subprocess.run")
@patch("m4.cli.get_default_database_path")
@patch("m4.cli.get_active_dataset")
def test_config_claude_infers_db_path_full(
    mock_active, mock_get_default, mock_subprocess
):
    mock_active.return_value = "mimic-iv"
    mock_get_default.return_value = Path("/tmp/inferred-full.duckdb")
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])
    assert result.exit_code == 0

    call_args = mock_subprocess.call_args[0][0]
    assert "--db-path" not in call_args


@patch("m4.cli.set_active_dataset")
@patch("m4.cli.detect_available_local_datasets")
def test_use_full_happy_path(mock_detect, mock_set_active):
    mock_detect.return_value = {
        "mimic-iv-demo": {
            "parquet_present": False,
            "db_present": False,
            "parquet_root": "/tmp/demo",
            "db_path": "/tmp/demo.duckdb",
        },
        "mimic-iv": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["use", "mimic-iv"])
    assert result.exit_code == 0
    # Updated format without trailing period
    assert "Active dataset set to 'mimic-iv'" in result.stdout
    mock_set_active.assert_called_once_with("mimic-iv")


@patch("m4.cli.compute_parquet_dir_size", return_value=123)
@patch("m4.cli.get_active_dataset", return_value="mimic-iv")
@patch("m4.cli.detect_available_local_datasets")
def test_status_happy_path(mock_detect, mock_active, mock_size):
    mock_detect.return_value = {
        "mimic-iv-demo": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/demo",
            "db_path": "/tmp/demo.duckdb",
        },
        "mimic-iv": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Active dataset:" in result.stdout
    assert "mimic-iv" in result.stdout
    # Updated Rich format: "Parquet size:  X.XX GB"
    assert "Parquet size:" in result.stdout


# ----------------------------------------------------------------
# Backend command tests
# ----------------------------------------------------------------


@patch("m4.cli.set_active_backend")
def test_backend_duckdb_happy_path(mock_set_backend):
    """Test setting backend to duckdb."""
    result = runner.invoke(app, ["backend", "duckdb"])

    assert result.exit_code == 0
    assert "Active backend set to 'duckdb'" in result.stdout
    mock_set_backend.assert_called_once_with("duckdb")


@patch("m4.cli.set_active_backend")
@patch("m4.cli.get_active_dataset")
@patch("m4.cli.DatasetRegistry.get")
def test_backend_bigquery_happy_path(mock_registry, mock_get_dataset, mock_set_backend):
    """Test setting backend to bigquery."""
    # Mock a dataset that supports BigQuery
    mock_get_dataset.return_value = "mimic-iv"
    mock_ds = MagicMock()
    mock_ds.bigquery_dataset_ids = ["mimiciv_3_1_hosp"]
    mock_registry.return_value = mock_ds

    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 0
    assert "Active backend set to 'bigquery'" in result.stdout
    assert "BigQuery requires valid Google Cloud credentials" in result.stdout
    mock_set_backend.assert_called_once_with("bigquery")


@patch("m4.cli.set_active_backend")
@patch("m4.cli.get_active_dataset")
@patch("m4.cli.DatasetRegistry.get")
def test_backend_bigquery_warns_unsupported_dataset(
    mock_registry, mock_get_dataset, mock_set_backend
):
    """Test that bigquery backend warns when current dataset doesn't support BQ."""
    # Mock a dataset that doesn't support BigQuery
    mock_get_dataset.return_value = "custom-dataset"
    mock_ds = MagicMock()
    mock_ds.bigquery_dataset_ids = []  # No BigQuery support
    mock_registry.return_value = mock_ds

    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 0
    assert "Active backend set to 'bigquery'" in result.stdout
    assert "is not available in BigQuery" in result.stdout
    mock_set_backend.assert_called_once_with("bigquery")


def test_backend_invalid_choice():
    """Test that invalid backend choice fails with helpful message."""
    result = runner.invoke(app, ["backend", "mysql"])

    assert result.exit_code == 1
    assert "Invalid Backend" in result.stdout
    assert "mysql" in result.stdout
    assert "bigquery" in result.stdout
    assert "duckdb" in result.stdout


@patch("m4.cli.set_active_backend")
def test_backend_case_insensitive(mock_set_backend):
    """Test that backend choice is case-insensitive."""
    result = runner.invoke(app, ["backend", "BIGQUERY"])

    assert result.exit_code == 0
    mock_set_backend.assert_called_once_with("bigquery")


@patch("m4.cli.set_active_backend")
def test_backend_duckdb_shows_init_hint(mock_set_backend):
    """Test that duckdb backend shows initialization hint."""
    result = runner.invoke(app, ["backend", "duckdb"])

    assert result.exit_code == 0
    assert "DuckDB uses local database files" in result.stdout
    assert "m4 init" in result.stdout
