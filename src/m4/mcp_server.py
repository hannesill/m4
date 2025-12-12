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

import logging

from fastmcp import FastMCP

from m4.auth import init_oauth2, require_oauth2
from m4.config import get_active_dataset
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.tools import ToolRegistry, ToolSelector, init_tools
from m4.core.tools.management import ListDatasetsInput, SetDatasetInput
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    GetDatabaseSchemaInput,
    GetICUStaysInput,
    GetLabResultsInput,
    GetRaceDistributionInput,
    GetTableInfoInput,
)

logger = logging.getLogger(__name__)

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
        "get_icu_stays",
        "get_lab_results",
        "get_race_distribution",
    }
)


def _get_active_dataset_def():
    """Get the currently active dataset definition.

    Returns:
        DatasetDefinition for the active dataset, or mimic-iv-demo as fallback.
    """
    active_ds_name = get_active_dataset()
    if active_ds_name:
        ds_def = DatasetRegistry.get(active_ds_name)
        if ds_def:
            return ds_def

    # Fallback to demo dataset
    return DatasetRegistry.get("mimic-iv-demo")


def _check_tool_compatibility(
    tool_name: str, dataset_def: DatasetDefinition
) -> tuple[bool, str]:
    """Check if a tool is compatible with the given dataset.

    Uses ToolSelector and tool metadata to perform proactive capability checking.
    This ensures users get helpful error messages before any backend execution
    is attempted.

    Args:
        tool_name: Name of the tool to check
        dataset_def: The dataset to check against

    Returns:
        Tuple of (is_compatible, error_message).
        If compatible, error_message is empty string.
        If not compatible, error_message contains user-facing guidance.
    """
    tool = ToolRegistry.get(tool_name)
    if not tool:
        logger.debug("Tool '%s' not found in registry", tool_name)
        return False, f"❌ **Error:** Unknown tool `{tool_name}`."

    # Use ToolSelector for capability-based check
    if _tool_selector.is_tool_available(tool_name, dataset_def):
        logger.debug(
            "Tool '%s' is compatible with dataset '%s'", tool_name, dataset_def.name
        )
        return True, ""

    # Build detailed incompatibility message
    logger.debug(
        "Tool '%s' is NOT compatible with dataset '%s'. "
        "Required modalities: %s, capabilities: %s. "
        "Dataset has modalities: %s, capabilities: %s",
        tool_name,
        dataset_def.name,
        tool.required_modalities,
        tool.required_capabilities,
        dataset_def.modalities,
        dataset_def.capabilities,
    )

    # Format modalities and capabilities for display
    required_modalities = sorted(m.name for m in tool.required_modalities)
    required_capabilities = sorted(c.name for c in tool.required_capabilities)
    available_modalities = sorted(m.name for m in dataset_def.modalities)
    available_capabilities = sorted(c.name for c in dataset_def.capabilities)

    # Find what's missing
    missing_modalities = set(required_modalities) - set(available_modalities)
    missing_capabilities = set(required_capabilities) - set(available_capabilities)

    error_parts = [
        f"❌ **Error:** Tool `{tool_name}` is not available for dataset "
        f"'{dataset_def.name}'.",
        "",
    ]

    if missing_modalities:
        error_parts.append(
            f"📦 **Missing modalities:** {', '.join(sorted(missing_modalities))}"
        )
    if missing_capabilities:
        error_parts.append(
            f"⚙️ **Missing capabilities:** {', '.join(sorted(missing_capabilities))}"
        )

    error_parts.extend(
        [
            "",
            "🔧 **Tool requires:**",
            f"   Modalities: {', '.join(required_modalities) or '(none)'}",
            f"   Capabilities: {', '.join(required_capabilities) or '(none)'}",
            "",
            f"📋 **Dataset '{dataset_def.name}' provides:**",
            f"   Modalities: {', '.join(available_modalities) or '(none)'}",
            f"   Capabilities: {', '.join(available_capabilities) or '(none)'}",
            "",
            "💡 **Suggestions:**",
            "   - Use `list_datasets()` to see all available datasets",
            "   - Use `set_dataset('dataset-name')` to switch datasets",
        ]
    )

    return False, "\n".join(error_parts)


def _get_supported_tools_snapshot(dataset_def: DatasetDefinition) -> str:
    """Generate a snapshot of supported tools for a dataset.

    Returns a formatted string listing the dataset's modalities, capabilities,
    and which MCP-exposed tools are available.

    Args:
        dataset_def: The dataset to generate snapshot for

    Returns:
        Formatted snapshot string
    """
    # Get compatible tools filtered to MCP-exposed ones
    compatible_tools = _tool_selector.tools_for_dataset(dataset_def)
    mcp_compatible = sorted(
        t.name for t in compatible_tools if t.name in _MCP_TOOL_NAMES
    )

    # Format modalities and capabilities
    modalities = sorted(m.name for m in dataset_def.modalities)
    capabilities = sorted(c.name for c in dataset_def.capabilities)

    snapshot_parts = [
        "",
        "─" * 40,
        f"✅ **Active dataset:** {dataset_def.name}",
        f"🧩 **Modalities:** {', '.join(modalities) or '(none)'}",
        f"⚙️ **Capabilities:** {', '.join(capabilities) or '(none)'}",
    ]

    if mcp_compatible:
        snapshot_parts.append(f"🛠️ **Supported tools:** {', '.join(mcp_compatible)}")
    else:
        snapshot_parts.append("⚠️ **No data tools available for this dataset.**")

    return "\n".join(snapshot_parts)


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
    dataset = _get_active_dataset_def()
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
    dataset = _get_active_dataset_def()
    result = tool.invoke(dataset, SetDatasetInput(dataset_name=dataset_name)).result

    # Append supported tools snapshot if dataset is valid
    if target_dataset_def is not None:
        result += _get_supported_tools_snapshot(target_dataset_def)

    return result


@mcp.tool()
@require_oauth2
def get_database_schema() -> str:
    """📚 Discover what data is available in the database.

    **When to use:** Start here to understand what tables exist.

    Returns:
        List of all available tables in the database with current backend info.
    """
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility("get_database_schema", dataset)
    if not is_compatible:
        return error_msg

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
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility("get_table_info", dataset)
    if not is_compatible:
        return error_msg

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
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility("execute_query", dataset)
    if not is_compatible:
        return error_msg

    tool = ToolRegistry.get("execute_query")
    return tool.invoke(dataset, ExecuteQueryInput(sql_query=sql_query)).result


@mcp.tool()
@require_oauth2
def get_icu_stays(patient_id: int | None = None, limit: int = 10) -> str:
    """🏥 Get ICU stay information and length of stay data.

    **Note:** Convenience function. For reliable queries, use the
    get_database_schema() → get_table_info() → execute_query() workflow.

    Args:
        patient_id: Specific patient ID to query (optional).
        limit: Maximum number of records (default: 10).

    Returns:
        ICU stay data or guidance if table not found.
    """
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility("get_icu_stays", dataset)
    if not is_compatible:
        return error_msg

    tool = ToolRegistry.get("get_icu_stays")
    return tool.invoke(
        dataset, GetICUStaysInput(patient_id=patient_id, limit=limit)
    ).result


@mcp.tool()
@require_oauth2
def get_lab_results(
    patient_id: int | None = None, lab_item: str | None = None, limit: int = 20
) -> str:
    """🧪 Get laboratory test results quickly.

    **Note:** Convenience function. For reliable queries, use the
    get_database_schema() → get_table_info() → execute_query() workflow.

    Args:
        patient_id: Specific patient ID to query (optional).
        lab_item: Lab item to filter by - either numeric itemid (e.g., "50912")
            or text pattern to search in labels (e.g., "glucose").
        limit: Maximum number of records (default: 20).

    Returns:
        Lab results or guidance if table not found.
    """
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility("get_lab_results", dataset)
    if not is_compatible:
        return error_msg

    tool = ToolRegistry.get("get_lab_results")
    return tool.invoke(
        dataset,
        GetLabResultsInput(patient_id=patient_id, lab_item=lab_item, limit=limit),
    ).result


@mcp.tool()
@require_oauth2
def get_race_distribution(limit: int = 10) -> str:
    """📊 Get race distribution from hospital admissions.

    **Note:** Convenience function. For reliable queries, use the
    get_database_schema() → get_table_info() → execute_query() workflow.

    Args:
        limit: Maximum number of race categories (default: 10).

    Returns:
        Race distribution or guidance if table not found.
    """
    dataset = _get_active_dataset_def()

    # Proactive capability check
    is_compatible, error_msg = _check_tool_compatibility(
        "get_race_distribution", dataset
    )
    if not is_compatible:
        return error_msg

    tool = ToolRegistry.get("get_race_distribution")
    return tool.invoke(dataset, GetRaceDistributionInput(limit=limit)).result


def main():
    """Main entry point for MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
