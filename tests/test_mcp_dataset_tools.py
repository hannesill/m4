"""Tests for dataset management MCP tools."""

from unittest.mock import Mock, patch

import pytest
from fastmcp import Client

from m4.core.tools import init_tools
from m4.mcp_server import mcp


class TestMCPDatasetTools:
    """Test MCP dataset management tools."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure tools are initialized before each test."""
        init_tools()

    @pytest.mark.asyncio
    async def test_list_datasets(self):
        """Test list_datasets tool."""
        mock_availability = {
            "mimic-iv-demo": {
                "parquet_present": True,
                "db_present": True,
                "parquet_root": "/tmp/demo_parquet",
                "db_path": "/tmp/demo.duckdb",
            },
            "mimic-iv": {
                "parquet_present": False,
                "db_present": False,
                "parquet_root": "/tmp/full_parquet",
                "db_path": "",
            },
        }

        with patch(
            "m4.core.tools.management.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.core.tools.management.DatasetRegistry.get") as mock_get:
                mock_ds = Mock()
                mock_ds.bigquery_dataset_ids = []
                mock_ds.modalities = frozenset()
                mock_get.return_value = mock_ds

                async with Client(mcp) as client:
                    result = await client.call_tool("list_datasets", {})
                    result_text = str(result)

                assert "Active dataset" not in result_text
                assert "=== MIMIC-IV-DEMO ===" in result_text
                assert "=== MIMIC-IV ===" in result_text
                assert "Local Database: ✅" in result_text
                assert "Local Database: ❌" in result_text

    @pytest.mark.asyncio
    async def test_set_dataset_returns_migration_error(self):
        """Test set_dataset tool returns migration guidance."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "set_dataset", {"dataset_name": "mimic-iv-demo"}
            )
            result_text = str(result)

            assert "**Error:**" in result_text
            assert "set_dataset is no longer supported" in result_text
            assert "explicit dataset" in result_text

    @pytest.mark.asyncio
    async def test_set_dataset_invalid_returns_migration_error(self):
        """Invalid names get the same migration guidance because no switch occurs."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "set_dataset", {"dataset_name": "invalid-ds"}
            )
            result_text = str(result)

            assert "**Error:**" in result_text
            assert "set_dataset is no longer supported" in result_text
