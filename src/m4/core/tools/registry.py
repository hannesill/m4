"""Tool registry and selector for capability-based tool filtering.

This module provides:
- ToolRegistry: Central registry for all available tools
- ToolSelector: Intelligent tool filtering based on dataset capabilities
- CompatibilityResult: Result object for tool compatibility checks
"""

import logging
from dataclasses import dataclass, field
from typing import ClassVar

from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.tools.base import Tool

logger = logging.getLogger(__name__)


@dataclass
class CompatibilityResult:
    """Result of a tool compatibility check.

    Attributes:
        compatible: Whether the tool is compatible with the dataset
        tool_name: Name of the tool that was checked
        dataset_name: Name of the dataset checked against
        missing_modalities: Set of modality names the dataset is missing
        missing_capabilities: Set of capability names the dataset is missing
        error_message: Formatted error message if not compatible (empty if compatible)
    """

    compatible: bool
    tool_name: str
    dataset_name: str
    missing_modalities: set[str] = field(default_factory=set)
    missing_capabilities: set[str] = field(default_factory=set)
    error_message: str = ""


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

    def check_compatibility(
        self, tool_name: str, dataset: DatasetDefinition
    ) -> CompatibilityResult:
        """Check tool compatibility and return detailed result.

        Performs proactive capability checking before tool invocation.
        Returns a result object with compatibility status and formatted
        error message for user-facing output.

        Args:
            tool_name: Name of the tool to check
            dataset: The dataset to check against

        Returns:
            CompatibilityResult with compatibility status and error details
        """
        tool = ToolRegistry.get(tool_name)
        if not tool:
            logger.debug("Tool '%s' not found in registry", tool_name)
            return CompatibilityResult(
                compatible=False,
                tool_name=tool_name,
                dataset_name=dataset.name,
                error_message=f"❌ **Error:** Unknown tool `{tool_name}`.",
            )

        # Use existing compatibility check
        if self.is_tool_available(tool_name, dataset):
            logger.debug(
                "Tool '%s' is compatible with dataset '%s'", tool_name, dataset.name
            )
            return CompatibilityResult(
                compatible=True,
                tool_name=tool_name,
                dataset_name=dataset.name,
            )

        # Build detailed incompatibility info
        logger.debug(
            "Tool '%s' is NOT compatible with dataset '%s'. "
            "Required modalities: %s, capabilities: %s. "
            "Dataset has modalities: %s, capabilities: %s",
            tool_name,
            dataset.name,
            tool.required_modalities,
            tool.required_capabilities,
            dataset.modalities,
            dataset.capabilities,
        )

        # Calculate what's missing
        required_modalities = {m.name for m in tool.required_modalities}
        required_capabilities = {c.name for c in tool.required_capabilities}
        available_modalities = {m.name for m in dataset.modalities}
        available_capabilities = {c.name for c in dataset.capabilities}

        missing_modalities = required_modalities - available_modalities
        missing_capabilities = required_capabilities - available_capabilities

        # Build formatted error message
        error_message = self._format_incompatibility_error(
            tool_name=tool_name,
            dataset_name=dataset.name,
            required_modalities=sorted(required_modalities),
            required_capabilities=sorted(required_capabilities),
            available_modalities=sorted(available_modalities),
            available_capabilities=sorted(available_capabilities),
            missing_modalities=missing_modalities,
            missing_capabilities=missing_capabilities,
        )

        return CompatibilityResult(
            compatible=False,
            tool_name=tool_name,
            dataset_name=dataset.name,
            missing_modalities=missing_modalities,
            missing_capabilities=missing_capabilities,
            error_message=error_message,
        )

    def _format_incompatibility_error(
        self,
        tool_name: str,
        dataset_name: str,
        required_modalities: list[str],
        required_capabilities: list[str],
        available_modalities: list[str],
        available_capabilities: list[str],
        missing_modalities: set[str],
        missing_capabilities: set[str],
    ) -> str:
        """Format a user-friendly incompatibility error message."""
        error_parts = [
            f"❌ **Error:** Tool `{tool_name}` is not available for dataset "
            f"'{dataset_name}'.",
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
                f"📋 **Dataset '{dataset_name}' provides:**",
                f"   Modalities: {', '.join(available_modalities) or '(none)'}",
                f"   Capabilities: {', '.join(available_capabilities) or '(none)'}",
                "",
                "💡 **Suggestions:**",
                "   - Use `list_datasets()` to see all available datasets",
                "   - Use `set_dataset('dataset-name')` to switch datasets",
            ]
        )

        return "\n".join(error_parts)

    def get_supported_tools_snapshot(
        self,
        dataset: DatasetDefinition,
        mcp_tool_names: frozenset[str] | None = None,
    ) -> str:
        """Generate a snapshot of supported tools for a dataset.

        Returns a formatted string listing the dataset's modalities,
        capabilities, and which tools are available.

        Args:
            dataset: The dataset to generate snapshot for
            mcp_tool_names: Optional filter to only include these tool names.
                           If None, includes all compatible tools.

        Returns:
            Formatted snapshot string
        """
        # Get compatible tools
        compatible_tools = self.tools_for_dataset(dataset)

        # Filter to MCP-exposed ones if filter provided
        if mcp_tool_names is not None:
            tool_names = sorted(
                t.name for t in compatible_tools if t.name in mcp_tool_names
            )
        else:
            tool_names = sorted(t.name for t in compatible_tools)

        # Format modalities and capabilities
        modalities = sorted(m.name for m in dataset.modalities)
        capabilities = sorted(c.name for c in dataset.capabilities)

        snapshot_parts = [
            "",
            "─" * 40,
            f"✅ **Active dataset:** {dataset.name}",
            f"🧩 **Modalities:** {', '.join(modalities) or '(none)'}",
            f"⚙️ **Capabilities:** {', '.join(capabilities) or '(none)'}",
        ]

        if tool_names:
            snapshot_parts.append(f"🛠️ **Supported tools:** {', '.join(tool_names)}")
        else:
            snapshot_parts.append("⚠️ **No data tools available for this dataset.**")

        return "\n".join(snapshot_parts)
