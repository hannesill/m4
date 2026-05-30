import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from m4.cli import app
from m4.core.exceptions import DatasetError
from m4.services.results import CommandResult

runner = CliRunner()


def _ndjson_lines(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


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


def test_init_command_duckdb_custom_path(tmp_path):
    """Test that m4 init --db-path uses custom database path override and DuckDB flow."""
    # Create a temp parquet dir with a dummy file so presence detection works
    pq_dir = tmp_path / "parquet" / "mimic-iv-demo"
    pq_dir.mkdir(parents=True)
    (pq_dir / "test.parquet").touch()

    custom_db_path = tmp_path / "custom_mimic.duckdb"
    resolved_custom_db_path = custom_db_path.resolve()

    with (
        patch("m4.config._find_project_root_from_cwd", return_value=Path.cwd()),
        patch("m4.cli.get_dataset_parquet_root", return_value=pq_dir),
        patch("m4.cli.init_duckdb_from_parquet", return_value=True) as mock_init,
        patch("m4.cli.verify_table_rowcount", return_value=100) as mock_rowcount,
        patch("m4.cli.set_active_dataset"),
    ):
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


@patch("m4.cli.initialize_dataset_service")
def test_init_json_preserves_single_object_output(mock_init):
    mock_init.return_value = CommandResult(
        command="init",
        data={
            "dataset": "mimic-iv-demo",
            "db_path": None,
            "parquet_root": None,
            "raw_root": None,
            "steps": [],
        },
    )

    result = runner.invoke(app, ["init", "mimic-iv-demo", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dataset"] == "mimic-iv-demo"
    assert len(result.stdout.strip().splitlines()) > 1
    assert not result.stdout.lstrip().startswith('{"version"')


@patch("m4.cli.initialize_dataset_service")
def test_init_json_events_ndjson_wraps_final_result(mock_init):
    mock_init.return_value = CommandResult(
        command="init",
        data={
            "dataset": "mimic-iv-demo",
            "db_path": None,
            "parquet_root": None,
            "raw_root": None,
            "steps": [],
        },
    )

    result = runner.invoke(
        app,
        ["init", "mimic-iv-demo", "--json", "--events", "ndjson", "--no-interactive"],
    )

    assert result.exit_code == 0
    events = _ndjson_lines(result.stdout)
    assert events[0]["event"] == "operation_started"
    assert events[-1]["event"] == "operation_completed"
    assert events[-1]["result"]["ok"] is True
    assert events[-1]["result"]["dataset"] == "mimic-iv-demo"


@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_download_missing_credentials_returns_structured_error(
    mock_parquet_root, mock_db_path, tmp_path
):
    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = tmp_path / "mimic.duckdb"

    result = runner.invoke(
        app,
        ["init", "mimic-iv", "--json", "--no-interactive", "--download"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_credentials"


@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_events_invalid_physionet_credentials_redacts_password(
    mock_parquet_root, mock_db_path, tmp_path
):
    class UnauthorizedResponse:
        def __init__(self):
            self.status_code = 401
            self.reason = "Unauthorized"
            self.content = b""
            self.headers = {}

    class Session:
        def __init__(self):
            self.headers = {}
            self.auth = None

        def get(self, *args, **kwargs):
            return UnauthorizedResponse()

    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = tmp_path / "mimic.duckdb"
    credentials_path = tmp_path / "physionet.json"
    credentials_path.write_text(
        json.dumps({"username": "alice", "password": "do-not-print"})
    )

    with patch("m4.data_io.requests.Session", Session):
        result = runner.invoke(
            app,
            [
                "init",
                "mimic-iv",
                "--json",
                "--events",
                "ndjson",
                "--no-interactive",
                "--download",
                "--physionet-credentials-file",
                str(credentials_path),
            ],
        )

    assert result.exit_code == 1
    events = _ndjson_lines(result.stdout)
    assert events[-1]["event"] == "operation_failed"
    assert events[-1]["error"]["code"] == "physionet_auth_failed"
    assert "do-not-print" not in result.stdout
    assert "do-not-print" not in result.stderr


def test_config_validation_bigquery_with_db_path():
    """Test that bigquery backend rejects db-path parameter."""
    result = runner.invoke(
        app, ["config", "claude", "--backend", "bigquery", "--db-path", "/test/path"]
    )
    # should fail when db-path is provided with bigquery
    assert result.exit_code == 1
    assert "db-path can only be used with --backend duckdb" in result.output


@patch("m4.cli.get_bigquery_project_id", return_value=None)
def test_config_validation_bigquery_requires_project_id(mock_get_project):
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
@patch("m4.cli.get_active_backend", return_value="duckdb")
def test_config_claude_success(mock_backend, mock_subprocess):
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
@patch("m4.cli.get_active_backend", return_value="duckdb")
def test_config_universal_quick_mode(mock_backend, mock_subprocess):
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
@patch("m4.cli.get_active_backend", return_value="duckdb")
def test_config_script_failure(mock_backend, mock_subprocess):
    """Test error handling when config script fails."""
    mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd")

    result = runner.invoke(app, ["config", "claude"])
    # command should return failure exit code when subprocess fails
    assert result.exit_code == 1
    # Just verify that the command failed with the right exit code
    # The specific error message may vary


@patch("subprocess.run")
@patch("m4.cli.get_active_backend", return_value="duckdb")
@patch("m4.cli.get_default_database_path")
@patch("m4.cli.get_active_dataset")
def test_config_claude_infers_db_path_demo(
    mock_active, mock_get_default, mock_backend, mock_subprocess
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
@patch("m4.cli.get_active_backend", return_value="duckdb")
@patch("m4.cli.get_default_database_path")
@patch("m4.cli.get_active_dataset")
def test_config_claude_infers_db_path_full(
    mock_active, mock_get_default, mock_backend, mock_subprocess
):
    mock_active.return_value = "mimic-iv"
    mock_get_default.return_value = Path("/tmp/inferred-full.duckdb")
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])
    assert result.exit_code == 0

    call_args = mock_subprocess.call_args[0][0]
    assert "--db-path" not in call_args


@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets")
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


@patch("m4.services.use.get_active_backend", return_value="duckdb")
@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets")
def test_use_json_success_includes_warning_codes(
    mock_detect, mock_set_active, mock_backend
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["use", "mimic-iv", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["command"] == "use"
    assert payload["active_dataset"] == "mimic-iv"
    assert payload["backend"] == "duckdb"
    assert payload["dataset"]["name"] == "mimic-iv"
    assert payload["dataset"]["db_present"] is False
    assert payload["warnings"] == ["local_db_missing"]
    assert "Active dataset set" not in result.stdout
    mock_set_active.assert_called_once_with("mimic-iv")


@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets", return_value={})
def test_use_json_dataset_not_found_emits_error(mock_detect, mock_set_active):
    result = runner.invoke(app, ["use", "missing-dataset", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "use"
    assert payload["error"]["code"] == "dataset_not_found"
    assert "Dataset Not Found" not in result.stdout
    mock_set_active.assert_not_called()


@patch("m4.services.use.get_active_backend", return_value="bigquery")
@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets")
def test_use_json_backend_incompatible_emits_error(
    mock_detect, mock_set_active, mock_backend
):
    mock_detect.return_value = {
        "mimic-iv-demo": {
            "parquet_present": True,
            "db_present": True,
            "parquet_root": "/tmp/demo",
            "db_path": "/tmp/demo.duckdb",
        },
    }

    result = runner.invoke(app, ["use", "mimic-iv-demo", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "backend_incompatible"
    assert "Backend Incompatible" not in result.stdout
    mock_set_active.assert_not_called()


@patch("m4.services.status.compute_parquet_dir_size", return_value=123)
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
@patch("m4.services.status.detect_available_local_datasets")
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
    # Derived status line should be present
    assert "Derived:" in result.stdout


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.verify_table_rowcount", return_value=123)
@patch("m4.services.status.compute_parquet_dir_size", return_value=1024**3)
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_json_outputs_parseable_json_without_rich_markup(
    mock_active,
    mock_detect,
    mock_size,
    mock_rowcount,
    mock_backend,
    mock_project,
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": True,
            "db_present": True,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["version"] == 1
    assert payload["active_dataset"] == "mimic-iv"
    assert len(payload["datasets"]) == 1
    assert payload["datasets"][0]["warnings"] == []

    rich_fragments = ["[bold]", "[success]", "─", "│", "__  __", "Medical Data"]
    assert not any(fragment in result.stdout for fragment in rich_fragments)


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_all_json_includes_all_mocked_datasets(
    mock_active,
    mock_detect,
    mock_backend,
    mock_project,
):
    mock_detect.return_value = {
        "mimic-iv-demo": {
            "parquet_present": False,
            "db_present": False,
            "parquet_root": "/tmp/demo",
            "db_path": "/tmp/demo.duckdb",
        },
        "mimic-iv": {
            "parquet_present": False,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["status", "--all", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {dataset["name"] for dataset in payload["datasets"]} == {
        "mimic-iv-demo",
        "mimic-iv",
    }


@patch("m4.services.status.verify_table_rowcount")
@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_all_json_does_not_probe_row_counts(
    mock_active,
    mock_detect,
    mock_backend,
    mock_project,
    mock_rowcount,
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": True,
            "db_present": True,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["status", "--all", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["datasets"][0]["row_count"] is None
    mock_rowcount.assert_not_called()


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.detect_available_local_datasets", return_value={})
@patch(
    "m4.services.status.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_status_json_no_active_dataset_returns_empty_dataset_list(
    mock_active,
    mock_detect,
    mock_backend,
    mock_project,
):
    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "version": 1,
        "active_dataset": None,
        "backend": "duckdb",
        "bigquery_project_id": None,
        "datasets": [],
    }


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.compute_parquet_dir_size")
@patch("m4.services.status.verify_table_rowcount")
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_json_missing_local_files_are_not_errors(
    mock_active,
    mock_detect,
    mock_rowcount,
    mock_size,
    mock_backend,
    mock_project,
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": False,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    dataset = json.loads(result.stdout)["datasets"][0]
    assert dataset["parquet_present"] is False
    assert dataset["db_present"] is False
    assert dataset["parquet_size_gb"] is None
    assert dataset["row_count"] is None
    mock_size.assert_not_called()
    mock_rowcount.assert_not_called()


@patch("m4.services.status.get_bigquery_project_id", return_value="allowed-project")
@patch("m4.services.status.get_active_backend", return_value="bigquery")
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_json_excludes_secret_values_but_allows_project_id(
    mock_active,
    mock_detect,
    mock_backend,
    mock_project,
    monkeypatch,
):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/secret-service.json")
    monkeypatch.setenv("M4_PASSWORD", "super-secret-password")
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": False,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    assert "allowed-project" in result.stdout
    assert "secret-service" not in result.stdout
    assert "super-secret-password" not in result.stdout


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_json_redacts_paths_by_default_and_exposes_with_paths(
    mock_active,
    mock_detect,
    mock_backend,
    mock_project,
):
    mock_detect.return_value = {
        "mimic-iv": {
            "raw_present": False,
            "parquet_present": False,
            "db_present": False,
            "raw_root": "/tmp/m4/raw_files/mimic-iv",
            "parquet_root": "/tmp/m4/parquet/mimic-iv",
            "db_path": "/tmp/m4/databases/mimic.duckdb",
        }
    }

    default_result = runner.invoke(app, ["status", "--json", "--no-interactive"])
    paths_result = runner.invoke(
        app, ["status", "--json", "--paths", "--no-interactive"]
    )

    assert default_result.exit_code == 0
    default_dataset = json.loads(default_result.stdout)["datasets"][0]
    assert default_dataset["setup_state"] == "credentials_required"
    assert default_dataset["requires_authentication"] is True
    assert "raw_root" not in default_dataset
    assert "/tmp/m4" not in default_result.stdout

    assert paths_result.exit_code == 0
    paths_dataset = json.loads(paths_result.stdout)["datasets"][0]
    assert paths_dataset["raw_root"] == str(
        Path("/tmp/m4/raw_files/mimic-iv").resolve()
    )
    assert paths_dataset["parquet_root"] == str(
        Path("/tmp/m4/parquet/mimic-iv").resolve()
    )
    assert paths_dataset["db_path"] == str(
        Path("/tmp/m4/databases/mimic.duckdb").resolve()
    )


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch(
    "m4.services.status.verify_table_rowcount",
    side_effect=Exception("No files found that match the pattern"),
)
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_json_path_mismatch_emits_warning(
    mock_active, mock_detect, mock_rowcount, mock_backend, mock_project
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": False,
            "db_present": True,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    dataset = json.loads(result.stdout)["datasets"][0]
    assert dataset["warnings"] == ["parquet_path_mismatch"]
    assert "_row_count_error" not in dataset


@patch("m4.services.status.get_bigquery_project_id", return_value=None)
@patch("m4.services.status.get_active_backend", return_value="duckdb")
@patch(
    "m4.services.status.verify_table_rowcount",
    side_effect=Exception("No files found that match the pattern"),
)
@patch("m4.services.status.detect_available_local_datasets")
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
def test_status_human_path_mismatch_prints_warning(
    mock_active, mock_detect, mock_rowcount, mock_backend, mock_project
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": False,
            "db_present": True,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Database views may point to wrong parquet location" in result.stdout


def test_status_derived_json_is_invalid_combination():
    result = runner.invoke(app, ["status", "--derived", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "status"
    assert payload["error"]["code"] == "invalid_option"
    assert "Active dataset" not in result.stdout
    assert "__  __" not in result.stdout


@patch("m4.cli.list_materialized_tables")
@patch("m4.cli.get_default_database_path")
@patch("m4.cli.get_active_backend", return_value="duckdb")
@patch("m4.cli.get_active_dataset", return_value="mimic-iv")
def test_status_derived_flag(
    mock_active, mock_backend, mock_db_path, mock_mat, tmp_path
):
    """Test m4 status --derived shows grouped category listing."""
    db_file = tmp_path / "mimic_iv.duckdb"
    db_file.touch()
    mock_db_path.return_value = db_file
    mock_mat.return_value = {"sofa", "sepsis3", "age"}

    result = runner.invoke(app, ["status", "--derived"])
    assert result.exit_code == 0
    assert "Derived tables for mimic-iv" in result.stdout
    assert "materialized" in result.stdout


@patch("m4.cli.get_active_backend", return_value="duckdb")
@patch("m4.cli.get_active_dataset", return_value="mimic-iv-demo")
def test_status_derived_flag_unsupported_dataset(mock_active, mock_backend):
    """Test --derived with a dataset that has no derived support."""
    result = runner.invoke(app, ["status", "--derived"])
    assert result.exit_code == 0
    assert "not available" in result.stdout


@patch("m4.cli.get_active_dataset", return_value=None)
def test_status_derived_flag_no_active_dataset(mock_active):
    """Test --derived with no active dataset set."""
    result = runner.invoke(app, ["status", "--derived"])
    assert result.exit_code == 0
    assert "No active dataset" in result.stdout


# ----------------------------------------------------------------
# Backend command tests
# ----------------------------------------------------------------


@patch("m4.services.backend.set_active_backend")
def test_backend_duckdb_happy_path(mock_set_backend):
    """Test setting backend to duckdb."""
    result = runner.invoke(app, ["backend", "duckdb"])

    assert result.exit_code == 0
    assert "Active backend set to 'duckdb'" in result.stdout
    mock_set_backend.assert_called_once_with("duckdb")


@patch("m4.services.backend.get_bigquery_project_id", return_value="my-project")
@patch("m4.services.backend.set_active_backend")
@patch("m4.services.backend.get_active_dataset")
@patch("m4.services.backend.DatasetRegistry.get")
def test_backend_bigquery_happy_path(
    mock_registry, mock_get_dataset, mock_set_backend, mock_get_project
):
    """Test setting backend to bigquery."""
    # Mock a dataset that supports BigQuery
    mock_get_dataset.return_value = "mimic-iv"
    mock_ds = MagicMock()
    mock_ds.bigquery_dataset_ids = ["mimiciv_hosp"]
    mock_registry.return_value = mock_ds

    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 0
    assert "Active backend set to 'bigquery'" in result.stdout
    assert "BigQuery requires valid Google Cloud credentials" in result.stdout
    mock_set_backend.assert_called_once_with("bigquery")


@patch("m4.services.backend.set_active_backend")
@patch("m4.services.backend.get_active_dataset")
@patch("m4.services.backend.DatasetRegistry.get")
def test_backend_bigquery_blocks_unsupported_dataset(
    mock_registry, mock_get_dataset, mock_set_backend
):
    """Test that switching to bigquery is blocked when dataset doesn't support BQ."""
    # Mock a dataset that doesn't support BigQuery
    mock_get_dataset.return_value = "custom-dataset"
    mock_ds = MagicMock()
    mock_ds.bigquery_dataset_ids = []  # No BigQuery support
    mock_registry.return_value = mock_ds

    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 1
    assert "Dataset Incompatible" in result.stdout
    assert "not available on BigQuery" in result.stdout
    mock_set_backend.assert_not_called()


def test_backend_invalid_choice():
    """Test that invalid backend choice fails with helpful message."""
    result = runner.invoke(app, ["backend", "mysql"])

    assert result.exit_code == 1
    assert "Invalid Backend" in result.stdout
    assert "mysql" in result.stdout
    assert "bigquery" in result.stdout
    assert "duckdb" in result.stdout


@patch("m4.services.backend.get_bigquery_project_id", return_value="my-project")
@patch("m4.services.backend.set_active_backend")
@patch(
    "m4.services.backend.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_backend_case_insensitive(mock_get_dataset, mock_set_backend, mock_get_project):
    """Test that backend choice is case-insensitive."""
    result = runner.invoke(app, ["backend", "BIGQUERY"])

    assert result.exit_code == 0
    mock_set_backend.assert_called_once_with("bigquery")


@patch("m4.services.backend.set_active_backend")
def test_backend_duckdb_shows_init_hint(mock_set_backend):
    """Test that duckdb backend shows initialization hint."""
    result = runner.invoke(app, ["backend", "duckdb"])

    assert result.exit_code == 0
    assert "DuckDB uses local database files" in result.stdout
    assert "m4 init" in result.stdout


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.get_active_dataset", return_value="mimic-iv")
@patch("m4.services.backend.set_active_backend")
def test_backend_json_duckdb_success(
    mock_set_backend, mock_get_dataset, mock_get_project
):
    result = runner.invoke(app, ["backend", "duckdb", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "version": 1,
        "ok": True,
        "command": "backend",
        "backend": "duckdb",
        "active_dataset": "mimic-iv",
        "bigquery_project_id": None,
        "warnings": [],
    }
    assert "Active backend set" not in result.stdout
    mock_set_backend.assert_called_once_with("duckdb")


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.get_active_dataset", return_value="mimic-iv")
@patch("m4.services.backend.set_active_backend")
def test_backend_json_bigquery_with_project_id_success(
    mock_set_backend, mock_get_dataset, mock_set_project
):
    result = runner.invoke(
        app, ["backend", "bigquery", "--project-id", "my-project", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["command"] == "backend"
    assert payload["backend"] == "bigquery"
    assert payload["active_dataset"] == "mimic-iv"
    assert payload["bigquery_project_id"] == "my-project"
    assert payload["warnings"] == []
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("my-project")


@patch("m4.services.backend.set_active_backend")
def test_backend_json_invalid_backend_emits_error(mock_set_backend):
    result = runner.invoke(app, ["backend", "mysql", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_backend"
    assert "Invalid Backend" not in result.stdout
    mock_set_backend.assert_not_called()


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
def test_backend_json_duckdb_rejects_project_id(mock_set_backend, mock_set_project):
    result = runner.invoke(app, ["backend", "duckdb", "--project-id", "x", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_option"
    assert "project-id can only be used with bigquery" in payload["error"]["message"]
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


@patch("m4.services.backend.set_active_backend")
@patch("m4.services.backend.get_active_dataset", return_value="mimic-iv-demo")
def test_backend_json_bigquery_blocks_incompatible_active_dataset(
    mock_get_dataset, mock_set_backend
):
    result = runner.invoke(app, ["backend", "bigquery", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "dataset_incompatible"
    assert "Dataset Incompatible" not in result.stdout
    mock_set_backend.assert_not_called()


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
@patch(
    "m4.services.backend.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_backend_json_bigquery_requires_project_id(
    mock_get_dataset, mock_set_backend, mock_set_project, mock_get_project
):
    result = runner.invoke(app, ["backend", "bigquery", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "project_id_required"
    assert "Project ID Required" not in result.stdout
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


# ----------------------------------------------------------------
# Init command: derived table skip/force behavior
# ----------------------------------------------------------------


class TestInitDerivedTableSkipForce:
    """Tests for derived table skip/force behavior at the end of m4 init.

    These tests mock the entire init pipeline to focus on the derived-table
    section, which only runs for mimic-iv on the duckdb backend.
    """

    def _invoke_init(self, tmp_path, *, force=False, derived_count=0, input_text=None):
        """Helper that mocks the full init pipeline and invokes m4 init mimic-iv.

        Returns the CliRunner result and the mock for materialize_all.
        """
        pq_dir = tmp_path / "parquet" / "mimic-iv"
        pq_dir.mkdir(parents=True)
        (pq_dir / "test.parquet").touch()

        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()

        args = ["init", "mimic-iv"]
        if force:
            args.append("--force")

        with (
            patch("m4.config._find_project_root_from_cwd", return_value=Path.cwd()),
            patch("m4.cli.get_dataset_parquet_root", return_value=pq_dir),
            patch("m4.cli.get_default_database_path", return_value=db_file),
            patch("m4.cli.init_duckdb_from_parquet", return_value=True),
            patch("m4.cli.verify_table_rowcount", return_value=100),
            patch("m4.cli.set_active_dataset"),
            patch("m4.cli.get_active_backend", return_value="duckdb"),
            patch("m4.cli.get_derived_table_count", return_value=derived_count),
            patch("m4.cli.materialize_all") as mock_materialize,
        ):
            mock_materialize.return_value = ["sofa", "sepsis3", "age"]
            result = runner.invoke(app, args, input=input_text)
            return result, mock_materialize

    def test_skips_prompt_when_derived_exist(self, tmp_path):
        """When derived tables exist and no --force, skip prompt and notify."""
        result, mock_materialize = self._invoke_init(tmp_path, derived_count=42)

        assert result.exit_code == 0
        assert "already materialized" in result.stdout
        assert "42 tables" in result.stdout
        mock_materialize.assert_not_called()

    def test_force_rematerializes_without_prompt(self, tmp_path):
        """When --force and derived tables exist, rematerialize without prompt."""
        result, mock_materialize = self._invoke_init(
            tmp_path, force=True, derived_count=42
        )

        assert result.exit_code == 0
        mock_materialize.assert_called_once()

    def test_prompts_when_no_derived_exist(self, tmp_path):
        """When no derived tables exist, prompt the user (answer no)."""
        result, mock_materialize = self._invoke_init(
            tmp_path, derived_count=0, input_text="n\n"
        )

        assert result.exit_code == 0
        assert "Materialize derived tables?" in result.stdout
        mock_materialize.assert_not_called()

    def test_prompts_and_materializes_on_yes(self, tmp_path):
        """When no derived tables exist and user says yes, materialize."""
        result, mock_materialize = self._invoke_init(
            tmp_path, derived_count=0, input_text="y\n"
        )

        assert result.exit_code == 0
        mock_materialize.assert_called_once()


# ----------------------------------------------------------------
# Backend command: --project-id tests
# ----------------------------------------------------------------


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
@patch(
    "m4.services.backend.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_backend_bigquery_with_project_id(
    mock_get_dataset, mock_set_backend, mock_set_project
):
    """Test backend bigquery --project-id persists project ID."""
    result = runner.invoke(
        app, ["backend", "bigquery", "--project-id", "my-gcp-project"]
    )

    assert result.exit_code == 0
    assert "Active backend set to 'bigquery'" in result.stdout
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("my-gcp-project")


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
def test_backend_duckdb_rejects_project_id(mock_set_backend, mock_set_project):
    """Test backend duckdb --project-id is rejected."""
    result = runner.invoke(app, ["backend", "duckdb", "--project-id", "my-gcp-project"])

    assert result.exit_code == 1
    assert "project-id can only be used with bigquery" in result.output
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
@patch(
    "m4.services.backend.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_backend_bigquery_without_project_id_errors(
    mock_get_dataset, mock_set_backend, mock_set_project, mock_get_project
):
    """Test backend bigquery without --project-id and no config project ID errors."""
    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 1
    assert "Project ID Required" in result.stdout
    assert "m4 backend bigquery --project-id" in result.stdout
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


@patch("m4.services.backend.get_bigquery_project_id", return_value="existing-project")
@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
@patch(
    "m4.services.backend.get_active_dataset",
    side_effect=DatasetError("No active dataset"),
)
def test_backend_bigquery_without_flag_uses_config_project_id(
    mock_get_dataset, mock_set_backend, mock_set_project, mock_get_project
):
    """Test backend bigquery without --project-id succeeds when project ID is in config."""
    result = runner.invoke(app, ["backend", "bigquery"])

    assert result.exit_code == 0
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_not_called()


# ----------------------------------------------------------------
# Config command: persistence to config.json tests
# ----------------------------------------------------------------


@patch("subprocess.run")
@patch("m4.cli.set_bigquery_project_id")
@patch("m4.cli.set_active_backend")
def test_config_claude_bigquery_persists_to_config(
    mock_set_backend, mock_set_project, mock_subprocess
):
    """Test that m4 config claude --backend bigquery persists backend and project_id."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(
        app,
        ["config", "claude", "--backend", "bigquery", "--project-id", "my-project"],
    )

    assert result.exit_code == 0
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("my-project")


@patch("subprocess.run")
@patch("m4.cli.get_active_backend", return_value="duckdb")
@patch("m4.cli.set_bigquery_project_id")
@patch("m4.cli.set_active_backend")
def test_config_claude_without_backend_flag_does_not_overwrite(
    mock_set_backend, mock_set_project, mock_get_backend, mock_subprocess
):
    """Test that m4 config claude without --backend does not overwrite the active backend."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])

    assert result.exit_code == 0
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


@patch("subprocess.run")
@patch("m4.cli.get_bigquery_project_id", return_value="inferred-project")
@patch("m4.cli.get_active_backend", return_value="bigquery")
def test_config_claude_infers_bigquery_project_from_config(
    mock_backend, mock_get_project, mock_subprocess
):
    """Test that m4 config claude infers project-id from config.json when backend is bigquery."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(app, ["config", "claude"])

    assert result.exit_code == 0
    # Verify the setup script was called with --backend bigquery and --project-id
    call_args = mock_subprocess.call_args[0][0]
    assert "--backend" in call_args
    assert "bigquery" in call_args
    assert "--project-id" in call_args
    assert "inferred-project" in call_args


@patch("m4.cli.get_bigquery_project_id", return_value=None)
@patch("m4.cli.get_active_backend", return_value="bigquery")
def test_config_claude_errors_when_bigquery_no_project_in_config(
    mock_backend, mock_get_project
):
    """Test that m4 config claude errors when backend is bigquery but no project-id anywhere."""
    result = runner.invoke(app, ["config", "claude"])

    assert result.exit_code == 1
    assert "BigQuery backend requires a project ID" in result.output


@patch("subprocess.run")
@patch("m4.cli.set_bigquery_project_id")
@patch("m4.cli.set_active_backend")
def test_config_universal_bigquery_persists_to_config(
    mock_set_backend, mock_set_project, mock_subprocess
):
    """Test that m4 config --quick --backend bigquery persists to config.json."""
    mock_subprocess.return_value = MagicMock(returncode=0)

    result = runner.invoke(
        app,
        [
            "config",
            "--quick",
            "--backend",
            "bigquery",
            "--project-id",
            "my-project",
        ],
    )

    assert result.exit_code == 0
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("my-project")


# ----------------------------------------------------------------
# Status command: BigQuery project ID display
# ----------------------------------------------------------------


@patch("m4.services.status.get_bigquery_project_id", return_value="my-gcp-project")
@patch("m4.services.status.get_active_backend", return_value="bigquery")
@patch("m4.services.status.compute_parquet_dir_size", return_value=123)
@patch("m4.services.status.get_active_dataset", return_value="mimic-iv")
@patch("m4.services.status.detect_available_local_datasets")
def test_status_bigquery_shows_project_id(
    mock_detect, mock_active, mock_size, mock_backend, mock_get_project
):
    """Test that m4 status shows BigQuery project ID in parentheses."""
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        },
    }

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "bigquery" in result.stdout
    assert "my-gcp-project" in result.stdout
