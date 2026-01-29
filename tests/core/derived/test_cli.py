"""Tests for the init-derived CLI command.

Tests cover:
- Listing available derived tables
- Error handling for unsupported datasets
- BigQuery backend detection
- Database not found handling
- Successful materialization (mocked)
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from m4.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def inject_version(monkeypatch):
    monkeypatch.setattr("m4.__version__", "0.0.1")


class TestInitDerivedList:
    """Tests for m4 init-derived --list."""

    def test_list_mimic_iv_shows_tables(self):
        result = runner.invoke(app, ["init-derived", "mimic-iv", "--list"])
        assert result.exit_code == 0
        assert "sofa" in result.stdout
        assert "sepsis3" in result.stdout
        assert "age" in result.stdout

    def test_list_mimic_iv_shows_count(self):
        result = runner.invoke(app, ["init-derived", "mimic-iv", "--list"])
        assert result.exit_code == 0
        assert "tables" in result.stdout


class TestInitDerivedErrors:
    """Tests for error handling in init-derived."""

    def test_unknown_dataset_fails(self):
        result = runner.invoke(app, ["init-derived", "nonexistent"])
        assert result.exit_code == 1
        assert "not supported" in result.stdout.lower() or "Not Found" in result.stdout

    def test_demo_dataset_blocked(self):
        result = runner.invoke(app, ["init-derived", "mimic-iv-demo"])
        assert result.exit_code == 1
        assert (
            "Not Supported" in result.stdout or "not supported" in result.stdout.lower()
        )

    @patch("m4.cli.get_active_backend", return_value="bigquery")
    def test_bigquery_backend_skips(self, mock_backend):
        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 0
        assert "BigQuery" in result.stdout
        assert "already available" in result.stdout

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_default_database_path", return_value=None)
    def test_missing_database_fails(self, mock_db_path, mock_backend):
        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 1
        assert "Not Found" in result.stdout or "not found" in result.stdout.lower()

    def test_eicu_not_supported(self):
        result = runner.invoke(app, ["init-derived", "eicu"])
        assert result.exit_code == 1


class TestInitDerivedSkipForce:
    """Tests for skip/force behavior when derived tables already exist."""

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=42)
    @patch("m4.cli.materialize_all")
    @patch("m4.cli.get_default_database_path")
    def test_skips_when_derived_exist(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file

        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 0
        assert "already materialized" in result.stdout
        assert "42 tables" in result.stdout
        mock_materialize.assert_not_called()

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=42)
    @patch("m4.cli.materialize_all")
    @patch("m4.cli.get_default_database_path")
    def test_force_rematerializes(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file
        mock_materialize.return_value = ["sofa", "sepsis3", "age"]

        result = runner.invoke(app, ["init-derived", "mimic-iv", "--force"])
        assert result.exit_code == 0
        mock_materialize.assert_called_once_with("mimic-iv", db_file)

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=0)
    @patch("m4.cli.materialize_all")
    @patch("m4.cli.get_default_database_path")
    def test_no_skip_when_no_derived(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file
        mock_materialize.return_value = ["sofa", "sepsis3", "age"]

        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 0
        mock_materialize.assert_called_once_with("mimic-iv", db_file)


class TestInitDerivedMaterialize:
    """Tests for successful materialization (mocked)."""

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=0)
    @patch("m4.cli.materialize_all")
    @patch("m4.cli.get_default_database_path")
    def test_successful_materialization(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file
        mock_materialize.return_value = ["sofa", "sepsis3", "age"]

        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 0
        mock_materialize.assert_called_once_with("mimic-iv", db_file)

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=0)
    @patch(
        "m4.cli.materialize_all", side_effect=ValueError("No built-in derived tables")
    )
    @patch("m4.cli.get_default_database_path")
    def test_value_error_handled(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file

        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 1

    @patch("m4.cli.get_active_backend", return_value="duckdb")
    @patch("m4.cli.get_derived_table_count", return_value=0)
    @patch("m4.cli.materialize_all", side_effect=RuntimeError("SQL failed"))
    @patch("m4.cli.get_default_database_path")
    def test_runtime_error_handled(
        self, mock_db_path, mock_materialize, mock_count, mock_backend, tmp_path
    ):
        db_file = tmp_path / "mimic_iv.duckdb"
        db_file.touch()
        mock_db_path.return_value = db_file

        result = runner.invoke(app, ["init-derived", "mimic-iv"])
        assert result.exit_code == 1
        assert "failed" in result.stdout.lower()
