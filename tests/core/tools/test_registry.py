"""Tests for ToolRegistry and ToolSelector."""

import pytest

from m4.core.datasets import Capability, DatasetDefinition, DatasetRegistry, Modality
from m4.core.tools import Tool, ToolInput, ToolOutput, ToolRegistry, ToolSelector


# Mock tool classes for testing
class MockTabularTool:
    """Mock tool requiring only tabular data."""

    name = "mock_tabular"
    description = "Mock tabular tool"
    input_model = ToolInput
    output_model = ToolOutput
    required_modalities = {Modality.TABULAR}
    required_capabilities = {Capability.COHORT_QUERY}
    supported_datasets = None

    def invoke(self, dataset: DatasetDefinition, params: ToolInput) -> ToolOutput:
        return ToolOutput(result="tabular data")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class MockNotesTool:
    """Mock tool requiring notes modality."""

    name = "mock_notes"
    description = "Mock notes tool"
    input_model = ToolInput
    output_model = ToolOutput
    required_modalities = {Modality.NOTES}
    required_capabilities = {Capability.CLINICAL_NOTES}
    supported_datasets = None

    def invoke(self, dataset: DatasetDefinition, params: ToolInput) -> ToolOutput:
        return ToolOutput(result="notes data")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class MockMIMICOnlyTool:
    """Mock tool that only works with MIMIC datasets."""

    name = "mock_mimic_only"
    description = "Mock MIMIC-only tool"
    input_model = ToolInput
    output_model = ToolOutput
    required_modalities = {Modality.TABULAR}
    required_capabilities = {Capability.ICU_STAYS}
    supported_datasets = {"mimic-iv-full", "mimic-iv-demo"}

    def invoke(self, dataset: DatasetDefinition, params: ToolInput) -> ToolOutput:
        return ToolOutput(result="mimic data")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


@pytest.fixture(autouse=True)
def reset_registries():
    """Reset tool registry before and after each test."""
    ToolRegistry.reset()
    yield
    ToolRegistry.reset()


class TestToolRegistry:
    """Test ToolRegistry functionality."""

    def test_register_tool(self):
        """Test registering a tool."""
        tool = MockTabularTool()
        ToolRegistry.register(tool)

        registered = ToolRegistry.get("mock_tabular")
        assert registered is not None
        assert registered.name == "mock_tabular"

    def test_register_duplicate_name_raises_error(self):
        """Test that registering a duplicate tool name raises ValueError."""
        tool1 = MockTabularTool()
        tool2 = MockTabularTool()

        ToolRegistry.register(tool1)
        with pytest.raises(ValueError, match="already registered"):
            ToolRegistry.register(tool2)

    def test_get_nonexistent_tool(self):
        """Test getting a tool that doesn't exist."""
        result = ToolRegistry.get("nonexistent")
        assert result is None

    def test_list_all_tools(self):
        """Test listing all registered tools."""
        tool1 = MockTabularTool()
        tool2 = MockNotesTool()

        ToolRegistry.register(tool1)
        ToolRegistry.register(tool2)

        all_tools = ToolRegistry.list_all()
        assert len(all_tools) == 2
        assert tool1 in all_tools
        assert tool2 in all_tools

    def test_list_all_empty(self):
        """Test listing tools when registry is empty."""
        all_tools = ToolRegistry.list_all()
        assert all_tools == []

    def test_reset_clears_registry(self):
        """Test that reset clears all registered tools."""
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())

        assert len(ToolRegistry.list_all()) == 2

        ToolRegistry.reset()
        assert len(ToolRegistry.list_all()) == 0


class TestToolSelector:
    """Test ToolSelector filtering logic."""

    def test_selector_returns_compatible_tools(self):
        """Test that selector returns only compatible tools."""
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())

        selector = ToolSelector()
        mimic_demo = DatasetRegistry.get("mimic-iv-demo")

        compatible = selector.tools_for_dataset(mimic_demo)

        # mimic-demo has TABULAR but not NOTES
        assert len(compatible) == 1
        assert compatible[0].name == "mock_tabular"

    def test_selector_with_notes_dataset(self):
        """Test selector with dataset that has notes."""
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())

        selector = ToolSelector()
        mimic_full = DatasetRegistry.get("mimic-iv-full")

        compatible = selector.tools_for_dataset(mimic_full)

        # mimic-full has both TABULAR and NOTES
        assert len(compatible) == 2
        tool_names = {tool.name for tool in compatible}
        assert "mock_tabular" in tool_names
        assert "mock_notes" in tool_names

    def test_selector_filters_by_dataset_name(self):
        """Test that selector respects supported_datasets restrictions."""
        ToolRegistry.register(MockMIMICOnlyTool())

        selector = ToolSelector()

        # Should work with MIMIC datasets
        mimic = DatasetRegistry.get("mimic-iv-demo")
        compatible = selector.tools_for_dataset(mimic)
        assert len(compatible) == 1

        # Create a non-MIMIC dataset with same capabilities
        eicu = DatasetDefinition(
            name="eicu",
            description="eICU database",
            modalities={Modality.TABULAR},
            capabilities={Capability.ICU_STAYS, Capability.COHORT_QUERY},
        )

        # Should NOT work with non-MIMIC datasets (even with capabilities)
        compatible = selector.tools_for_dataset(eicu)
        assert len(compatible) == 0

    def test_selector_by_dataset_name_string(self):
        """Test selector using dataset name as string."""
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())

        selector = ToolSelector()

        # Use string instead of DatasetDefinition
        compatible = selector.tools_for_dataset("mimic-iv-full")

        assert len(compatible) == 2
        tool_names = {tool.name for tool in compatible}
        assert "mock_tabular" in tool_names
        assert "mock_notes" in tool_names

    def test_selector_unknown_dataset_returns_empty(self):
        """Test selector with unknown dataset name."""
        ToolRegistry.register(MockTabularTool())

        selector = ToolSelector()
        compatible = selector.tools_for_dataset("unknown-dataset")

        assert compatible == []

    def test_is_tool_available_by_name(self):
        """Test checking if a specific tool is available."""
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())

        selector = ToolSelector()

        # Tabular tool available for demo (has TABULAR)
        assert selector.is_tool_available("mock_tabular", "mimic-iv-demo")

        # Notes tool NOT available for demo (lacks NOTES)
        assert not selector.is_tool_available("mock_notes", "mimic-iv-demo")

        # Both available for full (has TABULAR + NOTES)
        assert selector.is_tool_available("mock_tabular", "mimic-iv-full")
        assert selector.is_tool_available("mock_notes", "mimic-iv-full")

    def test_is_tool_available_with_dataset_definition(self):
        """Test is_tool_available with DatasetDefinition object."""
        ToolRegistry.register(MockTabularTool())

        selector = ToolSelector()
        mimic = DatasetRegistry.get("mimic-iv-demo")

        assert selector.is_tool_available("mock_tabular", mimic)

    def test_is_tool_available_nonexistent_tool(self):
        """Test is_tool_available with tool that doesn't exist."""
        selector = ToolSelector()
        assert not selector.is_tool_available("nonexistent", "mimic-iv-demo")

    def test_is_tool_available_unknown_dataset(self):
        """Test is_tool_available with unknown dataset."""
        ToolRegistry.register(MockTabularTool())

        selector = ToolSelector()
        assert not selector.is_tool_available("mock_tabular", "unknown-dataset")

    def test_tools_for_dataset_empty_registry(self):
        """Test tools_for_dataset when no tools are registered."""
        selector = ToolSelector()
        compatible = selector.tools_for_dataset("mimic-iv-demo")

        assert compatible == []


class TestIntegration:
    """Integration tests for registry and selector together."""

    def test_multiple_tools_with_varying_requirements(self):
        """Test complex scenario with multiple tools and datasets."""
        # Register tools
        ToolRegistry.register(MockTabularTool())
        ToolRegistry.register(MockNotesTool())
        ToolRegistry.register(MockMIMICOnlyTool())

        selector = ToolSelector()

        # Test with demo (TABULAR only)
        demo_tools = selector.tools_for_dataset("mimic-iv-demo")
        demo_names = {t.name for t in demo_tools}
        assert "mock_tabular" in demo_names
        assert "mock_mimic_only" in demo_names
        assert "mock_notes" not in demo_names  # No notes in demo

        # Test with full (TABULAR + NOTES)
        full_tools = selector.tools_for_dataset("mimic-iv-full")
        full_names = {t.name for t in full_tools}
        assert "mock_tabular" in full_names
        assert "mock_mimic_only" in full_names
        assert "mock_notes" in full_names  # Has notes

    def test_tool_protocol_conformance(self):
        """Test that tools conform to the Tool protocol."""
        tool = MockTabularTool()

        # Check protocol conformance
        assert isinstance(tool, Tool)
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "invoke")
        assert hasattr(tool, "is_compatible")
