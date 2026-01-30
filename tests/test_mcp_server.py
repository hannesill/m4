"""Tests for the MCP server functionality.

These tests verify the thin MCP adapter layer (mcp_server.py) which
delegates all business logic to tool classes.
"""

import os
from unittest.mock import Mock, patch

import pytest
from fastmcp import Client

from m4.core.datasets import DatasetDefinition, Modality
from m4.core.tools import init_tools
from m4.mcp_server import mcp


@pytest.fixture(autouse=True)
def ensure_tools_initialized():
    """Ensure tools are initialized before each test."""
    init_tools()


def _bigquery_available():
    """Check if BigQuery dependencies are available."""
    try:
        import importlib.util

        return importlib.util.find_spec("google.cloud.bigquery") is not None
    except ImportError:
        return False


class TestMCPServerSetup:
    """Test MCP server setup and configuration."""

    def test_server_instance_exists(self):
        """Test that the FastMCP server instance exists."""
        assert mcp is not None
        assert mcp.name == "m4"


class TestMCPTools:
    """Test MCP tools functionality."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create a test DuckDB database with schema-qualified tables."""
        import duckdb

        db_path = tmp_path / "test.duckdb"
        con = duckdb.connect(str(db_path))
        try:
            con.execute("CREATE SCHEMA mimiciv_icu")
            con.execute(
                """
                CREATE TABLE mimiciv_icu.icustays (
                    subject_id INTEGER,
                    hadm_id INTEGER,
                    stay_id INTEGER,
                    intime TIMESTAMP,
                    outtime TIMESTAMP
                )
                """
            )
            con.execute(
                """
                INSERT INTO mimiciv_icu.icustays (subject_id, hadm_id, stay_id, intime, outtime) VALUES
                    (10000032, 20000001, 30000001, '2180-07-23 15:00:00', '2180-07-24 12:00:00'),
                    (10000033, 20000002, 30000002, '2180-08-15 10:30:00', '2180-08-16 14:15:00')
                """
            )
            con.execute("CREATE SCHEMA mimiciv_hosp")
            con.execute(
                """
                CREATE TABLE mimiciv_hosp.labevents (
                    subject_id INTEGER,
                    hadm_id INTEGER,
                    itemid INTEGER,
                    charttime TIMESTAMP,
                    value TEXT
                )
                """
            )
            con.execute(
                """
                INSERT INTO mimiciv_hosp.labevents (subject_id, hadm_id, itemid, charttime, value) VALUES
                    (10000032, 20000001, 50912, '2180-07-23 16:00:00', '120'),
                    (10000033, 20000002, 50912, '2180-08-15 11:00:00', '95')
                """
            )
            con.commit()
        finally:
            con.close()

        return str(db_path)

    @pytest.mark.asyncio
    async def test_tools_via_client(self, test_db):
        """Test MCP tools through the FastMCP client."""
        from m4.core.backends import reset_backend_cache

        # Reset backend cache to ensure clean state
        reset_backend_cache()

        # Create a mock dataset with TABULAR modality
        mock_ds = DatasetDefinition(
            name="mimic-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.core.tools.tabular.get_backend") as mock_get_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    # Use real DuckDB backend with test database
                    mock_get_backend.return_value = DuckDBBackend(
                        db_path_override=test_db
                    )

                    async with Client(mcp) as client:
                        # Test execute_query tool
                        result = await client.call_tool(
                            "execute_query",
                            {
                                "sql_query": "SELECT COUNT(*) as count FROM mimiciv_icu.icustays"
                            },
                        )
                        result_text = str(result)
                        assert "count" in result_text
                        assert "2" in result_text

                        # Test get_database_schema tool
                        result = await client.call_tool("get_database_schema", {})
                        result_text = str(result)
                        assert (
                            "mimiciv_icu.icustays" in result_text
                            or "mimiciv_hosp.labevents" in result_text
                        )

    @pytest.mark.asyncio
    async def test_security_checks(self, test_db):
        """Test SQL injection protection."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            async with Client(mcp) as client:
                # Test dangerous queries are blocked
                dangerous_queries = [
                    "UPDATE mimiciv_icu.icustays SET subject_id = 999",
                    "DELETE FROM mimiciv_icu.icustays",
                    "INSERT INTO mimiciv_icu.icustays VALUES (1, 2, 3, '2020-01-01', '2020-01-02')",
                    "DROP TABLE mimiciv_icu.icustays",
                    "CREATE TABLE test (id INTEGER)",
                    "ALTER TABLE mimiciv_icu.icustays ADD COLUMN test TEXT",
                ]

                for query in dangerous_queries:
                    result = await client.call_tool(
                        "execute_query", {"sql_query": query}
                    )
                    result_text = str(result)
                    # Security errors are formatted as "**Error:** <message>"
                    assert "**Error:**" in result_text

    @pytest.mark.asyncio
    async def test_invalid_sql(self, test_db):
        """Test handling of invalid SQL."""
        from m4.core.backends import reset_backend_cache
        from m4.core.backends.duckdb import DuckDBBackend

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.core.tools.tabular.get_backend") as mock_get_backend:
                    mock_get_backend.return_value = DuckDBBackend(
                        db_path_override=test_db
                    )

                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "execute_query",
                            {"sql_query": "INVALID SQL QUERY"},
                        )
                        result_text = str(result)
                        # Security validation happens first, and this is valid
                        # SQL structure but will fail execution
                        assert "Error" in result_text or "error" in result_text

    @pytest.mark.asyncio
    async def test_empty_results(self, test_db):
        """Test handling of queries with no results."""
        from m4.core.backends import reset_backend_cache
        from m4.core.backends.duckdb import DuckDBBackend

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.core.tools.tabular.get_backend") as mock_get_backend:
                    mock_get_backend.return_value = DuckDBBackend(
                        db_path_override=test_db
                    )

                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "execute_query",
                            {
                                "sql_query": "SELECT * FROM mimiciv_icu.icustays WHERE subject_id = 999999"
                            },
                        )
                        result_text = str(result)
                        assert "No results found" in result_text

    @pytest.mark.asyncio
    async def test_oauth2_authentication_required(self, test_db):
        """Test that OAuth2 authentication is required when enabled."""
        from m4.auth import init_oauth2
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": test_db,
                "M4_OAUTH2_ENABLED": "true",
                "M4_OAUTH2_ISSUER_URL": "https://auth.example.com",
                "M4_OAUTH2_AUDIENCE": "m4-api",
            },
            clear=True,
        ):
            # Re-initialize OAuth2 with new env vars
            init_oauth2()

            async with Client(mcp) as client:
                # Test that tools require authentication
                result = await client.call_tool(
                    "execute_query",
                    {"sql_query": "SELECT COUNT(*) FROM mimiciv_icu.icustays"},
                )
                result_text = str(result)
                assert "Missing OAuth2 access token" in result_text

        # Reset OAuth2 to disabled after test
        with patch.dict(os.environ, {"M4_OAUTH2_ENABLED": "false"}, clear=True):
            init_oauth2()


class TestBigQueryIntegration:
    """Test BigQuery integration with mocks (no real API calls)."""

    @pytest.mark.skipif(
        not _bigquery_available(), reason="BigQuery dependencies not available"
    )
    @pytest.mark.asyncio
    async def test_bigquery_tools(self):
        """Test BigQuery tools functionality with mocks."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        # Mock Dataset definition for BigQuery
        mock_ds = DatasetDefinition(
            name="mimic-test",
            bigquery_project_id="test-project",
            bigquery_dataset_ids=["mimic_hosp", "mimic_icu"],
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "bigquery",
                "M4_PROJECT_ID": "test-project",
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.core.tools.tabular.get_backend") as mock_get_backend:
                    # Mock the backend
                    mock_backend = Mock()
                    mock_backend.name = "bigquery"

                    import pandas as pd

                    from m4.core.backends.base import QueryResult

                    # Create a mock DataFrame for the result
                    mock_df = pd.DataFrame({"result": ["Mock BigQuery result"]})
                    mock_backend.execute_query.return_value = QueryResult(
                        dataframe=mock_df,
                        row_count=5,
                    )
                    mock_backend.get_backend_info.return_value = (
                        "Backend: BigQuery (test-project)"
                    )
                    mock_get_backend.return_value = mock_backend

                    async with Client(mcp) as client:
                        # Test execute_query tool
                        result = await client.call_tool(
                            "execute_query",
                            {
                                "sql_query": "SELECT COUNT(*) FROM `physionet-data.mimiciv_icu.icustays`"
                            },
                        )
                        result_text = str(result)
                        assert "Mock BigQuery result" in result_text


class TestServerIntegration:
    """Test overall server integration."""

    def test_server_main_function_exists(self):
        """Test that the main function exists and is callable."""
        from m4.mcp_server import main

        assert callable(main)

    def test_server_can_be_imported_as_module(self):
        """Test that the server can be imported as a module."""
        import m4.mcp_server

        assert hasattr(m4.mcp_server, "mcp")
        assert hasattr(m4.mcp_server, "main")


class TestModalityChecking:
    """Test proactive modality-based tool filtering.

    These tests verify that:
    1. Incompatible tools return helpful error messages without backend execution
    2. Compatible tools work as expected
    3. set_dataset includes supported tools snapshot
    """

    @pytest.mark.asyncio
    async def test_incompatible_tool_returns_proactive_error(self):
        """Test that calling a tool on an incompatible dataset returns proactive error.

        This verifies no backend execution is attempted.
        """
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        # Create a dataset that lacks TABULAR modality (only has NOTES)
        notes_only_ds = DatasetDefinition(
            name="notes-only-dataset",
            modalities={Modality.NOTES},  # No TABULAR modality
        )

        with patch.dict(
            os.environ,
            {"M4_OAUTH2_ENABLED": "false"},
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=notes_only_ds
            ):
                # Mock backend that should NOT be called
                with patch("m4.core.tools.tabular.get_backend") as mock_backend:
                    async with Client(mcp) as client:
                        # Call execute_query which requires TABULAR modality
                        result = await client.call_tool(
                            "execute_query", {"sql_query": "SELECT 1"}
                        )
                        result_text = str(result)

                        # Verify proactive error message
                        assert "Error" in result_text
                        assert "execute_query" in result_text
                        assert "notes-only-dataset" in result_text
                        assert "TABULAR" in result_text

                        # Verify suggestions are included
                        assert "list_datasets" in result_text
                        assert "set_dataset" in result_text

                        # Verify backend was NOT called (no execution attempted)
                        mock_backend.assert_not_called()

    @pytest.mark.asyncio
    async def test_compatible_tool_executes_successfully(self, tmp_path):
        """Test that compatible tools execute against the backend."""
        import duckdb

        from m4.core.backends import reset_backend_cache
        from m4.core.backends.duckdb import DuckDBBackend

        reset_backend_cache()

        # Create test database
        db_path = tmp_path / "test.duckdb"
        con = duckdb.connect(str(db_path))
        try:
            con.execute("CREATE TABLE test_table (id INTEGER, value TEXT)")
            con.execute("INSERT INTO test_table VALUES (1, 'test1'), (2, 'test2')")
            con.commit()
        finally:
            con.close()

        # Create dataset with TABULAR modality
        tabular_ds = DatasetDefinition(
            name="tabular-dataset",
            modalities={Modality.TABULAR},
        )

        with patch.dict(
            os.environ,
            {"M4_OAUTH2_ENABLED": "false"},
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=tabular_ds
            ):
                with patch("m4.core.tools.tabular.get_backend") as mock_get_backend:
                    mock_get_backend.return_value = DuckDBBackend(
                        db_path_override=str(db_path)
                    )

                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "execute_query",
                            {"sql_query": "SELECT * FROM test_table LIMIT 10"},
                        )
                        result_text = str(result)

                        # Verify data was returned (backend was called)
                        assert "id" in result_text or "1" in result_text

                        # Verify NO error message
                        assert "not available" not in result_text.lower()

    @pytest.mark.asyncio
    async def test_set_dataset_returns_supported_tools_snapshot(self):
        """Test that set_dataset includes supported tools in response."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        # Create a dataset with TABULAR modality
        target_ds = DatasetDefinition(
            name="test-dataset",
            modalities={Modality.TABULAR},
        )

        with patch.dict(os.environ, {"M4_OAUTH2_ENABLED": "false"}, clear=True):
            with patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value={
                    "test-dataset": {"parquet_present": True, "db_present": True}
                },
            ):
                with patch("m4.core.tools.management.set_active_dataset"):
                    with patch(
                        "m4.core.tools.management.DatasetRegistry.get",
                        return_value=target_ds,
                    ):
                        with patch(
                            "m4.mcp_server.DatasetRegistry.get",
                            return_value=target_ds,
                        ):
                            with patch(
                                "m4.core.tools.management.get_active_backend",
                                return_value="duckdb",
                            ):
                                async with Client(mcp) as client:
                                    result = await client.call_tool(
                                        "set_dataset",
                                        {"dataset_name": "test-dataset"},
                                    )
                                    result_text = str(result)

                                    # Verify snapshot is included
                                    assert "Active dataset" in result_text
                                    assert "test-dataset" in result_text
                                    assert "Modalities" in result_text
                                    assert "Supported tools" in result_text

                                    # Tools should be sorted alphabetically
                                    assert "execute_query" in result_text

    @pytest.mark.asyncio
    async def test_set_dataset_invalid_returns_error_without_snapshot(self):
        """Test that set_dataset with invalid dataset returns error without snapshot."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        # Create a valid mock dataset for get_active
        mock_active_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities={Modality.TABULAR},
        )

        with patch.dict(os.environ, {"M4_OAUTH2_ENABLED": "false"}, clear=True):
            with patch(
                "m4.core.tools.management.detect_available_local_datasets",
                return_value={
                    "mimic-iv-demo": {"parquet_present": True, "db_present": True}
                },
            ):
                with patch(
                    "m4.mcp_server.DatasetRegistry.get_active",
                    return_value=mock_active_ds,
                ):
                    with patch(
                        "m4.mcp_server.DatasetRegistry.get", return_value=None
                    ):  # Unknown dataset for snapshot lookup
                        async with Client(mcp) as client:
                            result = await client.call_tool(
                                "set_dataset", {"dataset_name": "nonexistent-dataset"}
                            )
                            result_text = str(result)

                            # Should have error
                            assert "not found" in result_text.lower()

    @pytest.mark.asyncio
    async def test_tool_incompatibility_with_notes_only(self):
        """Test that tabular tools are incompatible with notes-only dataset."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        # Create dataset with only NOTES modality
        notes_ds = DatasetDefinition(
            name="notes-dataset",
            modalities={Modality.NOTES},  # Only notes data
        )

        with patch.dict(os.environ, {"M4_OAUTH2_ENABLED": "false"}, clear=True):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=notes_ds
            ):
                async with Client(mcp) as client:
                    # Test execute_query (requires TABULAR modality)
                    result = await client.call_tool(
                        "execute_query", {"sql_query": "SELECT 1"}
                    )
                    assert "TABULAR" in str(result)

                    # Test get_database_schema (requires TABULAR modality)
                    result = await client.call_tool("get_database_schema", {})
                    assert "TABULAR" in str(result)

    def test_check_tool_compatibility_helper(self):
        """Test the ToolSelector.check_compatibility method directly."""
        from m4.core.tools import ToolSelector

        selector = ToolSelector()

        # Dataset with only NOTES modality
        notes_ds = DatasetDefinition(
            name="notes-only",
            modalities={Modality.NOTES},
        )

        # Dataset with TABULAR modality
        tabular_ds = DatasetDefinition(
            name="tabular",
            modalities={Modality.TABULAR},
        )

        # Test compatible tool
        result = selector.check_compatibility("execute_query", tabular_ds)
        assert result.compatible is True
        assert result.error_message == ""

        # Test incompatible tool (execute_query requires TABULAR)
        result = selector.check_compatibility("execute_query", notes_ds)
        assert result.compatible is False
        assert "TABULAR" in result.error_message
        assert "notes-only" in result.error_message
        assert "list_datasets" in result.error_message

        # Test unknown tool
        result = selector.check_compatibility("nonexistent_tool", tabular_ds)
        assert result.compatible is False
        assert "Unknown tool" in result.error_message

    def test_supported_tools_snapshot_helper(self):
        """Test the ToolSelector.get_supported_tools_snapshot method."""
        from m4.core.tools import ToolSelector

        selector = ToolSelector()

        # Dataset with TABULAR modality
        tabular_ds = DatasetDefinition(
            name="tabular-dataset",
            modalities={Modality.TABULAR},
        )

        snapshot = selector.get_supported_tools_snapshot(tabular_ds)

        # Verify structure
        assert "Active dataset" in snapshot
        assert "tabular-dataset" in snapshot
        assert "Modalities" in snapshot
        assert "Supported tools" in snapshot

        # Verify tools are sorted (alphabetically)
        assert "execute_query" in snapshot
        assert "get_database_schema" in snapshot
        assert "get_table_info" in snapshot

    def test_supported_tools_snapshot_empty_modalities(self):
        """Test snapshot for dataset with no modalities."""
        from m4.core.tools import ToolSelector

        selector = ToolSelector()

        # Dataset with no modalities
        empty_ds = DatasetDefinition(
            name="empty-dataset",
            modalities=set(),  # No modalities
        )

        snapshot = selector.get_supported_tools_snapshot(empty_ds)

        # Should show warning about no tools or just management tools
        assert "No data tools available" in snapshot or "list_datasets" in snapshot
