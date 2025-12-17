"""M4 MCP Server - Thin MCP Protocol Adapter.

This module provides the FastMCP server that exposes M4 tools via MCP protocol.
All business logic is delegated to tool classes in m4.core.tools.

Architecture:
    mcp_server.py (this file) - MCP protocol adapter
        ↓ delegates to
    core/tools/*.py - Tool implementations
        ↓ uses
    core/backends/*.py - Database backends

Tool Surface:
    The MCP tool surface is stable - all tools remain registered regardless of
    the active dataset. Compatibility is enforced per-call via proactive
    capability checking before tool invocation.
"""

from fastmcp import FastMCP

from m4.auth import init_oauth2, require_oauth2
from m4.core.datasets import DatasetRegistry
from m4.core.tools import ToolRegistry, ToolSelector, init_tools
from m4.core.tools.management import ListDatasetsInput, SetDatasetInput
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    GetDatabaseSchemaInput,
    GetTableInfoInput,
)

# Create FastMCP server instance
mcp = FastMCP("m4")

# Initialize systems
init_oauth2()
init_tools()

# Tool selector for capability-based filtering
_tool_selector = ToolSelector()

# MCP-exposed tool names (for filtering in set_dataset snapshot)
_MCP_TOOL_NAMES = frozenset(
    {
        "list_datasets",
        "set_dataset",
        "get_database_schema",
        "get_table_info",
        "execute_query",
    }
)


# ==========================================
# MCP TOOLS - Thin adapters to tool classes
# ==========================================


@mcp.tool()
def list_datasets() -> str:
    """📋 List all available datasets and their status.

    Returns:
        A formatted string listing available datasets, indicating which one is active,
        and showing availability of local database and BigQuery support.
    """
    tool = ToolRegistry.get("list_datasets")
    dataset = DatasetRegistry.get_active()
    return tool.invoke(dataset, ListDatasetsInput()).result


@mcp.tool()
def set_dataset(dataset_name: str) -> str:
    """🔄 Switch the active dataset.

    Args:
        dataset_name: The name of the dataset to switch to (e.g., 'mimic-iv-demo').

    Returns:
        Confirmation message with supported tools snapshot, or error if not found.
    """
    # Check if target dataset exists before switching
    target_dataset_def = DatasetRegistry.get(dataset_name.lower())

    tool = ToolRegistry.get("set_dataset")
    dataset = DatasetRegistry.get_active()
    result = tool.invoke(dataset, SetDatasetInput(dataset_name=dataset_name)).result

    # Append supported tools snapshot if dataset is valid
    if target_dataset_def is not None:
        result += _tool_selector.get_supported_tools_snapshot(
            target_dataset_def, _MCP_TOOL_NAMES
        )

    return result


@mcp.tool()
@require_oauth2
def get_database_schema() -> str:
    """📚 Discover what data is available in the database.

    **When to use:** Start here to understand what tables exist.

    Returns:
        List of all available tables in the database with current backend info.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    result = _tool_selector.check_compatibility("get_database_schema", dataset)
    if not result.compatible:
        return result.error_message

    tool = ToolRegistry.get("get_database_schema")
    return tool.invoke(dataset, GetDatabaseSchemaInput()).result


@mcp.tool()
@require_oauth2
def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """🔍 Explore a specific table's structure and see sample data.

    **When to use:** After identifying relevant tables from get_database_schema().

    Args:
        table_name: Exact table name (case-sensitive).
        show_sample: Whether to include sample rows (default: True).

    Returns:
        Table structure with column names, types, and sample data.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    result = _tool_selector.check_compatibility("get_table_info", dataset)
    if not result.compatible:
        return result.error_message

    tool = ToolRegistry.get("get_table_info")
    return tool.invoke(
        dataset, GetTableInfoInput(table_name=table_name, show_sample=show_sample)
    ).result


@mcp.tool()
@require_oauth2
def execute_query(sql_query: str) -> str:
    """🚀 Execute SQL queries to analyze data.

    **Recommended workflow:**
    1. Use get_database_schema() to list tables
    2. Use get_table_info() to examine structure
    3. Write your SQL query with exact names

    Args:
        sql_query: Your SQL SELECT query (SELECT only).

    Returns:
        Query results or helpful error messages.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    result = _tool_selector.check_compatibility("execute_query", dataset)
    if not result.compatible:
        return result.error_message

    tool = ToolRegistry.get("execute_query")
    return tool.invoke(dataset, ExecuteQueryInput(sql_query=sql_query)).result


def main():
    """Main entry point for MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
