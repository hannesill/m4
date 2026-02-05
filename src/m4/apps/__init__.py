"""M4 Apps - MCP Apps with interactive UIs.

This package provides MCP Apps that render interactive UI alongside text results.
MCP Apps require hosts that support the MCP Apps protocol (Claude Desktop, etc.).

Apps are registered with the ToolRegistry like regular tools, but also declare
a UI resource that the host can render in an iframe.
"""

import threading

from m4.apps.cohort_builder.tool import CohortBuilderTool, QueryCohortTool
from m4.core.tools import ToolRegistry

# Track initialization state with thread safety
_apps_lock = threading.Lock()
_apps_initialized = False


def init_apps() -> None:
    """Initialize and register all available MCP Apps.

    This function registers all app tool classes with the ToolRegistry.
    It is idempotent and thread-safe - calling it multiple times or
    from multiple threads has no additional effect.

    This should be called during application startup, after init_tools().

    Example:
        from m4.apps import init_apps
        init_apps()  # Register all apps
    """
    global _apps_initialized

    with _apps_lock:
        # Check if already initialized
        if _apps_initialized:
            # Verify tools are still registered
            if ToolRegistry.get("cohort_builder") and ToolRegistry.get("query_cohort"):
                return

        # Register cohort builder app tools
        ToolRegistry.register(CohortBuilderTool())
        ToolRegistry.register(QueryCohortTool())

        _apps_initialized = True


def reset_apps() -> None:
    """Reset the app initialization state.

    This is primarily useful for testing to ensure a clean state
    between test runs. Thread-safe.

    Note: This does NOT remove tools from ToolRegistry - use reset_tools()
    for that. This only resets the initialization flag.
    """
    global _apps_initialized

    with _apps_lock:
        _apps_initialized = False


__all__ = [
    "CohortBuilderTool",
    "QueryCohortTool",
    "init_apps",
    "reset_apps",
]
