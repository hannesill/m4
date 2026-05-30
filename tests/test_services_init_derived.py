from pathlib import Path
from unittest.mock import Mock, patch

from m4.services.init_derived import init_derived_service


def test_init_derived_list_returns_tables():
    result = init_derived_service("mimic-iv", list_only=True)

    assert result.ok is True
    assert result.command == "init-derived"
    assert result.data["status"] == "listed"
    assert "sofa" in result.data["tables"]
    assert result.data["table_count"] == len(result.data["tables"])


def test_init_derived_unknown_dataset_returns_command_error():
    result = init_derived_service("missing")

    assert result.ok is False
    assert result.code == "dataset_not_found"


@patch("m4.services.init_derived.get_active_backend", return_value="bigquery")
def test_init_derived_bigquery_skips_materialization(mock_backend):
    result = init_derived_service("mimic-iv")

    assert result.ok is True
    assert result.data["status"] == "skipped"
    assert result.data["reason"] == "bigquery_derived_tables_available"


@patch("m4.services.init_derived.get_active_backend", return_value="duckdb")
@patch("m4.services.init_derived.get_default_database_path", return_value=None)
def test_init_derived_missing_duckdb_returns_error(mock_db_path, mock_backend):
    result = init_derived_service("mimic-iv")

    assert result.ok is False
    assert result.code == "database_not_found"


@patch("m4.services.init_derived.get_active_backend", return_value="duckdb")
@patch("m4.services.init_derived.get_derived_table_count", return_value=2)
@patch("m4.services.init_derived.materialize_all")
@patch("m4.services.init_derived.get_default_database_path")
def test_init_derived_existing_tables_skip_without_force(
    mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
):
    db_path = tmp_path / "mimic.duckdb"
    db_path.touch()
    mock_db_path.return_value = db_path

    result = init_derived_service("mimic-iv")

    assert result.ok is True
    assert result.data["reason"] == "already_materialized"
    mock_materialize.assert_not_called()


@patch("m4.services.init_derived.get_active_backend", return_value="duckdb")
@patch("m4.services.init_derived.get_derived_table_count", return_value=0)
@patch("m4.services.init_derived.materialize_all", return_value=["sofa"])
@patch("m4.services.init_derived.get_default_database_path")
def test_init_derived_materializes_with_event_reporter(
    mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
):
    db_path = tmp_path / "mimic.duckdb"
    db_path.touch()
    mock_db_path.return_value = db_path
    reporter = Mock()

    result = init_derived_service("mimic-iv", event_reporter=reporter)

    assert result.ok is True
    assert result.data["status"] == "completed"
    mock_materialize.assert_called_once_with(
        "mimic-iv", Path(db_path), event_reporter=reporter
    )
