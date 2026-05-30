from unittest.mock import patch

from m4.services.backend import set_active_backend_service
from m4.services.results import CommandError, CommandResult
from m4.services.use import set_active_dataset_service


def test_use_service_returns_migration_error():
    result = set_active_dataset_service("MIMIC-IV")

    assert isinstance(result, CommandError)
    assert result.code == "active_dataset_removed"
    assert "explicit dataset" in result.message
    assert "M4Client(dataset=...)" in (result.hint or "")


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.set_active_backend")
def test_backend_service_duckdb_success(mock_set_backend, mock_get_project):
    result = set_active_backend_service("duckdb")

    assert isinstance(result, CommandResult)
    assert result.to_json_dict() == {
        "version": 1,
        "ok": True,
        "command": "backend",
        "backend": "duckdb",
        "bigquery_project_id": None,
        "warnings": [],
    }
    mock_set_backend.assert_called_once_with("duckdb")


@patch("m4.services.backend.set_bigquery_project_id")
@patch("m4.services.backend.set_active_backend")
def test_backend_service_bigquery_persists_project_id(
    mock_set_backend, mock_set_project
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


@patch("m4.services.backend.get_bigquery_project_id", return_value=None)
@patch("m4.services.backend.set_active_backend")
def test_backend_service_bigquery_requires_project_id(
    mock_set_backend, mock_get_project
):
    result = set_active_backend_service("bigquery")

    assert isinstance(result, CommandError)
    assert result.code == "project_id_required"
    mock_set_backend.assert_not_called()
