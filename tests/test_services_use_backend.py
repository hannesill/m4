from unittest.mock import patch

from m4.core.exceptions import DatasetError
from m4.services.backend import set_active_backend_service
from m4.services.results import CommandError, CommandResult
from m4.services.use import set_active_dataset_service


@patch("m4.services.use.get_active_backend", return_value="duckdb")
@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets")
def test_use_service_success_includes_dataset_and_warning_codes(
    mock_detect, mock_set_active, mock_backend
):
    mock_detect.return_value = {
        "mimic-iv": {
            "parquet_present": True,
            "db_present": False,
            "parquet_root": "/tmp/full",
            "db_path": "/tmp/full.duckdb",
        }
    }

    result = set_active_dataset_service("MIMIC-IV")

    assert isinstance(result, CommandResult)
    payload = result.to_json_dict()
    assert payload["active_dataset"] == "mimic-iv"
    assert payload["backend"] == "duckdb"
    assert payload["dataset"]["db_present"] is False
    assert payload["warnings"] == ["local_db_missing"]
    mock_set_active.assert_called_once_with("mimic-iv")


@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets", return_value={})
def test_use_service_dataset_not_found_does_not_mutate(mock_detect, mock_set_active):
    result = set_active_dataset_service("missing")

    assert isinstance(result, CommandError)
    assert result.code == "dataset_not_found"
    mock_set_active.assert_not_called()


@patch("m4.services.use.get_active_backend", return_value="bigquery")
@patch("m4.services.use.set_active_dataset")
@patch("m4.services.use.detect_available_local_datasets")
def test_use_service_blocks_bigquery_incompatible_dataset(
    mock_detect, mock_set_active, mock_backend
):
    mock_detect.return_value = {
        "mimic-iv-demo": {
            "parquet_present": True,
            "db_present": True,
            "parquet_root": "/tmp/demo",
            "db_path": "/tmp/demo.duckdb",
        }
    }

    result = set_active_dataset_service("mimic-iv-demo")

    assert isinstance(result, CommandError)
    assert result.code == "backend_incompatible"
    mock_set_active.assert_not_called()


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.get_active_dataset", return_value="mimic-iv")
@patch("m4.services.backend.set_active_backend")
def test_backend_service_duckdb_success(
    mock_set_backend, mock_get_dataset, mock_get_project
):
    result = set_active_backend_service("duckdb")

    assert isinstance(result, CommandResult)
    assert result.to_json_dict() == {
        "version": 1,
        "ok": True,
        "command": "backend",
        "backend": "duckdb",
        "active_dataset": "mimic-iv",
        "bigquery_project_id": None,
        "warnings": [],
    }
    mock_set_backend.assert_called_once_with("duckdb")


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.get_active_dataset", side_effect=DatasetError("unset"))
@patch("m4.services.backend.set_active_backend")
def test_backend_service_bigquery_persists_project_id(
    mock_set_backend, mock_get_dataset, mock_set_project
):
    result = set_active_backend_service("BIGQUERY", project_id="my-project")

    assert isinstance(result, CommandResult)
    assert result.data["backend"] == "bigquery"
    assert result.data["bigquery_project_id"] == "my-project"
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("my-project")


@patch("m4.services.backend.set_active_backend")
def test_backend_service_invalid_backend_does_not_mutate(mock_set_backend):
    result = set_active_backend_service("mysql")

    assert isinstance(result, CommandError)
    assert result.code == "invalid_backend"
    mock_set_backend.assert_not_called()


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
def test_backend_service_duckdb_rejects_project_id(mock_set_backend, mock_set_project):
    result = set_active_backend_service("duckdb", project_id="x")

    assert isinstance(result, CommandError)
    assert result.code == "invalid_option"
    mock_set_backend.assert_not_called()
    mock_set_project.assert_not_called()


@patch("m4.services.backend.set_active_backend")
@patch("m4.services.backend.get_active_dataset", return_value="mimic-iv-demo")
def test_backend_service_bigquery_blocks_incompatible_active_dataset(
    mock_get_dataset, mock_set_backend
):
    result = set_active_backend_service("bigquery", project_id="my-project")

    assert isinstance(result, CommandError)
    assert result.code == "dataset_incompatible"
    mock_set_backend.assert_not_called()


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.set_active_backend")
@patch("m4.services.backend.get_active_dataset", side_effect=DatasetError("unset"))
def test_backend_service_bigquery_requires_project_id(
    mock_get_dataset, mock_set_backend, mock_get_project
):
    result = set_active_backend_service("bigquery")

    assert isinstance(result, CommandError)
    assert result.code == "project_id_required"
    mock_set_backend.assert_not_called()
