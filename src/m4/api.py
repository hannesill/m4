"""M4 Python API for direct access to clinical data tools.

This module provides a clean Python API for code execution environments
like Claude Code. Functions delegate to the same tool classes used by
the MCP server, ensuring consistent behavior across interfaces.

Unlike the MCP server, this API returns native Python types:
- execute_query() returns pd.DataFrame
- get_schema() returns dict with tables dict (name → description)
- get_table_info() returns dict with columns DataFrame and DDL
- etc.

Example:
    from m4 import execute_query, set_dataset, get_schema
    import pandas as pd

    set_dataset("mimic-iv")
    schema = get_schema()  # Returns dict with 'tables' dict
    for table, desc in schema['tables'].items():
        print(f"{table} -- {desc}")

    df = execute_query("SELECT COUNT(*) FROM mimiciv_hosp.patients")
    print(df)  # DataFrame

All queries use canonical schema.table names (e.g., mimiciv_hosp.patients)
that work on both DuckDB and BigQuery backends. Use set_dataset()
to switch between datasets.
"""

from typing import Any

import pandas as pd

from m4.config import get_active_dataset as _get_active_dataset
from m4.config import set_active_dataset as _set_active_dataset
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError, M4Error, ModalityError, QueryError
from m4.core.tools import ToolRegistry, ToolSelector, init_tools
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

# Initialize tools on module import
init_tools()

# Tool selector for compatibility checking
_tool_selector = ToolSelector()

# Re-export exceptions for convenience
__all__ = [
    "DatasetError",
    "M4Error",
    "ModalityError",
    "QueryError",
    "execute_query",
    "get_active_dataset",
    "get_note",
    "get_schema",
    "get_table_info",
    "list_datasets",
    "list_patient_notes",
    "search_notes",
    "set_dataset",
]


# =============================================================================
# Dataset Management
# =============================================================================


def list_datasets() -> list[str]:
    """List all available datasets.

    Returns:
        List of dataset names that can be used with set_dataset().

    Example:
        >>> list_datasets()
        ['mimic-iv', 'mimic-iv-note', 'eicu']
    """
    return [ds.name for ds in DatasetRegistry.list_all()]


def set_dataset(name: str) -> str:
    """Set the active dataset for subsequent queries.

    Args:
        name: Dataset name (e.g., 'mimic-iv', 'eicu')

    Returns:
        Confirmation message with dataset info.

    Raises:
        DatasetError: If dataset doesn't exist.

    Example:
        >>> set_dataset("mimic-iv")
        'Active dataset: mimic-iv (modalities: TABULAR)'
    """
    try:
        _set_active_dataset(name)
        dataset = DatasetRegistry.get(name)
        if not dataset:
            raise ValueError(f"Dataset '{name}' not found")
        modalities = ", ".join(m.name for m in dataset.modalities)
        return f"Active dataset: {name} (modalities: {modalities})"
    except ValueError as e:
        available = ", ".join(list_datasets())
        raise DatasetError(f"{e}. Available datasets: {available}") from e


def get_active_dataset() -> str:
    """Get the name of the currently active dataset.

    Returns:
        Name of the active dataset.

    Raises:
        DatasetError: If no dataset is active.
    """
    try:
        return _get_active_dataset()
    except ValueError as e:
        raise DatasetError(str(e)) from e


# =============================================================================
# Tabular Data Tools
# =============================================================================


def get_schema(include_ddl: bool = False) -> dict[str, Any]:
    """Get database schema information for the active dataset.

    Args:
        include_ddl: If True, include CREATE TABLE DDL for every table (default: False).

    Returns:
        dict with:
            - backend: str - Backend name ('duckdb' or 'bigquery')
            - dataset: str - Active dataset name
            - tables: dict[str, str] - Table name → description
            - ddl: str - Combined DDL for all tables (only when include_ddl=True)

    Example:
        >>> set_dataset("mimic-iv")
        >>> schema = get_schema()
        >>> for table, desc in schema['tables'].items():
        ...     print(f"{table} -- {desc}")
        >>> # Get full DDL in one call
        >>> schema = get_schema(include_ddl=True)
        >>> print(schema['ddl'])
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_database_schema")
    return tool.invoke(dataset, GetDatabaseSchemaInput(include_ddl=include_ddl))


def get_table_info(table_name: str, show_sample: bool = True) -> dict[str, Any]:
    """Get column information and sample data for a table.

    Args:
        table_name: Name of the table to inspect.
        show_sample: If True, include sample rows (default: True).

    Returns:
        dict with:
            - table_name: str - Table name
            - columns: pd.DataFrame - Normalized [column_name, data_type, nullable]
            - ddl: str - CREATE TABLE DDL string
            - sample: pd.DataFrame | None - Sample rows if requested

    Raises:
        QueryError: If table doesn't exist.

    Example:
        >>> info = get_table_info("mimiciv_hosp.patients")
        >>> print(info['ddl'])      # CREATE TABLE statement
        >>> print(info['columns'])  # DataFrame with column info
        >>> print(info['sample'])   # DataFrame with sample rows
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_table_info")
    return tool.invoke(
        dataset, GetTableInfoInput(table_name=table_name, show_sample=show_sample)
    )


def execute_query(sql: str) -> pd.DataFrame:
    """Execute a SQL SELECT query against the active dataset.

    Args:
        sql: SQL SELECT query string.

    Returns:
        pd.DataFrame with query results.

    Raises:
        SecurityError: If query violates security constraints.
        QueryError: If query execution fails.

    Example:
        >>> df = execute_query("SELECT gender, COUNT(*) FROM mimiciv_hosp.patients GROUP BY gender")
        >>> print(df)
           gender  count_star()
        0       M            55
        1       F            45
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("execute_query")
    return tool.invoke(dataset, ExecuteQueryInput(sql_query=sql))


# =============================================================================
# Clinical Notes Tools
# =============================================================================


def _check_notes_compatibility(tool_name: str) -> None:
    """Check that active dataset supports notes tools."""
    dataset = DatasetRegistry.get_active()
    result = _tool_selector.check_compatibility(tool_name, dataset)
    if not result.compatible:
        raise ModalityError(
            f"Dataset '{dataset.name}' does not support clinical notes. "
            f"Available modalities: {', '.join(m.name for m in dataset.modalities)}. "
            f"Use a dataset with NOTES modality (e.g., 'mimic-iv-note')."
        )


def search_notes(
    query: str,
    note_type: str = "all",
    limit: int = 5,
    snippet_length: int = 300,
) -> dict[str, Any]:
    """Search clinical notes by keyword, returning snippets.

    Args:
        query: Search term to find in notes.
        note_type: Type of notes - 'discharge', 'radiology', or 'all'.
        limit: Maximum results per note type (default: 5).
        snippet_length: Characters of context around matches (default: 300).

    Returns:
        dict with:
            - backend_info: str - Backend description
            - query: str - Search term used
            - snippet_length: int - Snippet length
            - results: dict[str, pd.DataFrame] - Results by note type

    Raises:
        ModalityError: If active dataset doesn't support notes.
        QueryError: If note_type is invalid.

    Example:
        >>> set_dataset("mimic-iv-note")
        >>> results = search_notes("pneumonia", limit=3)
        >>> for note_type, df in results['results'].items():
        ...     print(f"{note_type}: {len(df)} matches")
    """
    _check_notes_compatibility("search_notes")

    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("search_notes")
    return tool.invoke(
        dataset,
        SearchNotesInput(
            query=query,
            note_type=note_type,
            limit=limit,
            snippet_length=snippet_length,
        ),
    )


def get_note(note_id: str, max_length: int | None = None) -> dict[str, Any]:
    """Retrieve full text of a clinical note by ID.

    Args:
        note_id: The note ID (e.g., from search_notes results).
        max_length: Optional maximum characters to return.

    Returns:
        dict with:
            - backend_info: str - Backend description
            - note_id: str - Note identifier
            - subject_id: int - Patient ID
            - text: str - Full note text (possibly truncated)
            - note_length: int - Original note length
            - truncated: bool - Whether text was truncated

    Raises:
        ModalityError: If active dataset doesn't support notes.
        QueryError: If note not found.

    Example:
        >>> note = get_note("10000032_DS-1")
        >>> print(note['text'][:500])
    """
    _check_notes_compatibility("get_note")

    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_note")
    return tool.invoke(
        dataset,
        GetNoteInput(note_id=note_id, max_length=max_length),
    )


def list_patient_notes(
    subject_id: int,
    note_type: str = "all",
    limit: int = 20,
) -> dict[str, Any]:
    """List available clinical notes for a patient (metadata only).

    Args:
        subject_id: Patient identifier.
        note_type: Type of notes - 'discharge', 'radiology', or 'all'.
        limit: Maximum notes to return (default: 20).

    Returns:
        dict with:
            - backend_info: str - Backend description
            - subject_id: int - Patient ID
            - notes: dict[str, pd.DataFrame] - Note metadata by type

    Raises:
        ModalityError: If active dataset doesn't support notes.
        QueryError: If note_type is invalid.

    Example:
        >>> notes = list_patient_notes(10000032)
        >>> for note_type, df in notes['notes'].items():
        ...     print(f"{note_type}: {len(df)} notes")
    """
    _check_notes_compatibility("list_patient_notes")

    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("list_patient_notes")
    return tool.invoke(
        dataset,
        ListPatientNotesInput(
            subject_id=subject_id,
            note_type=note_type,
            limit=limit,
        ),
    )
