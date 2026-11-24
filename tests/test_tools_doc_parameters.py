"""docs/TOOLS.md lists the parameters each MCP tool takes."""

import inspect
import re
from pathlib import Path

import pytest

from m4 import mcp_server

TOOLS_MD = Path(__file__).resolve().parents[1] / "docs" / "TOOLS.md"


def _documented_parameters() -> dict[str, set[str]]:
    sections = re.split(r"^### `(\w+)`$", TOOLS_MD.read_text(), flags=re.M)
    documented = {}
    for name, body in zip(sections[1::2], sections[2::2], strict=True):
        if "**Parameters:**\n" in body:
            block = body.split("**Parameters:**\n", 1)[1].split("\n\n", 1)[0]
            documented[name] = set(re.findall(r"^- `(\w+)`", block, flags=re.M))
    return documented


DOCUMENTED = _documented_parameters()


def test_parameter_lists_are_found():
    assert {"get_table_info", "execute_query", "search_notes"} <= DOCUMENTED.keys()


@pytest.mark.parametrize("tool_name", sorted(DOCUMENTED))
def test_documented_parameters_match_the_tool(tool_name):
    tool = getattr(mcp_server, tool_name)
    signature = inspect.signature(tool.fn)
    assert DOCUMENTED[tool_name] == set(signature.parameters)
