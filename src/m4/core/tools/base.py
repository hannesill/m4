"""Base tool protocol and input/output models.

This module defines the core Tool protocol that all M4 tools must implement.
Tools declare their required modalities and are automatically filtered based
on the active dataset's modalities.
"""

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from m4.core.datasets import DatasetDefinition, Modality


@dataclass
class ToolInput:
    """Base class for tool input parameters.

    Tool-specific input classes should inherit from this and add
    their own fields.

    Example:
        @dataclass
        class ICUStaysInput(ToolInput):
            patient_id: int | None = None
            limit: int = 10
    """

    pass


@dataclass
class ToolOutput:
    """Base class for tool output.

    All tools return a ToolOutput with at least a result string.
    Additional metadata can be included for debugging or logging.

    Attributes:
        result: The tool's output as a formatted string
        metadata: Optional metadata about the execution
    """

    result: str
    metadata: dict[str, Any] | None = None


@runtime_checkable
class Tool(Protocol):
    """Protocol defining the interface for all M4 tools.

    Tools must implement this protocol to be registered and used in M4.
    The protocol uses structural typing (duck typing) so tools don't need
    to explicitly inherit from a base class.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description (shown to LLMs)
        input_model: Class for parsing input parameters
        output_model: Class for formatting output
        required_modalities: Modalities required (e.g., TABULAR, NOTES)
        supported_datasets: Optional set of dataset names (None = all compatible)

    Example:
        class ExecuteQueryTool:
            name = "execute_query"
            description = "Execute SQL queries"
            input_model = ExecuteQueryInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.TABULAR})
            supported_datasets = None

            def invoke(self, dataset, params):
                # Implementation
                ...

            def is_compatible(self, dataset):
                # Compatibility check
                ...
    """

    # Tool metadata
    name: str
    description: str

    # Input/output specifications
    input_model: type[ToolInput]
    output_model: type[ToolOutput]

    # Compatibility constraints
    required_modalities: AbstractSet[Modality]
    supported_datasets: AbstractSet[str] | None  # None = all compatible datasets

    def invoke(self, dataset: DatasetDefinition, params: ToolInput) -> ToolOutput:
        """Execute the tool with given parameters on the specified dataset.

        Args:
            dataset: The dataset definition to query
            params: Tool-specific input parameters

        Returns:
            ToolOutput with formatted results

        Raises:
            Any exceptions should be caught and returned as error messages
            in the ToolOutput.result field.
        """
        ...

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if this tool is compatible with the given dataset.

        This method performs two checks:
        1. If supported_datasets is set, check if dataset.name is in the set
        2. Check if dataset has all required modalities

        Args:
            dataset: The dataset to check compatibility with

        Returns:
            True if the tool can operate on this dataset, False otherwise

        Example:
            tool = ExecuteQueryTool()
            mimic = DatasetRegistry.get("mimic-iv")
            if tool.is_compatible(mimic):
                output = tool.invoke(mimic, params)
        """
        # Check explicit dataset restrictions
        if self.supported_datasets is not None:
            if dataset.name not in self.supported_datasets:
                return False

        # Check modality requirements
        if not self.required_modalities.issubset(dataset.modalities):
            return False

        return True
