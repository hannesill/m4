"""M4 MCP Server - Thin MCP Protocol Adapter.

This module provides the FastMCP server that exposes M4 tools via MCP protocol.
All business logic is delegated to tool classes in m4.core.tools.

Architecture:
    mcp_server.py (this file) - MCP protocol adapter
        ↓ delegates to
    core/tools/*.py - Tool implementations (return native types)
        ↓ uses
    core/backends/*.py - Database backends

    The MCP layer uses the serialization module to convert native Python
    types to MCP-friendly strings. Exceptions are caught and formatted.

Tool Surface:
    The MCP tool surface is stable - all tools remain registered regardless of
    the active dataset. Compatibility is enforced per-call via proactive
    capability checking before tool invocation.
"""

from typing import Any

import pandas as pd
from fastmcp import FastMCP

from m4.auth import init_oauth2, require_oauth2
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import M4Error
from m4.core.serialization import serialize_for_mcp
from m4.core.tools import ToolRegistry, ToolSelector, init_tools
from m4.core.tools.management import ListDatasetsInput, SetDatasetInput
from m4.core.tools.notes import (
    GetNoteInput,
    ListPatientNotesInput,
    SearchNotesInput,
)
from m4.core.tools.tabular import (
    ExecuteQueryInput,
    GetDatabaseSchemaInput,
    GetTableInfoInput,
)

# Create FastMCP server instance
mcp = FastMCP("m4")

# Initialize systems
init_oauth2()
init_tools()

# Tool selector for capability-based filtering
_tool_selector = ToolSelector()

# MCP-exposed tool names (for filtering in set_dataset snapshot)
_MCP_TOOL_NAMES = frozenset(
    {
        "list_datasets",
        "set_dataset",
        "get_database_schema",
        "get_table_info",
        "execute_query",
        "search_notes",
        "get_note",
        "list_patient_notes",
    }
)


# ===========================================
# SERIALIZATION HELPERS
# ===========================================


def _serialize_schema_result(result: dict[str, Any]) -> str:
    """Serialize get_database_schema result to MCP string."""
    backend_info = result.get("backend_info", "")
    tables = result.get("tables", [])

    if not tables:
        return f"{backend_info}\n**Available Tables:**\nNo tables found"

    table_list = "\n".join(f"  {t}" for t in tables)
    return f"{backend_info}\n**Available Tables:**\n{table_list}"


def _serialize_table_info_result(result: dict[str, Any]) -> str:
    """Serialize get_table_info result to MCP string."""
    backend_info = result.get("backend_info", "")
    table_name = result.get("table_name", "")
    schema = result.get("schema")
    sample = result.get("sample")

    parts = [
        backend_info,
        f"**Table:** {table_name}",
        "",
        "**Column Information:**",
    ]

    if schema is not None and isinstance(schema, pd.DataFrame):
        parts.append(schema.to_string(index=False))
    else:
        parts.append("(no schema information)")

    if sample is not None and isinstance(sample, pd.DataFrame) and not sample.empty:
        parts.extend(
            [
                "",
                "**Sample Data (first 3 rows):**",
                sample.to_string(index=False),
            ]
        )

    return "\n".join(parts)


def _serialize_datasets_result(result: dict[str, Any]) -> str:
    """Serialize list_datasets result to MCP string."""
    active = result.get("active_dataset") or "(unset)"
    backend = result.get("backend", "duckdb")
    datasets = result.get("datasets", {})

    if not datasets:
        return "No datasets detected."

    output = [f"Active dataset: {active}\n"]
    output.append(
        f"Backend: {'local (DuckDB)' if backend == 'duckdb' else 'cloud (BigQuery)'}\n"
    )

    for label, info in datasets.items():
        is_active = " (Active)" if info.get("is_active") else ""
        output.append(f"=== {label.upper()}{is_active} ===")

        parquet_icon = "✅" if info.get("parquet_present") else "❌"
        db_icon = "✅" if info.get("db_present") else "❌"
        bq_status = "✅" if info.get("bigquery_support") else "❌"

        output.append(f"  Local Parquet: {parquet_icon}")
        output.append(f"  Local Database: {db_icon}")
        output.append(f"  BigQuery Support: {bq_status}")

        derived = info.get("derived")
        if derived and derived.get("supported"):
            total = derived["total"]
            materialized = derived.get("materialized")
            if materialized is not None:
                icon = "✅" if materialized == total else "⚠️"
                output.append(
                    f"  Derived Tables: {icon} {materialized}/{total} materialized"
                )
                if materialized < total:
                    output.append(f"    Run: m4 init-derived {label}")
            else:
                output.append(f"  Derived Tables: ✅ {total} available")

        output.append("")

    return "\n".join(output)


def _serialize_set_dataset_result(result: dict[str, Any]) -> str:
    """Serialize set_dataset result to MCP string."""
    dataset_name = result.get("dataset_name", "")
    warnings = result.get("warnings", [])

    status_msg = f"✅ Active dataset switched to '{dataset_name}'."

    for warning in warnings:
        status_msg += f"\n⚠️ {warning}"

    return status_msg


def _serialize_search_notes_result(result: dict[str, Any]) -> str:
    """Serialize search_notes result to MCP string."""
    backend_info = result.get("backend_info", "")
    query = result.get("query", "")
    snippet_length = result.get("snippet_length", 300)
    results = result.get("results", {})

    if not results or all(df.empty for df in results.values()):
        tables = ", ".join(results.keys()) if results else "notes"
        return f"{backend_info}\n**No matches found** for '{query}' in {tables}."

    output_parts = [
        backend_info,
        f"**Search:** '{query}' (showing snippets of ~{snippet_length} chars)",
    ]

    for table, df in results.items():
        if not df.empty:
            output_parts.append(f"\n**{table.upper()}:**\n{df.to_string(index=False)}")

    output_parts.append(
        "\n**Tip:** Use `get_note(note_id)` to retrieve full text of a specific note."
    )

    return "\n".join(output_parts)


def _serialize_get_note_result(result: dict[str, Any]) -> str:
    """Serialize get_note result to MCP string."""
    backend_info = result.get("backend_info", "")
    note_id = result.get("note_id", "")
    subject_id = result.get("subject_id", "")
    text = result.get("text", "")
    note_length = result.get("note_length", 0)
    truncated = result.get("truncated", False)

    parts = [backend_info, ""]

    if truncated:
        parts.append(f"**Note (truncated, original length: {note_length} chars):**")
    else:
        parts.append(f"**Note {note_id} (subject_id: {subject_id}):**")

    parts.append(text)

    if truncated:
        parts.append("\n[...truncated...]")

    return "\n".join(parts)


def _serialize_list_patient_notes_result(result: dict[str, Any]) -> str:
    """Serialize list_patient_notes result to MCP string."""
    backend_info = result.get("backend_info", "")
    subject_id = result.get("subject_id", "")
    notes = result.get("notes", {})

    if not notes or all(df.empty for df in notes.values()):
        return (
            f"{backend_info}\n**No notes found** for subject_id {subject_id}.\n\n"
            "**Tip:** Verify the subject_id exists in the related MIMIC-IV dataset."
        )

    output_parts = [
        backend_info,
        f"**Notes for subject_id {subject_id}:**",
    ]

    for table, df in notes.items():
        if not df.empty:
            output_parts.append(
                f"\n**{table.upper()} NOTES:**\n{df.to_string(index=False)}"
            )

    output_parts.append(
        "\n**Tip:** Use `get_note(note_id)` to retrieve full text of a specific note."
    )

    return "\n".join(output_parts)


# ==========================================
# MCP TOOLS - Thin adapters to tool classes
# ==========================================


@mcp.tool()
def list_datasets() -> str:
    """📋 List all available datasets and their status.

    Returns:
        A formatted string listing available datasets, indicating which one is active,
        and showing availability of local database and BigQuery support.
    """
    try:
        tool = ToolRegistry.get("list_datasets")
        dataset = DatasetRegistry.get_active()
        result = tool.invoke(dataset, ListDatasetsInput())
        return _serialize_datasets_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
def set_dataset(dataset_name: str) -> str:
    """🔄 Switch the active dataset.

    Args:
        dataset_name: The name of the dataset to switch to (e.g., 'mimic-iv-demo').

    Returns:
        Confirmation message with supported tools snapshot, or error if not found.
    """
    try:
        # Check if target dataset exists before switching
        target_dataset_def = DatasetRegistry.get(dataset_name.lower())

        tool = ToolRegistry.get("set_dataset")
        dataset = DatasetRegistry.get_active()
        result = tool.invoke(dataset, SetDatasetInput(dataset_name=dataset_name))
        output = _serialize_set_dataset_result(result)

        # Append supported tools snapshot if dataset is valid
        if target_dataset_def is not None:
            output += _tool_selector.get_supported_tools_snapshot(
                target_dataset_def, _MCP_TOOL_NAMES
            )

        return output
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
@require_oauth2
def get_database_schema() -> str:
    """📚 Discover what data is available in the database.

    **When to use:** Start here to understand what tables exist.

    Returns:
        List of all available tables in the database with current backend info.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    compat_result = _tool_selector.check_compatibility("get_database_schema", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("get_database_schema")
        result = tool.invoke(dataset, GetDatabaseSchemaInput())
        return _serialize_schema_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
@require_oauth2
def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """🔍 Explore a specific table's structure and see sample data.

    **When to use:** After identifying relevant tables from get_database_schema().

    Args:
        table_name: Exact table name (case-sensitive).
        show_sample: Whether to include sample rows (default: True).

    Returns:
        Table structure with column names, types, and sample data.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    compat_result = _tool_selector.check_compatibility("get_table_info", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("get_table_info")
        result = tool.invoke(
            dataset, GetTableInfoInput(table_name=table_name, show_sample=show_sample)
        )
        return _serialize_table_info_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
@require_oauth2
def execute_query(sql_query: str) -> str:
    """🚀 Execute SQL queries to analyze data.

    **Recommended workflow:**
    1. Use get_database_schema() to list tables
    2. Use get_table_info() to examine structure
    3. Write your SQL query with exact names

    Args:
        sql_query: Your SQL SELECT query (SELECT only).

    Returns:
        Query results or helpful error messages.
    """
    dataset = DatasetRegistry.get_active()

    # Proactive capability check
    compat_result = _tool_selector.check_compatibility("execute_query", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("execute_query")
        result = tool.invoke(dataset, ExecuteQueryInput(sql_query=sql_query))
        # Result is a DataFrame - serialize it
        return serialize_for_mcp(result)
    except M4Error as e:
        return f"**Error:** {e}"


# ==========================================
# CLINICAL NOTES TOOLS
# ==========================================


@mcp.tool()
@require_oauth2
def search_notes(
    query: str,
    note_type: str = "all",
    limit: int = 5,
    snippet_length: int = 300,
) -> str:
    """🔍 Search clinical notes by keyword.

    Returns snippets around matches to prevent context overflow.
    Use get_note() to retrieve full text of specific notes.

    **Note types:** 'discharge' (summaries), 'radiology' (reports), or 'all'

    Args:
        query: Search term to find in notes.
        note_type: Type of notes to search ('discharge', 'radiology', or 'all').
        limit: Maximum number of results per note type (default: 5).
        snippet_length: Characters of context around matches (default: 300).

    Returns:
        Matching snippets with note IDs for follow-up retrieval.
    """
    dataset = DatasetRegistry.get_active()

    compat_result = _tool_selector.check_compatibility("search_notes", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("search_notes")
        result = tool.invoke(
            dataset,
            SearchNotesInput(
                query=query,
                note_type=note_type,
                limit=limit,
                snippet_length=snippet_length,
            ),
        )
        return _serialize_search_notes_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
@require_oauth2
def get_note(note_id: str, max_length: int | None = None) -> str:
    """📄 Retrieve full text of a specific clinical note.

    **Warning:** Clinical notes can be very long. Consider using
    search_notes() first to find relevant notes, or use max_length
    to truncate output.

    Args:
        note_id: The note ID (e.g., from search_notes or list_patient_notes).
        max_length: Optional maximum characters to return (truncates if exceeded).

    Returns:
        Full note text, or truncated version if max_length specified.
    """
    dataset = DatasetRegistry.get_active()

    compat_result = _tool_selector.check_compatibility("get_note", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("get_note")
        result = tool.invoke(
            dataset,
            GetNoteInput(note_id=note_id, max_length=max_length),
        )
        return _serialize_get_note_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


@mcp.tool()
@require_oauth2
def list_patient_notes(
    subject_id: int,
    note_type: str = "all",
    limit: int = 20,
) -> str:
    """📋 List available clinical notes for a patient.

    Returns note metadata (IDs, types, lengths) without full text.
    Use get_note(note_id) to retrieve specific notes.

    **Cross-dataset tip:** Get subject_id from MIMIC-IV queries, then
    use it here to find related clinical notes.

    Args:
        subject_id: Patient identifier (same as in MIMIC-IV).
        note_type: Type of notes to list ('discharge', 'radiology', or 'all').
        limit: Maximum notes to return (default: 20).

    Returns:
        List of available notes with metadata for the patient.
    """
    dataset = DatasetRegistry.get_active()

    compat_result = _tool_selector.check_compatibility("list_patient_notes", dataset)
    if not compat_result.compatible:
        return compat_result.error_message

    try:
        tool = ToolRegistry.get("list_patient_notes")
        result = tool.invoke(
            dataset,
            ListPatientNotesInput(
                subject_id=subject_id,
                note_type=note_type,
                limit=limit,
            ),
        )
        return _serialize_list_patient_notes_result(result)
    except M4Error as e:
        return f"**Error:** {e}"


def main():
    """Main entry point for MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
