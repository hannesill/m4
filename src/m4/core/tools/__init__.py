"""M4 Core Tools - Tool protocol and registry.

This package provides the tool abstraction layer for M4:
- Tool protocol: Interface for all M4 tools
- ToolInput/ToolOutput: Base classes for tool parameters
- ToolRegistry: Registry for managing tools
- ToolSelector: Intelligent tool filtering based on capabilities
- init_tools(): Initialize and register all available tools
"""

from m4.core.tools.base import Tool, ToolInput, ToolOutput
from m4.core.tools.management import (
    ListDatasetsTool,
    SetDatasetTool,
)
from m4.core.tools.registry import ToolRegistry, ToolSelector

# Import tool classes for registration
from m4.core.tools.tabular import (
    ExecuteQueryTool,
    GetDatabaseSchemaTool,
    GetICUStaysTool,
    GetLabResultsTool,
    GetRaceDistributionTool,
    GetTableInfoTool,
)

# Track initialization state
_tools_initialized = False


def init_tools() -> None:
    """Initialize and register all available tools.

    This function registers all tool classes with the ToolRegistry.
    It is idempotent - calling it multiple times has no additional effect.

    This should be called during application startup, before the MCP
    server begins accepting requests.

    Example:
        from m4.core.tools import init_tools
        init_tools()  # Register all tools
    """
    global _tools_initialized

    if _tools_initialized:
        return

    # Register management tools (always available)
    ToolRegistry.register(ListDatasetsTool())
    ToolRegistry.register(SetDatasetTool())

    # Register tabular data tools
    ToolRegistry.register(GetDatabaseSchemaTool())
    ToolRegistry.register(GetTableInfoTool())
    ToolRegistry.register(ExecuteQueryTool())
    ToolRegistry.register(GetICUStaysTool())
    ToolRegistry.register(GetLabResultsTool())
    ToolRegistry.register(GetRaceDistributionTool())

    _tools_initialized = True


def reset_tools() -> None:
    """Reset the tool registry and initialization state.

    This is primarily useful for testing to ensure a clean state
    between test runs.
    """
    global _tools_initialized
    ToolRegistry.reset()
    _tools_initialized = False


__all__ = [
    "ExecuteQueryTool",
    "GetDatabaseSchemaTool",
    "GetICUStaysTool",
    "GetLabResultsTool",
    "GetRaceDistributionTool",
    "GetTableInfoTool",
    "ListDatasetsTool",
    "SetDatasetTool",
    "Tool",
    "ToolInput",
    "ToolOutput",
    "ToolRegistry",
    "ToolSelector",
    "init_tools",
    "reset_tools",
]
