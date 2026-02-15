"""End-to-end integration tests.

These tests exercise the full stack (Tool class -> Backend -> DuckDB -> Result)
with minimal mocking. They catch issues where individual layers work but the
combination fails.
"""

from unittest.mock import patch

import duckdb
import pandas as pd
import pytest

from m4.core.backends.duckdb import DuckDBBackend
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import QueryError, SecurityError
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    ExecuteQueryTool,
    GetDatabaseSchemaInput,
    GetDatabaseSchemaTool,
    GetTableInfoInput,
    GetTableInfoTool,
)


@pytest.fixture
def integration_env(tmp_path):
    """Full stack test environment with real DuckDB.

    Creates a temp DuckDB database with schema-qualified tables
    matching the MIMIC-IV demo structure.
    """
    db_path = tmp_path / "integration_test.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        # Create mimiciv_hosp schema with patients table
        con.execute("CREATE SCHEMA mimiciv_hosp")
        con.execute("""
            CREATE TABLE mimiciv_hosp.patients (
                subject_id INTEGER PRIMARY KEY,
                gender VARCHAR,
                anchor_age INTEGER,
                anchor_year INTEGER,
                dod TIMESTAMP
            )
        """)
        con.execute("""
            INSERT INTO mimiciv_hosp.patients VALUES
                (10000032, 'M', 52, 2180, NULL),
                (10000033, 'F', 67, 2175, '2175-08-09'),
                (10000034, 'M', 45, 2160, NULL)
        """)

        # Create mimiciv_icu schema with icustays table
        con.execute("CREATE SCHEMA mimiciv_icu")
        con.execute("""
            CREATE TABLE mimiciv_icu.icustays (
                subject_id INTEGER,
                hadm_id INTEGER,
                stay_id INTEGER,
                intime TIMESTAMP,
                outtime TIMESTAMP
            )
        """)
        con.execute("""
            INSERT INTO mimiciv_icu.icustays VALUES
                (10000032, 20000001, 30000001, '2180-07-23 15:00:00', '2180-07-24 12:00:00'),
                (10000033, 20000002, 30000002, '2180-08-15 10:30:00', '2180-08-16 14:15:00')
        """)
        con.commit()
    finally:
        con.close()

    dataset = DatasetDefinition(
        name="integration-test",
        modalities=frozenset({Modality.TABULAR}),
        schema_mapping={"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"},
    )

    backend = DuckDBBackend(db_path_override=str(db_path))

    return dataset, backend, str(db_path)


class TestEndToEnd:
    """End-to-end integration tests exercising Tool -> Backend -> DuckDB."""

    def test_execute_query_full_stack(self, integration_env):
        """ExecuteQueryTool returns correct DataFrame through the full stack."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(
                dataset,
                ExecuteQueryInput(
                    sql_query="SELECT COUNT(*) as cnt FROM mimiciv_hosp.patients"
                ),
            )

        assert isinstance(result, pd.DataFrame)
        assert "cnt" in result.columns
        assert result["cnt"].iloc[0] == 3

    def test_get_database_schema_full_stack(self, integration_env):
        """GetDatabaseSchemaTool lists schema-qualified tables."""
        dataset, backend, db_path = integration_env

        tool = GetDatabaseSchemaTool()
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(dataset, GetDatabaseSchemaInput())

        assert isinstance(result, dict)
        assert "tables" in result
        tables = result["tables"]
        assert "mimiciv_hosp.patients" in tables
        assert "mimiciv_icu.icustays" in tables

    def test_get_table_info_full_stack(self, integration_env):
        """GetTableInfoTool returns schema and sample data for a real table."""
        dataset, backend, db_path = integration_env

        tool = GetTableInfoTool()
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(
                dataset,
                GetTableInfoInput(table_name="mimiciv_hosp.patients"),
            )

        assert isinstance(result, dict)

        # Columns should be a normalized DataFrame
        columns = result["columns"]
        assert isinstance(columns, pd.DataFrame)
        column_names = columns["column_name"].tolist()
        assert "subject_id" in column_names
        assert "gender" in column_names

        # DDL should be present
        assert "CREATE TABLE" in result["ddl"]

        # Sample should be a DataFrame with actual patient data
        sample = result["sample"]
        assert isinstance(sample, pd.DataFrame)
        assert len(sample) > 0

    def test_execute_query_error_full_stack(self, integration_env):
        """ExecuteQueryTool raises QueryError for a nonexistent table."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            with pytest.raises(QueryError) as exc_info:
                tool.invoke(
                    dataset,
                    ExecuteQueryInput(sql_query="SELECT * FROM nonexistent_table"),
                )

        # The sanitized error message should contain user-friendly guidance
        error_msg = str(exc_info.value)
        assert "table" in error_msg.lower() or "not found" in error_msg.lower()

    def test_invalid_sql_full_stack(self, integration_env):
        """ExecuteQueryTool raises SecurityError for dangerous SQL."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            with pytest.raises(SecurityError):
                tool.invoke(
                    dataset,
                    ExecuteQueryInput(sql_query="DROP TABLE patients"),
                )

    def test_execute_query_with_join(self, integration_env):
        """ExecuteQueryTool handles JOIN queries across schemas."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        sql = """
            SELECT p.subject_id, p.gender, i.stay_id, i.intime
            FROM mimiciv_hosp.patients p
            JOIN mimiciv_icu.icustays i ON p.subject_id = i.subject_id
            ORDER BY p.subject_id
        """
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(dataset, ExecuteQueryInput(sql_query=sql))

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2  # Two patients have ICU stays
        assert "subject_id" in result.columns
        assert "gender" in result.columns
        assert "stay_id" in result.columns
        assert "intime" in result.columns

    def test_execute_query_with_aggregation(self, integration_env):
        """ExecuteQueryTool handles GROUP BY aggregation queries."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        sql = (
            "SELECT gender, COUNT(*) as cnt FROM mimiciv_hosp.patients GROUP BY gender"
        )
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(dataset, ExecuteQueryInput(sql_query=sql))

        assert isinstance(result, pd.DataFrame)
        assert "gender" in result.columns
        assert "cnt" in result.columns
        # 2 males, 1 female
        gender_counts = dict(zip(result["gender"], result["cnt"]))
        assert gender_counts["M"] == 2
        assert gender_counts["F"] == 1

    def test_execute_query_empty_result(self, integration_env):
        """ExecuteQueryTool returns empty DataFrame for no-match queries."""
        dataset, backend, db_path = integration_env

        tool = ExecuteQueryTool()
        sql = "SELECT * FROM mimiciv_hosp.patients WHERE subject_id = -1"
        with patch("m4.core.tools.tabular.get_backend", return_value=backend):
            result = tool.invoke(dataset, ExecuteQueryInput(sql_query=sql))

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
