"""Tests for tool call telemetry."""

import json
import os
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import M4Error
from m4.core.telemetry import (
    _agent_id_var,
    _interface_var,
    _writer,
    invoke_tracked,
    set_agent_id,
    set_interface,
)
from m4.core.tools.base import ToolInput

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class MockInput(ToolInput):
    sql_query: str = "SELECT 1"
    limit: int = 10


class MockTool:
    name = "mock_tool"
    description = "A mock tool for testing"
    input_model = MockInput
    required_modalities = frozenset({Modality.TABULAR})
    supported_datasets = None

    def __init__(self, return_value="ok", side_effect=None):
        self._return_value = return_value
        self._side_effect = side_effect

    def invoke(self, dataset, params):
        if self._side_effect:
            raise self._side_effect
        return self._return_value

    def is_compatible(self, dataset):
        return True


@pytest.fixture
def mock_dataset():
    return DatasetDefinition(
        name="test-dataset",
        description="Test dataset",
        modalities=frozenset({Modality.TABULAR}),
    )


@pytest.fixture(autouse=True)
def reset_telemetry_state():
    """Reset telemetry writer and context vars between tests."""
    _writer.reset()
    token_iface = _interface_var.set("unknown")
    token_agent = _agent_id_var.set(None)
    yield
    _writer.reset()
    _interface_var.reset(token_iface)
    _agent_id_var.reset(token_agent)


def _capture_record(mock_dataset, tool=None, params=None):
    """Helper: invoke a tool and return the parsed telemetry record."""
    tool = tool or MockTool(return_value="ok")
    params = params or MockInput()
    with patch("m4.core.telemetry.logger") as mock_logger:
        invoke_tracked(tool, mock_dataset, params)
        return json.loads(mock_logger.info.call_args[0][0])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInvokeTracked:
    def test_returns_tool_result(self, mock_dataset):
        tool = MockTool(return_value={"data": [1, 2, 3]})
        result = invoke_tracked(tool, mock_dataset, MockInput())
        assert result == {"data": [1, 2, 3]}

    def test_success_record(self, mock_dataset):
        record = _capture_record(mock_dataset)

        assert record["success"] is True
        assert record["tool_name"] == "mock_tool"
        assert record["dataset_name"] == "test-dataset"
        assert record["error_type"] is None
        assert record["error_message"] is None
        assert record["duration_ms"] >= 0

    def test_failure_record_reraises(self, mock_dataset):
        tool = MockTool(side_effect=M4Error("something broke"))

        with patch("m4.core.telemetry.logger") as mock_logger:
            with pytest.raises(M4Error, match="something broke"):
                invoke_tracked(tool, mock_dataset, MockInput())

            record = json.loads(mock_logger.info.call_args[0][0])

        assert record["success"] is False
        assert record["error_type"] == "M4Error"
        assert record["error_message"] == "something broke"

    def test_context_vars_in_record(self, mock_dataset):
        set_interface("mcp")
        set_agent_id("agent-42")

        record = _capture_record(mock_dataset)

        assert record["interface"] == "mcp"
        assert record["agent_id"] == "agent-42"

    def test_params_captured(self, mock_dataset):
        params = MockInput(sql_query="SELECT * FROM patients", limit=5)
        record = _capture_record(mock_dataset, params=params)

        assert record["params_summary"]["sql_query"] == "SELECT * FROM patients"
        assert record["params_summary"]["limit"] == 5


class TestJSONLFile:
    def test_jsonl_written(self, mock_dataset, tmp_path):
        """JSONL file is written with valid JSON per line."""
        with patch("m4.config.get_telemetry_dir", return_value=tmp_path):
            tool = MockTool(return_value="ok")
            invoke_tracked(tool, mock_dataset, MockInput())
            invoke_tracked(tool, mock_dataset, MockInput(sql_query="SELECT 2"))

        jsonl_path = tmp_path / "tool_calls.jsonl"
        assert jsonl_path.exists()

        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 2

        for line in lines:
            record = json.loads(line)
            assert record["tool_name"] == "mock_tool"
            assert record["success"] is True

    def test_telemetry_off_suppresses_file(self, mock_dataset, tmp_path):
        """M4_TELEMETRY=off suppresses file output."""
        with patch.dict(os.environ, {"M4_TELEMETRY": "off"}):
            with patch("m4.config.get_telemetry_dir", return_value=tmp_path):
                tool = MockTool(return_value="ok")
                invoke_tracked(tool, mock_dataset, MockInput())

        jsonl_path = tmp_path / "tool_calls.jsonl"
        assert not jsonl_path.exists()


class TestContextVars:
    def test_default_interface(self, mock_dataset):
        record = _capture_record(mock_dataset)

        assert record["interface"] == "unknown"
        assert record["agent_id"] is None

    def test_set_interface(self):
        set_interface("python_api")
        assert _interface_var.get() == "python_api"

    def test_set_agent_id(self):
        set_agent_id("my-agent")
        assert _agent_id_var.get() == "my-agent"
