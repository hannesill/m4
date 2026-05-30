"""M4 Python API for direct access to clinical data tools.

This module provides a clean Python API for code execution environments
like Claude Code. Functions delegate to the same tool classes used by
the MCP server, ensuring consistent behavior across interfaces.

Unlike the MCP server, this API returns native Python types:
- execute_query() returns pd.DataFrame
- get_schema() returns dict with tables list
- get_table_info() returns dict with schema DataFrame
- etc.

Example:
    from m4 import M4Client, execute_query, get_schema
    import pandas as pd

    client = M4Client(dataset="mimic-iv")
    schema = client.schema()  # Returns dict with 'tables' list
    print(schema['tables'])

    df = execute_query(
        "SELECT COUNT(*) FROM mimiciv_hosp.patients",
        dataset="mimic-iv",
    )
    print(df)  # DataFrame

All queries use canonical schema.table names (e.g., mimiciv_hosp.patients)
that work on both DuckDB and BigQuery backends.
"""

import os
from pathlib import Path
from typing import Any

import pandas as pd

from m4.client import M4Client
from m4.config import _ensure_custom_datasets_loaded, get_bigquery_project_id
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError, M4Error, ModalityError, QueryError
from m4.core.telemetry import set_interface
from m4.core.tools import init_tools

# Initialize tools on module import
init_tools()
set_interface("python_api")

# Re-export exceptions for convenience
__all__ = [
    "DatasetError",
    "M4Client",
    "M4Error",
    "ModalityError",
    "QueryError",
    "execute_query",
    "get_active_dataset",
    "get_capabilities",
    "get_note",
    "get_schema",
    "get_table_info",
    "get_telemetry_path",
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
        List of dataset names that can be used with M4Client(dataset=...).

    Example:
        >>> list_datasets()
        ['mimic-iv-demo', 'mimic-iv', 'mimic-iv-note', 'eicu']
    """
    _ensure_custom_datasets_loaded()
    return [ds.name for ds in DatasetRegistry.list_all()]


def set_dataset(name: str) -> str:
    """Deprecated compatibility shim for removed global dataset state."""
    raise DatasetError(
        f"set_dataset({name!r}) is no longer supported because M4 no longer keeps "
        "a global active dataset. Use M4Client(dataset='mimic-iv') or pass "
        "dataset='mimic-iv' to convenience functions such as execute_query(...)."
    )


def get_active_dataset() -> str:
    """Deprecated compatibility shim for removed global dataset state."""
    raise DatasetError(
        "get_active_dataset() is no longer supported because M4 no longer keeps "
        "a global active dataset. Pass dataset explicitly, for example "
        "M4Client(dataset='mimic-iv') or execute_query(sql, dataset='mimic-iv')."
    )


def get_capabilities() -> dict[str, Any]:
    """Return the stable M4 capability manifest."""
    from m4.services.capabilities import build_capabilities_manifest

    return build_capabilities_manifest()


def _client(dataset: str, backend: str | None = None) -> M4Client:
    path_disclosure = os.getenv("M4_PATH_DISCLOSURE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
        "paths",
    }
    return M4Client(
        dataset=dataset,
        backend=backend,
        interface="python_api",
        study_id=os.getenv("M4_STUDY_ID"),
        session_id=os.getenv("M4_SESSION_ID"),
        actor=os.getenv("M4_ACTOR"),
        project_id=get_bigquery_project_id(),
        db_path=os.getenv("M4_DB_PATH"),
        path_disclosure=path_disclosure,
    )


# =============================================================================
# Tabular Data Tools
# =============================================================================


def get_schema(dataset: str, backend: str | None = None) -> dict[str, Any]:
    """Get database schema information for a dataset.

    Returns:
        dict with:
            - backend_info: str - Backend description
            - tables: list[str] - List of table names

    Example:
        >>> schema = get_schema(dataset="mimic-iv")
        >>> print(schema['tables'])
        ['admissions', 'diagnoses_icd', 'patients', ...]
    """
    return _client(dataset, backend).schema()


def get_table_info(
    table_name: str,
    *,
    dataset: str,
    backend: str | None = None,
    show_sample: bool = True,
) -> dict[str, Any]:
    """Get column information and sample data for a table.

    Args:
        table_name: Name of the table to inspect.
        show_sample: If True, include sample rows (default: True).

    Returns:
        dict with:
            - backend_info: str - Backend description
            - table_name: str - Table name
            - schema: pd.DataFrame - Column information
            - sample: pd.DataFrame | None - Sample rows if requested

    Raises:
        QueryError: If table doesn't exist.

    Example:
        >>> info = get_table_info("patients")
        >>> print(info['schema'])  # DataFrame with column info
        >>> print(info['sample'])  # DataFrame with sample rows
    """
    return _client(dataset, backend).table_info(table_name, show_sample=show_sample)


def execute_query(
    sql: str,
    *,
    dataset: str,
    backend: str | None = None,
) -> pd.DataFrame:
    """Execute a SQL SELECT query against a dataset.

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
    return _client(dataset, backend).query(sql)


# =============================================================================
# Clinical Notes Tools
# =============================================================================


def search_notes(
    query: str,
    *,
    dataset: str,
    backend: str | None = None,
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
        ModalityError: If dataset doesn't support notes.
        QueryError: If note_type is invalid.

    Example:
        >>> results = search_notes("pneumonia", dataset="mimic-iv-note", limit=3)
        >>> for note_type, df in results['results'].items():
        ...     print(f"{note_type}: {len(df)} matches")
    """
    return _client(dataset, backend).search_notes(
        query=query,
        note_type=note_type,
        limit=limit,
        snippet_length=snippet_length,
    )


def get_note(
    note_id: str,
    *,
    dataset: str,
    backend: str | None = None,
    max_length: int | None = None,
) -> dict[str, Any]:
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
        ModalityError: If dataset doesn't support notes.
        QueryError: If note not found.

    Example:
        >>> note = get_note("10000032_DS-1")
        >>> print(note['text'][:500])
    """
    return _client(dataset, backend).get_note(note_id=note_id, max_length=max_length)


def list_patient_notes(
    subject_id: int,
    *,
    dataset: str,
    backend: str | None = None,
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
        ModalityError: If dataset doesn't support notes.
        QueryError: If note_type is invalid.

    Example:
        >>> notes = list_patient_notes(10000032)
        >>> for note_type, df in notes['notes'].items():
        ...     print(f"{note_type}: {len(df)} notes")
    """
    return _client(dataset, backend).list_patient_notes(
        subject_id=subject_id,
        note_type=note_type,
        limit=limit,
    )


# =============================================================================
# Telemetry
# =============================================================================


def get_telemetry_path() -> Path:
    """Return the path to the telemetry JSONL file.

    This file contains one JSON record per line, with each record
    representing a tool invocation (see ToolCallRecord for schema).
    External systems can read this file to build provenance trails.

    Returns:
        Path to the tool_calls.jsonl file (may not exist if no
        calls have been made yet, or if M4_TELEMETRY=off).
    """
    from m4.config import get_telemetry_dir
    from m4.core.telemetry import TELEMETRY_FILENAME

    event_log = os.environ.get("M4_EVENT_LOG")
    if event_log:
        return Path(event_log).expanduser()

    return get_telemetry_dir() / TELEMETRY_FILENAME
