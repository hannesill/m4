"""Tests for m4.core.tools.base module.

Tests cover:
- ToolInput and ToolOutput base classes
- Tool protocol implementation
- Tool compatibility checking
"""

from dataclasses import dataclass

from m4.core.datasets import (
    DatasetDefinition,
    Modality,
)
from m4.core.tools.base import Tool, ToolInput, ToolOutput


class TestToolInputOutput:
    """Test ToolInput and ToolOutput base classes."""

    def test_tool_input_can_be_subclassed(self):
        """Test that ToolInput can be extended with custom fields."""

        @dataclass
        class CustomInput(ToolInput):
            patient_id: int
            limit: int = 10

        input_obj = CustomInput(patient_id=123, limit=5)
        assert input_obj.patient_id == 123
        assert input_obj.limit == 5

    def test_tool_output_with_result(self):
        """Test creating ToolOutput with result."""
        output = ToolOutput(result="test result")
        assert output.result == "test result"
        assert output.metadata is None

    def test_tool_output_with_metadata(self):
        """Test creating ToolOutput with metadata."""
        output = ToolOutput(
            result="test result",
            metadata={"rows": 10, "execution_time": 0.5},
        )
        assert output.result == "test result"
        assert output.metadata["rows"] == 10
        assert output.metadata["execution_time"] == 0.5


class TestToolProtocol:
    """Test Tool protocol implementation."""

    def test_tool_protocol_basics(self):
        """Test that a class can implement the Tool protocol."""

        class MockTool:
            name = "mock_tool"
            description = "A mock tool for testing"
            input_model = ToolInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.TABULAR})
            supported_datasets = None

            def invoke(self, dataset, params):
                return ToolOutput(result="mock result")

            def is_compatible(self, dataset):
                if (
                    self.supported_datasets
                    and dataset.name not in self.supported_datasets
                ):
                    return False
                if not self.required_modalities.issubset(dataset.modalities):
                    return False
                return True

        # Should be recognized as a Tool
        tool = MockTool()
        assert isinstance(tool, Tool)

    def test_tool_is_compatible_with_matching_dataset(self):
        """Test that tool is compatible with dataset that has required modalities."""

        class MockTool:
            name = "mock_tool"
            description = "A mock tool"
            input_model = ToolInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.TABULAR})
            supported_datasets = None

            def invoke(self, dataset, params):
                return ToolOutput(result="mock")

            def is_compatible(self, dataset):
                if (
                    self.supported_datasets
                    and dataset.name not in self.supported_datasets
                ):
                    return False
                if not self.required_modalities.issubset(dataset.modalities):
                    return False
                return True

        tool = MockTool()

        compatible_ds = DatasetDefinition(
            name="test-compatible",
            modalities={Modality.TABULAR, Modality.NOTES},
        )

        assert tool.is_compatible(compatible_ds) is True

    def test_tool_not_compatible_with_missing_modality(self):
        """Test that tool is not compatible when dataset lacks required modality."""

        class MockTool:
            name = "notes_tool"
            description = "A notes tool"
            input_model = ToolInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.NOTES})
            supported_datasets = None

            def invoke(self, dataset, params):
                return ToolOutput(result="mock")

            def is_compatible(self, dataset):
                if (
                    self.supported_datasets
                    and dataset.name not in self.supported_datasets
                ):
                    return False
                if not self.required_modalities.issubset(dataset.modalities):
                    return False
                return True

        tool = MockTool()

        # Dataset without NOTES modality
        incompatible_ds = DatasetDefinition(
            name="test-no-notes",
            modalities={Modality.TABULAR},
        )

        assert tool.is_compatible(incompatible_ds) is False

    def test_tool_with_supported_datasets_filter(self):
        """Test that tool can restrict to specific datasets."""

        class MockTool:
            name = "mimic_specific_tool"
            description = "MIMIC-only tool"
            input_model = ToolInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.TABULAR})
            supported_datasets = frozenset({"mimic-iv-demo", "mimic-iv"})

            def invoke(self, dataset, params):
                return ToolOutput(result="mock")

            def is_compatible(self, dataset):
                if (
                    self.supported_datasets
                    and dataset.name not in self.supported_datasets
                ):
                    return False
                if not self.required_modalities.issubset(dataset.modalities):
                    return False
                return True

        tool = MockTool()

        # Compatible dataset in supported list
        mimic_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities={Modality.TABULAR},
        )
        assert tool.is_compatible(mimic_ds) is True

        # Dataset with modalities but not in supported list
        eicu_ds = DatasetDefinition(
            name="eicu",
            modalities={Modality.TABULAR},
        )
        assert tool.is_compatible(eicu_ds) is False

    def test_tool_invoke_returns_output(self):
        """Test that tool invoke method returns ToolOutput."""

        @dataclass
        class CustomInput(ToolInput):
            query: str

        class MockTool:
            name = "query_tool"
            description = "A query tool"
            input_model = CustomInput
            output_model = ToolOutput
            required_modalities = frozenset({Modality.TABULAR})
            supported_datasets = None

            def invoke(self, dataset, params):
                result = f"Executed query: {params.query} on {dataset.name}"
                return ToolOutput(result=result, metadata={"dataset": dataset.name})

            def is_compatible(self, dataset):
                return True

        tool = MockTool()
        dataset = DatasetDefinition(
            name="test-dataset",
            modalities={Modality.TABULAR},
        )
        params = CustomInput(query="SELECT * FROM patients")

        output = tool.invoke(dataset, params)

        assert isinstance(output, ToolOutput)
        assert "SELECT * FROM patients" in output.result
        assert "test-dataset" in output.result
        assert output.metadata["dataset"] == "test-dataset"
