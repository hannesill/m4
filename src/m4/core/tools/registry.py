"""Tool registry and selector for capability-based tool filtering.

This module provides:
- ToolRegistry: Central registry for all available tools
- ToolSelector: Intelligent tool filtering based on dataset capabilities
"""

from typing import ClassVar

from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.tools.base import Tool


class ToolRegistry:
    """Registry for managing available tools.

    This class maintains a global registry of all tools that can be
    exposed via the MCP server. Tools are filtered dynamically based
    on the active dataset's capabilities.

    Example:
        # Register tools
        ToolRegistry.register(GetICUStaysTool())
        ToolRegistry.register(SearchClinicalNotesTool())

        # List all registered tools
        all_tools = ToolRegistry.list_all()
    """

    _tools: ClassVar[dict[str, Tool]] = {}

    @classmethod
    def register(cls, tool: Tool):
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in cls._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                f"Use a unique name or unregister the existing tool first."
            )
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Tool | None:
        """Get a tool by name.

        Args:
            name: Tool name (exact match, case-sensitive)

        Returns:
            Tool instance if found, None otherwise
        """
        return cls._tools.get(name)

    @classmethod
    def list_all(cls) -> list[Tool]:
        """Get all registered tools.

        Returns:
            List of all Tool instances
        """
        return list(cls._tools.values())

    @classmethod
    def reset(cls):
        """Clear all registered tools.

        Useful for testing or re-initialization.
        """
        cls._tools.clear()


class ToolSelector:
    """Intelligent tool selection based on dataset capabilities.

    This class provides the core filtering logic that determines which
    tools should be exposed to the LLM based on the active dataset's
    declared capabilities.

    Example:
        selector = ToolSelector()
        mimic = DatasetRegistry.get("mimic-iv-full")
        compatible_tools = selector.tools_for_dataset(mimic)
    """

    def tools_for_dataset(self, dataset: DatasetDefinition | str) -> list[Tool]:
        """Get all tools compatible with a given dataset.

        This method performs three-level filtering:
        1. Explicit dataset restrictions (if tool.supported_datasets is set)
        2. Modality requirements (dataset must have all required modalities)
        3. Capability requirements (dataset must have all required capabilities)

        Args:
            dataset: DatasetDefinition instance or dataset name string

        Returns:
            List of compatible Tool instances

        Example:
            # By name
            tools = selector.tools_for_dataset("mimic-iv-full")

            # By definition
            mimic = DatasetRegistry.get("mimic-iv-full")
            tools = selector.tools_for_dataset(mimic)
        """
        # Resolve dataset if given as string
        if isinstance(dataset, str):
            resolved = DatasetRegistry.get(dataset)
            if not resolved:
                return []  # Unknown dataset → no tools
            dataset = resolved

        compatible = []
        for tool in ToolRegistry.list_all():
            if tool.is_compatible(dataset):
                compatible.append(tool)

        return compatible

    def is_tool_available(
        self, tool_name: str, dataset: DatasetDefinition | str
    ) -> bool:
        """Check if a specific tool is available for a dataset.

        Args:
            tool_name: Name of the tool to check
            dataset: DatasetDefinition instance or dataset name

        Returns:
            True if the tool exists and is compatible with the dataset

        Example:
            if selector.is_tool_available("search_clinical_notes", "eicu"):
                # eICU doesn't have notes → False
                ...
        """
        tool = ToolRegistry.get(tool_name)
        if not tool:
            return False

        # Resolve dataset if given as string
        if isinstance(dataset, str):
            resolved = DatasetRegistry.get(dataset)
            if not resolved:
                return False
            dataset = resolved

        return tool.is_compatible(dataset)
