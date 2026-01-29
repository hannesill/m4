"""Tests for m4.core.derived.materializer module.

Tests cover:
- materialize_all() function with mocked DuckDB
- Pre-flight schema validation
- Error handling for unsupported datasets
- Integration tests (local only, requires real MIMIC-IV data)
"""

from unittest.mock import MagicMock, call, patch

import pytest

from m4.core.derived.builtins import get_execution_order
from m4.core.derived.materializer import _check_required_schemas, materialize_all

# Schema rows returned by mocked DuckDB for the pre-flight check
_MOCK_SCHEMA_ROWS = [("mimiciv_hosp",), ("mimiciv_icu",), ("main",)]


def _make_mock_con():
    """Create a MagicMock DuckDB connection that passes the schema check."""
    mock_con = MagicMock()
    mock_con.execute.return_value.fetchall.return_value = _MOCK_SCHEMA_ROWS
    return mock_con


class TestCheckRequiredSchemas:
    """Tests for the pre-flight schema validation."""

    def test_passes_when_schemas_exist(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [
            ("mimiciv_hosp",),
            ("mimiciv_icu",),
            ("main",),
        ]
        # Should not raise
        _check_required_schemas(mock_con, "mimic-iv")

    def test_raises_when_schemas_missing(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [("main",)]

        with pytest.raises(RuntimeError, match="Required schemas not found"):
            _check_required_schemas(mock_con, "mimic-iv")

    def test_error_message_lists_missing_schemas(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [("main",)]

        with pytest.raises(RuntimeError, match=r"mimiciv_hosp.*mimiciv_icu"):
            _check_required_schemas(mock_con, "mimic-iv")

    def test_error_message_suggests_reinit(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [("main",)]

        with pytest.raises(RuntimeError, match="m4 init mimic-iv --force"):
            _check_required_schemas(mock_con, "mimic-iv")

    def test_skips_check_for_unknown_datasets(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = []
        # No required schemas defined for "other" — should not raise
        _check_required_schemas(mock_con, "other")


class TestMaterializeAll:
    """Tests for materialize_all() with mocked DuckDB."""

    @patch("m4.core.derived.materializer.duckdb")
    def test_creates_schema_and_executes_sql(self, mock_duckdb, tmp_path):
        """Verify the function creates the schema and executes SQL files."""
        mock_con = _make_mock_con()
        mock_duckdb.connect.return_value = mock_con

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        result = materialize_all("mimic-iv", db_path)

        # Should connect to the database
        mock_duckdb.connect.assert_called_once_with(str(db_path))

        # Should drop and recreate the derived schema
        calls = mock_con.execute.call_args_list
        assert call("DROP SCHEMA IF EXISTS mimiciv_derived CASCADE") in calls
        assert call("CREATE SCHEMA mimiciv_derived") in calls

        # Should execute SQL for each file in order
        execution_order = get_execution_order("mimic-iv")
        assert len(result) == len(execution_order)

        # Each SQL file should have been read and executed
        for sql_path in execution_order:
            expected_sql = sql_path.read_text()
            assert call(expected_sql) in calls

        # Should close the connection
        mock_con.close.assert_called_once()

    @patch("m4.core.derived.materializer.duckdb")
    def test_returns_table_names(self, mock_duckdb, tmp_path):
        """Verify return value is list of table names."""
        mock_con = _make_mock_con()
        mock_duckdb.connect.return_value = mock_con

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        result = materialize_all("mimic-iv", db_path)

        assert isinstance(result, list)
        assert all(isinstance(name, str) for name in result)
        assert "sofa" in result
        assert "sepsis3" in result
        assert "age" in result

    @patch("m4.core.derived.materializer.duckdb")
    def test_preserves_execution_order(self, mock_duckdb, tmp_path):
        """Verify tables are created in dependency order."""
        mock_con = _make_mock_con()
        mock_duckdb.connect.return_value = mock_con

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        result = materialize_all("mimic-iv", db_path)

        expected_order = [p.stem for p in get_execution_order("mimic-iv")]
        assert result == expected_order

    def test_unsupported_dataset_raises_value_error(self, tmp_path):
        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        with pytest.raises(ValueError, match="No built-in derived tables"):
            materialize_all("eicu", db_path)

    @patch("m4.core.derived.materializer.duckdb")
    def test_closes_connection_on_error(self, mock_duckdb, tmp_path):
        """Verify connection is closed even if SQL execution fails."""
        mock_con = MagicMock()
        mock_duckdb.connect.return_value = mock_con

        schema_result = MagicMock()
        schema_result.fetchall.return_value = _MOCK_SCHEMA_ROWS
        call_count = 0

        def side_effect(sql):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Schema check query
                return schema_result
            if call_count > 5:  # Fail after some calls
                raise RuntimeError("SQL execution failed")

        mock_con.execute.side_effect = side_effect

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        with pytest.raises(RuntimeError, match="SQL execution failed"):
            materialize_all("mimic-iv", db_path)

        # Connection should still be closed
        mock_con.close.assert_called_once()

    @patch("m4.core.derived.materializer.duckdb")
    def test_fails_with_missing_schemas(self, mock_duckdb, tmp_path):
        """Verify materialization fails early if required schemas are missing."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [("main",)]
        mock_duckdb.connect.return_value = mock_con

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        with pytest.raises(RuntimeError, match="Required schemas not found"):
            materialize_all("mimic-iv", db_path)

        # Should NOT have attempted to drop/create the derived schema
        execute_sqls = [c.args[0] for c in mock_con.execute.call_args_list]
        assert "DROP SCHEMA IF EXISTS mimiciv_derived CASCADE" not in execute_sqls

        # Connection should still be closed
        mock_con.close.assert_called_once()


class TestMaterializeAllIntegration:
    """Integration tests requiring real MIMIC-IV data.

    These tests are skipped in CI — they require a local MIMIC-IV
    database initialized via `m4 init mimic-iv`.
    """

    @pytest.fixture
    def mimic_iv_db_path(self):
        """Get the MIMIC-IV database path, skip if not available."""
        from m4.config import get_default_database_path

        db_path = get_default_database_path("mimic-iv")
        if not db_path or not db_path.exists():
            pytest.skip("MIMIC-IV database not available locally")
        return db_path

    @pytest.mark.requires_mimic_iv
    def test_materialize_all_creates_queryable_tables(self, mimic_iv_db_path):
        """Full integration: materialize all tables and verify they're queryable."""
        import duckdb

        created = materialize_all("mimic-iv", mimic_iv_db_path)
        assert len(created) >= 50

        # Verify key tables are queryable
        con = duckdb.connect(str(mimic_iv_db_path), read_only=True)
        try:
            for table in ["sofa", "sepsis3", "age", "charlson"]:
                result = con.execute(
                    f"SELECT COUNT(*) FROM mimiciv_derived.{table}"
                ).fetchone()
                assert result is not None
                assert result[0] > 0, f"Table {table} is empty"
        finally:
            con.close()
