import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import m4.config as cfg_mod
from m4 import M4Client, get_capabilities
from m4.cli import app
from m4.core.datasets import DatasetRegistry
from m4.data_io import DatasetDownloadError, PhysioNetCredentials
from m4.services.capabilities import build_capabilities_manifest
from m4.services.download import (
    build_wget_command,
    download_dataset_service,
    validate_raw_layout,
)
from m4.services.results import CommandError, CommandResult
from m4.services.setup import doctor_service, setup_agent_service

runner = CliRunner()


def _install_custom_dataset(tmp_path, monkeypatch, name="custom-ed"):
    datasets_dir = tmp_path / "m4_data" / "datasets"
    datasets_dir.mkdir(parents=True)
    (datasets_dir / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "description": "Custom test dataset",
                "file_listing_url": "https://physionet.org/files/custom-ed/1.0/",
                "requires_authentication": True,
                "modalities": ["TABULAR"],
                "schema_mapping": {"": "custom_ed"},
            }
        )
    )
    monkeypatch.setattr(cfg_mod, "_CUSTOM_DATASETS_DIR", datasets_dir)
    DatasetRegistry.reset()


def teardown_function():
    DatasetRegistry.reset()


def test_capabilities_manifest_shape():
    manifest = build_capabilities_manifest()

    assert manifest["schema_version"] == 1
    assert "cli" in manifest["interfaces"]
    assert "mcp" in manifest["interfaces"]
    assert any(dataset["name"] == "mimic-iv" for dataset in manifest["datasets"])
    assert any(tool["name"] == "execute_query" for tool in manifest["tools"])
    assert (
        manifest["provenance_policy"]["event_export_command"]
        == "m4 provenance export --json"
    )
    commands = {command["name"]: command for command in manifest["commands"]}
    assert "agent-env" in commands
    assert "--physionet-credentials-file" in commands["download"]["flags"]
    assert "--events" in commands["download"]["flags"]
    assert commands["setup-agent"]["mutates"] is False
    assert commands["setup-agent"]["mutates_with"] == ["--apply"]
    assert "--apply" in commands["quickstart"]["flags"]


def test_capabilities_manifest_structural_contract():
    manifest = build_capabilities_manifest()

    assert {
        "schema_version",
        "interfaces",
        "runtime",
        "commands",
        "tools",
        "datasets",
        "limits",
        "concepts",
        "provenance_policy",
    }.issubset(manifest)

    for command in manifest["commands"]:
        assert {"name", "flags", "mutates"}.issubset(command)

    for dataset in manifest["datasets"]:
        assert {
            "name",
            "requires_authentication",
            "modalities",
            "bigquery",
            "verification_table",
            "schema_mapping",
            "expected_local_layout",
        }.issubset(dataset)
        assert {
            "available",
            "project_id",
            "dataset_ids",
            "schema_mapping",
        }.issubset(dataset["bigquery"])
        assert {
            "recommended_raw_root",
            "raw_subdirectories",
            "parquet_root",
            "duckdb_filename",
        }.issubset(dataset["expected_local_layout"])

    for tool in manifest["tools"]:
        assert {
            "name",
            "description",
            "input_fields",
            "required_modalities",
            "compatible_datasets",
            "supported_datasets",
        }.issubset(tool)

    assert {
        "query_row_limit_default",
        "path_redaction_default",
        "supported_backends",
        "conversion_env",
    }.issubset(manifest["limits"])
    assert {"derived_tables", "skills"}.issubset(manifest["concepts"])
    assert {
        "telemetry_destination",
        "path_redaction",
        "event_export_command",
        "non_phi_policy",
    }.issubset(manifest["provenance_policy"])


def test_capabilities_manifest_agent_command_contract():
    manifest = build_capabilities_manifest()
    commands = {command["name"]: command for command in manifest["commands"]}
    expected = {
        "download",
        "init",
        "setup-agent",
        "quickstart",
        "doctor",
        "capabilities",
        "schema",
        "query",
    }

    assert expected.issubset(commands)
    for name in expected:
        assert isinstance(commands[name]["flags"], list)
        assert isinstance(commands[name]["mutates"], bool)
    assert commands["setup-agent"]["mutates_with"] == ["--apply"]
    assert commands["quickstart"]["mutates_with"] == ["--apply"]


def test_capabilities_manifest_builtin_dataset_identity_contract():
    manifest = build_capabilities_manifest()
    datasets = {dataset["name"]: dataset for dataset in manifest["datasets"]}
    expected = {"mimic-iv-demo", "mimic-iv", "mimic-iv-note", "eicu"}

    assert expected.issubset(datasets)
    for name in expected:
        dataset = datasets[name]
        assert dataset["name"] == name
        assert isinstance(dataset["requires_authentication"], bool)
        assert dataset["modalities"]
        assert dataset["expected_local_layout"]["recommended_raw_root"]
        assert dataset["expected_local_layout"]["duckdb_filename"]
        assert "available" in dataset["bigquery"]
        assert "dataset_ids" in dataset["bigquery"]
        assert "verification_table" in dataset


def test_python_get_capabilities_exports_manifest():
    assert get_capabilities()["schema_version"] == 1


def test_m4client_capabilities_exports_manifest():
    client = M4Client(dataset="mimic-iv-demo", backend="duckdb")

    assert client.capabilities()["schema_version"] == 1


def test_capabilities_cli_json():
    result = runner.invoke(app, ["capabilities", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert "datasets" in payload


def test_agent_env_formats():
    dotenv = runner.invoke(app, ["agent-env", "--dataset", "mimic-iv-demo"])
    assert dotenv.exit_code == 0
    assert "M4_BACKEND=" in dotenv.stdout

    json_result = runner.invoke(
        app, ["agent-env", "--dataset", "mimic-iv-demo", "--format", "json"]
    )
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["command"] == "agent-env"

    text = runner.invoke(
        app, ["agent-env", "--dataset", "mimic-iv-demo", "--format", "text"]
    )
    assert text.exit_code == 0
    assert "Recommended commands" in text.stdout


def test_agent_env_invalid_format():
    result = runner.invoke(app, ["agent-env", "--format", "yaml"])

    assert result.exit_code == 1
    assert "Unsupported format" in result.stdout


def test_credentialed_download_returns_wget_guidance(tmp_path):
    result = download_dataset_service("mimic-iv", target=str(tmp_path))

    assert isinstance(result, CommandResult)
    assert result.ok is True
    assert result.data["status"] == "blocked"
    assert "--cut-dirs=3 -nH" in result.data["wget_command"]
    assert "--ask-password" in result.data["wget_command"]
    assert result.data["next_steps"][0].endswith("mimiciv/")


def test_eicu_download_returns_top_level_raw_layout_guidance(tmp_path):
    result = download_dataset_service("eicu", target=str(tmp_path))

    assert isinstance(result, CommandResult)
    assert result.data["status"] == "blocked"
    assert "--cut-dirs=3 -nH" in result.data["wget_command"]
    assert "https://physionet.org/files/eicu-crd/2.0/" in result.data["wget_command"]


def test_download_service_loads_custom_dataset_and_quotes_target(tmp_path, monkeypatch):
    _install_custom_dataset(tmp_path, monkeypatch)
    target = tmp_path / "raw data"

    result = download_dataset_service("custom-ed", target=str(target))

    assert isinstance(result, CommandResult)
    assert result.data["status"] == "blocked"
    assert result.data["dataset"] == "custom-ed"
    assert "--cut-dirs=3 -nH" in result.data["wget_command"]
    assert f"-P '{target}'" in result.data["wget_command"]
    assert result.data["next_steps"][0].endswith("/custom-ed/1.0/")


def test_wget_command_cut_dirs_follows_listing_url_path(tmp_path, monkeypatch):
    _install_custom_dataset(tmp_path, monkeypatch)
    cfg_mod.ensure_custom_datasets_loaded()
    dataset = DatasetRegistry.get("custom-ed")

    command = build_wget_command(dataset, tmp_path / "target with spaces")

    assert "--cut-dirs=3 -nH" in command
    assert f"-P '{tmp_path / 'target with spaces'}'" in command


def test_public_download_service_uses_downloader(tmp_path):
    with patch(
        "m4.services.download.download_dataset", return_value=True
    ) as mock_download:
        result = download_dataset_service("mimic-iv-demo", target=str(tmp_path))

    assert isinstance(result, CommandResult)
    assert result.data["status"] == "completed"
    mock_download.assert_called_once()


def test_public_download_cli_json_uses_downloader(tmp_path):
    with patch(
        "m4.services.download.download_dataset", return_value=True
    ) as mock_download:
        result = runner.invoke(
            app, ["download", "mimic-iv-demo", "--target", str(tmp_path), "--json"]
        )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "download"
    assert payload["status"] == "completed"
    mock_download.assert_called_once()


def test_credentialed_download_cli_without_credentials_returns_guidance():
    result = runner.invoke(app, ["download", "mimic-iv", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["wget_command"]
    assert "None" not in "\n".join(payload["next_steps"])


def test_init_credentialed_guidance_matches_download_command(tmp_path):
    pq_root = tmp_path / "m4_data" / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)

    with (
        patch("m4.config._find_project_root_from_cwd", return_value=Path.cwd()),
        patch("m4.cli.get_dataset_parquet_root", return_value=pq_root),
    ):
        result = runner.invoke(app, ["init", "mimic-iv", "--no-interactive"])

    assert result.exit_code == 0
    assert "--cut-dirs=3 -nH" in result.output
    assert "raw_files/mimic-iv" in result.output.replace("\n", "")


def test_credentialed_download_with_credentials_delegates(tmp_path):
    creds = PhysioNetCredentials(username="alice", password="secret")
    with patch(
        "m4.services.download.download_dataset", return_value=True
    ) as mock_download:
        result = download_dataset_service(
            "mimic-iv",
            target=str(tmp_path),
            physionet_credentials=creds,
        )

    assert isinstance(result, CommandResult)
    assert result.data["status"] == "completed"
    mock_download.assert_called_once()
    assert mock_download.call_args.kwargs["credentials"] == creds


def test_credentialed_download_cli_with_credentials_file_delegates(tmp_path):
    creds_file = tmp_path / "physionet.json"
    creds_file.write_text(json.dumps({"username": "alice", "password": "secret"}))

    with patch(
        "m4.services.download.download_dataset", return_value=True
    ) as mock_download:
        result = runner.invoke(
            app,
            [
                "download",
                "mimic-iv",
                "--target",
                str(tmp_path),
                "--json",
                "--physionet-credentials-file",
                str(creds_file),
            ],
        )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    mock_download.assert_called_once()
    assert mock_download.call_args.kwargs["credentials"].username == "alice"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("physionet_auth_failed", "bad credentials"),
        ("download_network_failed", "network down"),
    ],
)
def test_download_errors_become_stable_command_errors(tmp_path, code, message):
    with patch(
        "m4.services.download.download_dataset",
        side_effect=DatasetDownloadError(code, message),
    ):
        result = download_dataset_service(
            "mimic-iv",
            target=str(tmp_path),
            physionet_credentials=PhysioNetCredentials("alice", "secret"),
        )

    assert isinstance(result, CommandError)
    assert result.code == code
    assert result.message == message


def test_layout_validation_detects_nested_and_missing_dirs(tmp_path):
    nested = tmp_path / "physionet.org" / "files" / "mimiciv" / "3.1"
    nested.mkdir(parents=True)
    (nested / "patients.csv.gz").write_bytes(b"")

    result = validate_raw_layout("mimic-iv", tmp_path)

    assert result["ok"] is False
    assert "nested_physionet_layout" in result["warnings"]
    assert "missing_required_subdirectories" in result["warnings"]
    assert "empty_csv_gz" in result["warnings"]


def test_doctor_setup_agent_quickstart_json():
    doctor = runner.invoke(app, ["doctor", "--json"])
    assert doctor.exit_code == 0
    assert json.loads(doctor.stdout)["command"] == "doctor"

    setup = runner.invoke(
        app,
        [
            "setup-agent",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--format",
            "json",
        ],
    )
    assert setup.exit_code == 0
    assert json.loads(setup.stdout)["command"] == "setup-agent"

    quickstart = runner.invoke(app, ["quickstart", "--workflow", "demo", "--json"])
    assert quickstart.exit_code == 0
    assert json.loads(quickstart.stdout)["command"] == "quickstart"


def test_setup_agent_service_loads_custom_dataset(tmp_path, monkeypatch):
    _install_custom_dataset(tmp_path, monkeypatch)

    result = setup_agent_service(
        mode="local",
        client="generic",
        dataset="custom-ed",
        backend="duckdb",
        project_id=None,
    )

    assert isinstance(result, CommandResult)
    assert result.data["environment"]["M4_DATASET"] == "custom-ed"


@patch("m4.services.setup.get_active_backend", return_value="duckdb")
@patch("m4.services.setup.get_active_dataset", return_value="mimic-iv-demo")
@patch("m4.services.setup.collect_status_snapshot")
def test_doctor_only_requires_active_duckdb_dataset(
    mock_status, mock_dataset, mock_backend
):
    mock_status.return_value = {
        "version": 1,
        "active_dataset": "mimic-iv-demo",
        "backend": "duckdb",
        "bigquery_project_id": None,
        "datasets": [
            {
                "name": "mimic-iv-demo",
                "db_present": True,
                "warnings": [],
            },
            {
                "name": "mimic-iv",
                "db_present": False,
                "warnings": [],
            },
        ],
    }

    result = doctor_service()

    assert result.data["summary"]["ok"] is True
    check_names = [check["name"] for check in result.data["checks"]]
    assert "duckdb:mimic-iv-demo" in check_names
    assert "duckdb:mimic-iv" not in check_names
