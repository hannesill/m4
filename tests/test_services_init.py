from unittest.mock import patch

from m4.services.init import initialize_dataset_service
from m4.services.results import CommandError, CommandResult


def _step_by_name(result: CommandResult, name: str) -> dict:
    return next(step for step in result.data["steps"] if step["name"] == name)


def test_init_service_unsupported_dataset_error():
    result = initialize_dataset_service("not-a-dataset")

    assert isinstance(result, CommandError)
    assert result.code == "dataset_not_found"


@patch("m4.services.init.get_dataset_parquet_root", return_value=None)
def test_init_service_missing_parquet_directory_resolution_error(mock_parquet_root):
    result = initialize_dataset_service("mimic-iv-demo")

    assert isinstance(result, CommandError)
    assert result.code == "invalid_option"
    assert "Could not determine dataset directories" in result.message


@patch("m4.services.init.has_derived_support", return_value=False)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_parquet_already_present_path(
    mock_parquet_root,
    mock_db_path,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv-demo"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv-demo")

    assert isinstance(result, CommandResult)
    assert _step_by_name(result, "raw_files")["status"] == "skipped"
    assert _step_by_name(result, "parquet")["status"] == "skipped"
    assert _step_by_name(result, "database")["status"] == "completed"
    mock_init.assert_called_once_with(
        dataset_name="mimic-iv-demo", db_target_path=db_path
    )
    mock_set_active.assert_called_once_with("mimic-iv-demo")


@patch("m4.services.init.has_derived_support", return_value=False)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.convert_csv_to_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_raw_to_parquet_conversion_path(
    mock_parquet_root,
    mock_db_path,
    mock_convert,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv-demo"
    pq_root.mkdir(parents=True)
    raw_root = tmp_path / "raw_files" / "mimic-iv-demo" / "hosp"
    raw_root.mkdir(parents=True)
    (raw_root / "admissions.csv.gz").touch()
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv-demo")

    assert isinstance(result, CommandResult)
    assert _step_by_name(result, "raw_files")["status"] == "completed"
    assert _step_by_name(result, "parquet")["status"] == "completed"
    mock_convert.assert_called_once()


@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_credentialed_dataset_returns_blocked_state(
    mock_parquet_root, mock_db_path, tmp_path
):
    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv")

    assert isinstance(result, CommandResult)
    assert _step_by_name(result, "raw_files")["status"] == "blocked"
    assert _step_by_name(result, "database")["status"] == "skipped"


@patch("m4.services.init.has_derived_support", return_value=False)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_force_deletes_existing_database(
    mock_parquet_root,
    mock_db_path,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv-demo"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()
    db_path = tmp_path / "mimic.duckdb"
    db_path.write_text("old")
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv-demo", force=True)

    assert isinstance(result, CommandResult)
    assert not db_path.exists()
    mock_init.assert_called_once()


@patch("m4.services.init.get_active_backend", return_value="duckdb")
@patch("m4.services.init.get_derived_table_count", return_value=0)
@patch("m4.services.init.has_derived_support", return_value=True)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_derived_skipped_by_default(
    mock_parquet_root,
    mock_db_path,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    mock_derived_count,
    mock_backend,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv")

    assert isinstance(result, CommandResult)
    assert _step_by_name(result, "derived")["status"] == "skipped"


@patch("m4.services.init.get_active_backend", return_value="duckdb")
@patch("m4.services.init.materialize_all", return_value=["sofa", "sepsis3"])
@patch("m4.services.init.get_derived_table_count", return_value=42)
@patch("m4.services.init.has_derived_support", return_value=True)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_force_materializes_existing_derived_tables(
    mock_parquet_root,
    mock_db_path,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    mock_derived_count,
    mock_materialize,
    mock_backend,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv", force=True)

    assert isinstance(result, CommandResult)
    assert _step_by_name(result, "derived")["status"] == "completed"
    mock_materialize.assert_called_once_with("mimic-iv", db_path)


@patch("m4.services.init.get_active_backend", return_value="duckdb")
@patch("m4.services.init.materialize_all", side_effect=RuntimeError("SQL failed"))
@patch("m4.services.init.get_derived_table_count", return_value=42)
@patch("m4.services.init.has_derived_support", return_value=True)
@patch("m4.services.init.set_active_dataset")
@patch("m4.services.init.verify_table_rowcount", return_value=100)
@patch("m4.services.init.init_duckdb_from_parquet", return_value=True)
@patch("m4.services.init.get_default_database_path")
@patch("m4.services.init.get_dataset_parquet_root")
def test_init_service_derived_failure_is_nonfatal_step(
    mock_parquet_root,
    mock_db_path,
    mock_init,
    mock_verify,
    mock_set_active,
    mock_derived_support,
    mock_derived_count,
    mock_materialize,
    mock_backend,
    tmp_path,
):
    pq_root = tmp_path / "parquet" / "mimic-iv"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()
    db_path = tmp_path / "mimic.duckdb"
    mock_parquet_root.return_value = pq_root
    mock_db_path.return_value = db_path

    result = initialize_dataset_service("mimic-iv", force=True)

    assert isinstance(result, CommandResult)
    assert result.ok is True
    assert _step_by_name(result, "derived")["status"] == "failed"
