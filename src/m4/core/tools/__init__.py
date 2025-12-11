"""M4 Core Tools - Tool protocol and registry.

This package provides the tool abstraction layer for M4:
- Tool protocol: Interface for all M4 tools
- ToolInput/ToolOutput: Base classes for tool parameters
- ToolRegistry: Registry for managing tools (Phase 2)
"""

from m4.core.tools.base import Tool, ToolInput, ToolOutput

__all__ = [
    "Tool",
    "ToolInput",
    "ToolOutput",
]
