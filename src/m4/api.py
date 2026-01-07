"""M4 Python API for direct access to clinical data tools.

This module provides a clean Python API for code execution environments
like Claude Code. Functions delegate to the same tool classes used by
the MCP server, ensuring consistent behavior across interfaces.

Example:
    from m4 import execute_query, set_dataset, get_schema

    set_dataset("mimic-iv")
    print(get_schema())

    result = execute_query("SELECT COUNT(*) FROM patients")
    print(result)

All functions work with the currently active dataset. Use set_dataset()
to switch between datasets.
"""

from m4.config import get_active_dataset as _get_active_dataset
from m4.config import set_active_dataset as _set_active_dataset
from m4.core.datasets import DatasetRegistry
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


class M4Error(Exception):
    """Base exception for M4 API errors."""

    pass


class DatasetError(M4Error):
    """Raised when there's an issue with dataset configuration."""

    pass


class QueryError(M4Error):
    """Raised when a query fails to execute."""

    pass


class ModalityError(M4Error):
    """Raised when a tool is incompatible with the active dataset."""

    pass


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


def get_schema() -> str:
    """List all tables available in the active dataset.

    Returns:
        Formatted list of table names.

    Example:
        >>> set_dataset("mimic-iv")
        >>> print(get_schema())
        admissions
        diagnoses_icd
        patients
        ...
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_database_schema")
    return tool.invoke(dataset, GetDatabaseSchemaInput()).result


def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """Get column information and sample data for a table.

    Args:
        table_name: Name of the table to inspect.
        show_sample: If True, include sample rows (default: True).

    Returns:
        Formatted table schema and optional sample data.

    Example:
        >>> print(get_table_info("patients"))
        Column Information:
        subject_id | INTEGER | ...
        gender | VARCHAR | ...

        Sample Data (first 3 rows):
        ...
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_table_info")
    return tool.invoke(
        dataset, GetTableInfoInput(table_name=table_name, show_sample=show_sample)
    ).result


def execute_query(sql: str) -> str:
    """Execute a SQL SELECT query against the active dataset.

    Args:
        sql: SQL SELECT query string.

    Returns:
        Query results as formatted string.

    Raises:
        QueryError: If query is unsafe or execution fails.

    Example:
        >>> result = execute_query("SELECT gender, COUNT(*) FROM patients GROUP BY gender")
        >>> print(result)
    """
    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("execute_query")
    result = tool.invoke(dataset, ExecuteQueryInput(sql_query=sql)).result

    # Convert security errors to exceptions for Python API
    if result.startswith("**Security Error:**"):
        raise QueryError(result.replace("**Security Error:** ", ""))

    return result


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
) -> str:
    """Search clinical notes by keyword, returning snippets.

    Args:
        query: Search term to find in notes.
        note_type: Type of notes - 'discharge', 'radiology', or 'all'.
        limit: Maximum results per note type (default: 5).
        snippet_length: Characters of context around matches (default: 300).

    Returns:
        Matching snippets with note IDs.

    Raises:
        ModalityError: If active dataset doesn't support notes.

    Example:
        >>> set_dataset("mimic-iv-note")
        >>> results = search_notes("pneumonia", limit=3)
        >>> print(results)
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
    ).result


def get_note(note_id: str, max_length: int | None = None) -> str:
    """Retrieve full text of a clinical note by ID.

    Args:
        note_id: The note ID (e.g., from search_notes results).
        max_length: Optional maximum characters to return.

    Returns:
        Full note text (or truncated if max_length specified).

    Raises:
        ModalityError: If active dataset doesn't support notes.

    Example:
        >>> note = get_note("10000032_DS-1")
        >>> print(note[:500])
    """
    _check_notes_compatibility("get_note")

    dataset = DatasetRegistry.get_active()
    tool = ToolRegistry.get("get_note")
    return tool.invoke(
        dataset,
        GetNoteInput(note_id=note_id, max_length=max_length),
    ).result


def list_patient_notes(
    subject_id: int,
    note_type: str = "all",
    limit: int = 20,
) -> str:
    """List available clinical notes for a patient (metadata only).

    Args:
        subject_id: Patient identifier.
        note_type: Type of notes - 'discharge', 'radiology', or 'all'.
        limit: Maximum notes to return (default: 20).

    Returns:
        List of note metadata (IDs, types, lengths) without full text.

    Raises:
        ModalityError: If active dataset doesn't support notes.

    Example:
        >>> notes = list_patient_notes(10000032)
        >>> print(notes)
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
    ).result
