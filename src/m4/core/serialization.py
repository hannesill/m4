"""Serialization utilities for converting native Python types to MCP-friendly strings.

This module provides the serialization layer that enables tools to return native
Python types (DataFrames, lists, dicts) while the MCP server converts them to
strings for the protocol.

The Python API bypasses this layer entirely, receiving native types directly.
"""

from typing import Any

import pandas as pd


def serialize_for_mcp(value: Any, max_rows: int = 50) -> str:
    """Convert native Python types to MCP-friendly strings.

    This is the primary entry point for the MCP server to serialize tool
    return values. The Python API should NOT use this function - it receives
    native types directly.

    Args:
        value: Any Python value to serialize
        max_rows: Maximum rows to display for DataFrames (default: 50)

    Returns:
        String representation suitable for MCP protocol

    Examples:
        >>> serialize_for_mcp(None)
        'Operation completed successfully.'

        >>> df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
        >>> print(serialize_for_mcp(df))
        |   a |   b |
        |----:|----:|
        |   1 |   3 |
        |   2 |   4 |

        >>> serialize_for_mcp(['table1', 'table2', 'table3'])
        'table1\\ntable2\\ntable3'
    """
    if value is None:
        return "Operation completed successfully."

    if isinstance(value, pd.DataFrame):
        return _serialize_dataframe(value, max_rows)

    if isinstance(value, list):
        return _serialize_list(value)

    if isinstance(value, dict):
        return _serialize_dict(value)

    # int, float, str, bool, etc.
    return str(value)


def _serialize_dataframe(df: pd.DataFrame, max_rows: int) -> str:
    """Convert DataFrame to formatted table with truncation.

    Args:
        df: DataFrame to serialize
        max_rows: Maximum number of rows to display

    Returns:
        Formatted table string
    """
    if df.empty:
        return "No results found"

    total_rows = len(df)
    truncated = total_rows > max_rows

    if truncated:
        display_df = df.head(max_rows)
        result = display_df.to_string(index=False)
        result += f"\n\n... ({total_rows} total rows, showing first {max_rows})"
        return result

    return df.to_string(index=False)


def _serialize_list(items: list) -> str:
    """Convert list to newline-separated string.

    Handles nested structures by converting elements to strings.

    Args:
        items: List to serialize

    Returns:
        Newline-separated string representation
    """
    if not items:
        return "(empty list)"

    # Check if list contains dicts (like search results)
    if items and isinstance(items[0], dict):
        return _serialize_list_of_dicts(items)

    return "\n".join(str(item) for item in items)


def _serialize_list_of_dicts(items: list[dict]) -> str:
    """Convert list of dicts to formatted output.

    Args:
        items: List of dictionaries to serialize

    Returns:
        Formatted string representation
    """
    if not items:
        return "(empty list)"

    # Convert to DataFrame for consistent table formatting
    df = pd.DataFrame(items)
    return df.to_markdown(index=False)


def _serialize_dict(data: dict) -> str:
    """Convert dict to formatted key-value pairs.

    Args:
        data: Dictionary to serialize

    Returns:
        Formatted string representation
    """
    if not data:
        return "(empty)"

    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            # Nested dict - indent
            lines.append(f"**{key}:**")
            for k, v in value.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(value, list):
            lines.append(f"**{key}:** {', '.join(str(v) for v in value)}")
        else:
            lines.append(f"**{key}:** {value}")

    return "\n".join(lines)
