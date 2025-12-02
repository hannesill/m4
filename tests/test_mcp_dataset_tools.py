from unittest.mock import Mock, patch

import pytest
from fastmcp import Client

from m4.mcp_server import mcp


class TestMCPDatasetTools:
    """Test MCP dataset management tools."""

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
            "mimic-iv-full": {
                "parquet_present": False,
                "db_present": False,
                "parquet_root": "/tmp/full_parquet",
                "db_path": "",
            },
        }

        # We need to mock DatasetRegistry.get as well since list_datasets calls it
        with patch(
            "m4.mcp_server.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch(
                "m4.mcp_server.get_active_dataset", return_value="mimic-iv-demo"
            ):
                with patch("m4.mcp_server.DatasetRegistry.get") as mock_get:
                    # Mock ds_def
                    mock_ds = Mock()
                    mock_ds.bigquery_dataset_ids = []
                    mock_get.return_value = mock_ds

                    async with Client(mcp) as client:
                        result = await client.call_tool("list_datasets", {})
                        result_text = str(result)

                        assert "Active dataset: mimic-iv-demo" in result_text
                        assert "=== MIMIC-IV-DEMO (Active) ===" in result_text
                        assert "=== MIMIC-IV-FULL ===" in result_text
                        # Check icons (logic is in the tool, verify output)
                        # The test setup has demo as present, full as absent
                        # But note: we can't easily assert exactly which check mark belongs to which unless we parse better
                        # But we can check that both exist in output
                        assert "Local Database: ✅" in result_text
                        assert "Local Database: ❌" in result_text

    @pytest.mark.asyncio
    async def test_set_dataset_success(self):
        """Test set_dataset tool with valid dataset."""
        mock_availability = {
            "mimic-iv-demo": {"parquet_present": True, "db_present": True}
        }

        with patch(
            "m4.mcp_server.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.mcp_server.set_active_dataset") as mock_set:
                with patch("m4.mcp_server.DatasetRegistry.get"):
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "set_dataset", {"dataset_name": "mimic-iv-demo"}
                        )
                        result_text = str(result)

                        assert (
                            "Active dataset switched to 'mimic-iv-demo'" in result_text
                        )
                        mock_set.assert_called_once_with("mimic-iv-demo")

    @pytest.mark.asyncio
    async def test_set_dataset_invalid(self):
        """Test set_dataset tool with invalid dataset."""
        mock_availability = {"mimic-iv-demo": {}}

        with patch(
            "m4.mcp_server.detect_available_local_datasets",
            return_value=mock_availability,
        ):
            with patch("m4.mcp_server.set_active_dataset") as mock_set:
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "set_dataset", {"dataset_name": "invalid-ds"}
                    )
                    result_text = str(result)

                    assert "Error: Dataset 'invalid-ds' not found" in result_text
                    mock_set.assert_not_called()
