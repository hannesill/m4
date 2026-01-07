"""Clinical notes tools for retrieving and searching text data.

This module provides specialized tools for clinical notes that prevent
context overflow by returning snippets instead of full text by default.

Tools:
- search_notes: Full-text search with result snippets
- get_note: Retrieve a single note by ID
- list_patient_notes: List available notes for a patient (metadata only)

Architecture Note:
    Tools return native Python types. The MCP server serializes these
    for the protocol; the Python API receives them directly.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from m4.core.backends import get_backend
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import QueryError
from m4.core.tools.base import ToolInput


class NoteType(str, Enum):
    """Types of clinical notes available."""

    DISCHARGE = "discharge"
    RADIOLOGY = "radiology"
    ALL = "all"


# Input models
@dataclass
class SearchNotesInput(ToolInput):
    """Input for search_notes tool."""

    query: str
    note_type: str = "all"  # discharge, radiology, or all
    limit: int = 5
    snippet_length: int = 300


@dataclass
class GetNoteInput(ToolInput):
    """Input for get_note tool."""

    note_id: str
    max_length: int | None = None  # Optional truncation


@dataclass
class ListPatientNotesInput(ToolInput):
    """Input for list_patient_notes tool."""

    subject_id: int
    note_type: str = "all"  # discharge, radiology, or all
    limit: int = 20


# Tool implementations
class SearchNotesTool:
    """Tool for full-text search across clinical notes.

    Returns snippets around matches to prevent context overflow.
    Use get_note() to retrieve full text of specific notes.

    Returns:
        dict with search results by table, each containing a DataFrame
    """

    name = "search_notes"
    description = (
        "Search clinical notes by keyword. Returns snippets, not full text. "
        "Use get_note() to retrieve full content of a specific note."
    )
    input_model = SearchNotesInput

    required_modalities: frozenset[Modality] = frozenset({Modality.NOTES})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: SearchNotesInput
    ) -> dict[str, Any]:
        """Search notes and return snippets around matches.

        Returns:
            dict with:
                - backend_info: str - Backend description
                - query: str - Search term used
                - snippet_length: int - Snippet length
                - results: dict[str, pd.DataFrame] - Results by table type

        Raises:
            QueryError: If note_type is invalid
        """
        backend = get_backend()

        # Determine which tables to search
        tables_to_search = self._get_tables_for_type(params.note_type)

        if not tables_to_search:
            raise QueryError(
                f"Invalid note_type '{params.note_type}'. "
                "Use 'discharge', 'radiology', or 'all'."
            )

        results: dict[str, pd.DataFrame] = {}
        search_term = params.query.replace("'", "''")  # Escape single quotes

        for table in tables_to_search:
            # Build search query with snippet extraction
            # Using LIKE for basic search - could be enhanced with full-text search
            sql = f"""
                SELECT
                    note_id,
                    subject_id,
                    CASE
                        WHEN POSITION(LOWER('{search_term}') IN LOWER(text)) > 0 THEN
                            SUBSTRING(
                                text,
                                GREATEST(1, POSITION(LOWER('{search_term}') IN LOWER(text)) - {params.snippet_length // 2}),
                                {params.snippet_length}
                            )
                        ELSE LEFT(text, {params.snippet_length})
                    END as snippet,
                    LENGTH(text) as note_length
                FROM {table}
                WHERE LOWER(text) LIKE '%{search_term.lower()}%'
                LIMIT {params.limit}
            """

            result = backend.execute_query(sql, dataset)
            if result.success and result.dataframe is not None:
                results[table] = result.dataframe

        return {
            "backend_info": backend.get_backend_info(dataset),
            "query": params.query,
            "snippet_length": params.snippet_length,
            "results": results,
        }

    def _get_tables_for_type(self, note_type: str) -> list[str]:
        """Get table names for a note type."""
        note_type = note_type.lower()
        if note_type == "discharge":
            return ["discharge"]
        elif note_type == "radiology":
            return ["radiology"]
        elif note_type == "all":
            return ["discharge", "radiology"]
        return []

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True


class GetNoteTool:
    """Tool for retrieving a single clinical note by ID.

    Returns the full note text. Use with caution as notes can be long.

    Returns:
        dict with note metadata and full text
    """

    name = "get_note"
    description = (
        "Retrieve full text of a specific clinical note by note_id. "
        "Notes can be very long - consider using search_notes() first "
        "to find relevant notes."
    )
    input_model = GetNoteInput

    required_modalities: frozenset[Modality] = frozenset({Modality.NOTES})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetNoteInput
    ) -> dict[str, Any]:
        """Retrieve a single note by ID.

        Returns:
            dict with:
                - backend_info: str - Backend description
                - note_id: str - Note identifier
                - subject_id: int - Patient ID
                - text: str - Full note text (possibly truncated)
                - note_length: int - Original note length
                - truncated: bool - Whether text was truncated

        Raises:
            QueryError: If note not found
        """
        backend = get_backend()

        # Note IDs contain the note type (e.g., "10000032_DS-1" for discharge)
        note_id = params.note_id.replace("'", "''")

        # Try both tables since we may not know which one contains the note
        for table in ["discharge", "radiology"]:
            sql = f"""
                SELECT
                    note_id,
                    subject_id,
                    text,
                    LENGTH(text) as note_length
                FROM {table}
                WHERE note_id = '{note_id}'
                LIMIT 1
            """

            result = backend.execute_query(sql, dataset)
            if (
                result.success
                and result.dataframe is not None
                and not result.dataframe.empty
            ):
                row = result.dataframe.iloc[0]
                text = str(row["text"])
                note_length = int(row["note_length"])
                truncated = False

                # Optionally truncate if max_length specified
                if params.max_length and len(text) > params.max_length:
                    text = text[: params.max_length]
                    truncated = True

                return {
                    "backend_info": backend.get_backend_info(dataset),
                    "note_id": str(row["note_id"]),
                    "subject_id": int(row["subject_id"]),
                    "text": text,
                    "note_length": note_length,
                    "truncated": truncated,
                }

        raise QueryError(
            f"Note '{params.note_id}' not found. "
            "Use list_patient_notes(subject_id) or search_notes(query) "
            "to find valid note IDs."
        )

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True


class ListPatientNotesTool:
    """Tool for listing available notes for a patient.

    Returns metadata only (note IDs, types, lengths) - not full text.
    Use this to discover what notes exist before retrieving them.

    Returns:
        dict with notes metadata by table type
    """

    name = "list_patient_notes"
    description = (
        "List available clinical notes for a patient by subject_id. "
        "Returns note metadata (IDs, types, lengths) without full text. "
        "Use get_note(note_id) to retrieve specific notes."
    )
    input_model = ListPatientNotesInput

    required_modalities: frozenset[Modality] = frozenset({Modality.NOTES})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: ListPatientNotesInput
    ) -> dict[str, Any]:
        """List notes for a patient without returning full text.

        Returns:
            dict with:
                - backend_info: str - Backend description
                - subject_id: int - Patient ID
                - notes: dict[str, pd.DataFrame] - Notes metadata by table type

        Raises:
            QueryError: If note_type is invalid
        """
        backend = get_backend()

        tables_to_query = self._get_tables_for_type(params.note_type)

        if not tables_to_query:
            raise QueryError(
                f"Invalid note_type '{params.note_type}'. "
                "Use 'discharge', 'radiology', or 'all'."
            )

        notes: dict[str, pd.DataFrame] = {}

        for table in tables_to_query:
            # Query for metadata only - explicitly exclude full text
            sql = f"""
                SELECT
                    note_id,
                    subject_id,
                    '{table}' as note_type,
                    LENGTH(text) as note_length,
                    LEFT(text, 100) as preview
                FROM {table}
                WHERE subject_id = {params.subject_id}
                LIMIT {params.limit}
            """

            result = backend.execute_query(sql, dataset)
            if result.success and result.dataframe is not None:
                notes[table] = result.dataframe

        return {
            "backend_info": backend.get_backend_info(dataset),
            "subject_id": params.subject_id,
            "notes": notes,
        }

    def _get_tables_for_type(self, note_type: str) -> list[str]:
        """Get table names for a note type."""
        note_type = note_type.lower()
        if note_type == "discharge":
            return ["discharge"]
        elif note_type == "radiology":
            return ["radiology"]
        elif note_type == "all":
            return ["discharge", "radiology"]
        return []

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True
