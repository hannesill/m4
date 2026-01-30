"""Tests for clinical notes tools.

Tests cover:
- SearchNotesTool invoke, SQL generation, error handling, compatibility
- GetNoteTool invoke, truncation, error handling, compatibility
- ListPatientNotesTool invoke, SQL generation, error handling, compatibility
- _get_tables_for_type helper on SearchNotesTool
- Protocol conformance for all notes tools

Note: Tools return native types (dict, DataFrame) instead of ToolOutput.
      Tools raise exceptions for errors instead of returning error messages.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from m4.core.backends.base import QueryResult
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import QueryError
from m4.core.tools.notes import (
    GetNoteInput,
    GetNoteTool,
    ListPatientNotesInput,
    ListPatientNotesTool,
    SearchNotesInput,
    SearchNotesTool,
)


@pytest.fixture
def notes_dataset():
    """Dataset with NOTES modality."""
    return DatasetDefinition(
        name="test-notes",
        modalities=frozenset({Modality.NOTES}),
    )


@pytest.fixture
def tabular_only_dataset():
    """Dataset WITHOUT NOTES modality."""
    return DatasetDefinition(
        name="test-tabular-only",
        modalities=frozenset({Modality.TABULAR}),
    )


@pytest.fixture
def mock_backend():
    """Mock backend returning controlled QueryResults."""
    backend = MagicMock()
    backend.name = "duckdb"
    backend.get_backend_info.return_value = "Test backend"
    return backend


class TestSearchNotesTool:
    """Tests for SearchNotesTool functionality."""

    def test_invoke_returns_results(self, notes_dataset, mock_backend):
        """Test that invoke returns dict with expected keys."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "snippet": ["Patient presented with..."],
                "note_length": [5000],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="sepsis", note_type="discharge")
            result = tool.invoke(notes_dataset, params)

            assert "backend_info" in result
            assert "query" in result
            assert "snippet_length" in result
            assert "results" in result
            assert "mimiciv_note.discharge" in result["results"]

    def test_invoke_searches_all_tables_by_default(self, notes_dataset, mock_backend):
        """Test that default note_type='all' searches both tables."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "snippet": ["..."],
                "note_length": [500],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="sepsis")
            result = tool.invoke(notes_dataset, params)

            assert "mimiciv_note.discharge" in result["results"]
            assert "mimiciv_note.radiology" in result["results"]
            assert mock_backend.execute_query.call_count == 2

    def test_invoke_searches_single_table_when_specified(
        self, notes_dataset, mock_backend
    ):
        """Test that specifying note_type limits to one table."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "snippet": ["..."],
                "note_length": [500],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="sepsis", note_type="discharge")
            result = tool.invoke(notes_dataset, params)

            assert mock_backend.execute_query.call_count == 1
            assert "mimiciv_note.discharge" in result["results"]

    def test_invoke_invalid_note_type_raises(self, notes_dataset, mock_backend):
        """Test that an invalid note_type raises QueryError."""
        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="sepsis", note_type="invalid")

            with pytest.raises(QueryError, match="Invalid note_type"):
                tool.invoke(notes_dataset, params)

    def test_invoke_empty_results(self, notes_dataset, mock_backend):
        """Test invoke with no matching notes returns empty results."""
        empty_df = pd.DataFrame(
            columns=["note_id", "subject_id", "snippet", "note_length"]
        )
        # Empty DataFrame still counts as success, but empty DF is falsy
        # for the `result.dataframe is not None` check. However, an empty
        # DataFrame IS not None, so it will be added to results.
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="nonexistent_term_xyz")
            result = tool.invoke(notes_dataset, params)

            # Empty DataFrames with success still get added to results
            assert isinstance(result["results"], dict)

    def test_invoke_backend_error_collected_not_raised(
        self, notes_dataset, mock_backend
    ):
        """Test that backend errors are collected, not raised."""
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=None,
            error="Table does not exist",
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(query="sepsis")
            # Should NOT raise
            result = tool.invoke(notes_dataset, params)

            assert "errors" in result
            assert len(result["errors"]) == 2

    def test_invoke_sql_escapes_single_quotes(self, notes_dataset, mock_backend):
        """Test that single quotes in query are escaped."""
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=pd.DataFrame(
                columns=[
                    "note_id",
                    "subject_id",
                    "snippet",
                    "note_length",
                ]
            ),
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(
                query="patient's condition",
                note_type="discharge",
            )
            tool.invoke(notes_dataset, params)

            sql_arg = mock_backend.execute_query.call_args[0][0]
            assert "patient''s condition" in sql_arg

    def test_invoke_sql_contains_search_term_and_limit(
        self, notes_dataset, mock_backend
    ):
        """Test SQL contains the search term, limit, and snippet_length."""
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=pd.DataFrame(
                columns=[
                    "note_id",
                    "subject_id",
                    "snippet",
                    "note_length",
                ]
            ),
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = SearchNotesTool()
            params = SearchNotesInput(
                query="sepsis",
                limit=10,
                snippet_length=500,
                note_type="discharge",
            )
            tool.invoke(notes_dataset, params)

            sql_arg = mock_backend.execute_query.call_args[0][0]
            assert "sepsis" in sql_arg
            assert "LIMIT 10" in sql_arg
            assert "500" in sql_arg

    def test_compatibility_with_notes_dataset(self, notes_dataset):
        """Test tool is compatible with NOTES dataset."""
        tool = SearchNotesTool()
        assert tool.is_compatible(notes_dataset) is True

    def test_incompatibility_with_tabular_dataset(self, tabular_only_dataset):
        """Test tool is NOT compatible with TABULAR-only dataset."""
        tool = SearchNotesTool()
        assert tool.is_compatible(tabular_only_dataset) is False


class TestGetTablesForType:
    """Tests for SearchNotesTool._get_tables_for_type helper."""

    def test_discharge_returns_discharge_table(self):
        """Test discharge returns only the discharge table."""
        tool = SearchNotesTool()
        assert tool._get_tables_for_type("discharge") == ["mimiciv_note.discharge"]

    def test_radiology_returns_radiology_table(self):
        """Test radiology returns only the radiology table."""
        tool = SearchNotesTool()
        assert tool._get_tables_for_type("radiology") == ["mimiciv_note.radiology"]

    def test_all_returns_both_tables(self):
        """Test all returns both discharge and radiology tables."""
        tool = SearchNotesTool()
        result = tool._get_tables_for_type("all")
        assert result == [
            "mimiciv_note.discharge",
            "mimiciv_note.radiology",
        ]

    def test_invalid_returns_empty(self):
        """Test invalid note_type returns empty list."""
        tool = SearchNotesTool()
        assert tool._get_tables_for_type("invalid") == []

    def test_case_insensitive(self):
        """Test that note_type lookup is case insensitive."""
        tool = SearchNotesTool()
        assert tool._get_tables_for_type("DISCHARGE") == ["mimiciv_note.discharge"]


class TestGetNoteTool:
    """Tests for GetNoteTool functionality."""

    def test_invoke_finds_note_in_first_table(self, notes_dataset, mock_backend):
        """Test finding a note in the first table searched."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "text": ["Patient was admitted for..."],
                "note_length": [26],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_DS-1")
            result = tool.invoke(notes_dataset, params)

            assert result["note_id"] == "10001_DS-1"
            assert result["subject_id"] == 10001
            assert result["text"] == "Patient was admitted for..."
            assert result["note_length"] == 26
            assert result["truncated"] is False

    def test_invoke_finds_note_in_second_table(self, notes_dataset, mock_backend):
        """Test finding a note when first table is empty."""
        empty_df = pd.DataFrame(
            columns=["note_id", "subject_id", "text", "note_length"]
        )
        found_df = pd.DataFrame(
            {
                "note_id": ["10001_RD-1"],
                "subject_id": [10001],
                "text": ["Chest X-ray findings..."],
                "note_length": [22],
            }
        )
        mock_backend.execute_query.side_effect = [
            QueryResult(dataframe=empty_df, row_count=0),
            QueryResult(dataframe=found_df, row_count=1),
        ]

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_RD-1")
            result = tool.invoke(notes_dataset, params)

            assert result["note_id"] == "10001_RD-1"
            assert result["text"] == "Chest X-ray findings..."

    def test_invoke_note_not_found_raises(self, notes_dataset, mock_backend):
        """Test that missing note raises QueryError."""
        empty_df = pd.DataFrame(
            columns=["note_id", "subject_id", "text", "note_length"]
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="nonexistent")

            with pytest.raises(QueryError, match="not found"):
                tool.invoke(notes_dataset, params)

    def test_invoke_note_not_found_includes_backend_errors(
        self, notes_dataset, mock_backend
    ):
        """Test that backend errors are included in the raised error."""
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=None,
            error="Connection timeout",
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_DS-1")

            with pytest.raises(QueryError, match="Backend errors"):
                tool.invoke(notes_dataset, params)

    def test_invoke_truncates_with_max_length(self, notes_dataset, mock_backend):
        """Test that text is truncated when exceeding max_length."""
        long_text = "A" * 1000
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "text": [long_text],
                "note_length": [1000],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_DS-1", max_length=100)
            result = tool.invoke(notes_dataset, params)

            assert len(result["text"]) == 100
            assert result["truncated"] is True

    def test_invoke_no_truncation_when_under_max_length(
        self, notes_dataset, mock_backend
    ):
        """Test no truncation when text is shorter than max_length."""
        short_text = "A" * 50
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "text": [short_text],
                "note_length": [50],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_DS-1", max_length=100)
            result = tool.invoke(notes_dataset, params)

            assert len(result["text"]) == 50
            assert result["truncated"] is False

    def test_invoke_no_truncation_when_max_length_none(
        self, notes_dataset, mock_backend
    ):
        """Test full text returned when max_length is None."""
        long_text = "B" * 10000
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "text": [long_text],
                "note_length": [10000],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10001_DS-1", max_length=None)
            result = tool.invoke(notes_dataset, params)

            assert len(result["text"]) == 10000
            assert result["truncated"] is False

    def test_invoke_escapes_note_id_single_quotes(self, notes_dataset, mock_backend):
        """Test that single quotes in note_id are escaped."""
        empty_df = pd.DataFrame(
            columns=["note_id", "subject_id", "text", "note_length"]
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = GetNoteTool()
            params = GetNoteInput(note_id="10000032_DS-1'; DROP TABLE--")

            # Will raise QueryError because note not found, but we
            # check the SQL that was generated before that.
            with pytest.raises(QueryError):
                tool.invoke(notes_dataset, params)

            sql_arg = mock_backend.execute_query.call_args[0][0]
            assert "10000032_DS-1''; DROP TABLE--" in sql_arg

    def test_compatibility(self, notes_dataset, tabular_only_dataset):
        """Test compatibility with NOTES and TABULAR-only datasets."""
        tool = GetNoteTool()
        assert tool.is_compatible(notes_dataset) is True
        assert tool.is_compatible(tabular_only_dataset) is False


class TestListPatientNotesTool:
    """Tests for ListPatientNotesTool functionality."""

    def test_invoke_returns_notes_metadata(self, notes_dataset, mock_backend):
        """Test that invoke returns dict with expected keys."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "note_type": ["mimiciv_note.discharge"],
                "note_length": [5000],
                "preview": ["Patient presented with..."],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001, note_type="discharge")
            result = tool.invoke(notes_dataset, params)

            assert "backend_info" in result
            assert "subject_id" in result
            assert "notes" in result
            assert "mimiciv_note.discharge" in result["notes"]

    def test_invoke_queries_all_tables_by_default(self, notes_dataset, mock_backend):
        """Test that default note_type='all' queries both tables."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "note_type": ["mimiciv_note.discharge"],
                "note_length": [5000],
                "preview": ["..."],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001)
            tool.invoke(notes_dataset, params)

            assert mock_backend.execute_query.call_count == 2

    def test_invoke_queries_single_table_when_specified(
        self, notes_dataset, mock_backend
    ):
        """Test that specifying note_type limits to one table."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_RD-1"],
                "subject_id": [10001],
                "note_type": ["mimiciv_note.radiology"],
                "note_length": [800],
                "preview": ["Chest X-ray..."],
            }
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=df,
            row_count=1,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001, note_type="radiology")
            tool.invoke(notes_dataset, params)

            assert mock_backend.execute_query.call_count == 1

    def test_invoke_invalid_note_type_raises(self, notes_dataset, mock_backend):
        """Test that an invalid note_type raises QueryError."""
        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001, note_type="invalid")

            with pytest.raises(QueryError, match="Invalid note_type"):
                tool.invoke(notes_dataset, params)

    def test_invoke_empty_results(self, notes_dataset, mock_backend):
        """Test invoke when patient has no notes returns empty DFs."""
        empty_df = pd.DataFrame(
            columns=[
                "note_id",
                "subject_id",
                "note_type",
                "note_length",
                "preview",
            ]
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=99999)
            result = tool.invoke(notes_dataset, params)

            # Empty DataFrames with success still get added
            assert "mimiciv_note.discharge" in result["notes"]
            assert "mimiciv_note.radiology" in result["notes"]
            assert result["notes"]["mimiciv_note.discharge"].empty
            assert result["notes"]["mimiciv_note.radiology"].empty

    def test_invoke_backend_error_collected(self, notes_dataset, mock_backend):
        """Test that backend errors are collected in the response."""
        df = pd.DataFrame(
            {
                "note_id": ["10001_DS-1"],
                "subject_id": [10001],
                "note_type": ["mimiciv_note.discharge"],
                "note_length": [5000],
                "preview": ["..."],
            }
        )
        mock_backend.execute_query.side_effect = [
            QueryResult(dataframe=df, row_count=1),
            QueryResult(dataframe=None, error="Table not found"),
        ]

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001)
            result = tool.invoke(notes_dataset, params)

            assert "errors" in result
            assert len(result["errors"]) == 1

    def test_invoke_sql_uses_subject_id_and_limit(self, notes_dataset, mock_backend):
        """Test SQL contains subject_id and limit values."""
        empty_df = pd.DataFrame(
            columns=[
                "note_id",
                "subject_id",
                "note_type",
                "note_length",
                "preview",
            ]
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(
                subject_id=12345, limit=10, note_type="discharge"
            )
            tool.invoke(notes_dataset, params)

            sql_arg = mock_backend.execute_query.call_args[0][0]
            assert "subject_id = 12345" in sql_arg
            assert "LIMIT 10" in sql_arg

    def test_invoke_sql_selects_preview_not_full_text(
        self, notes_dataset, mock_backend
    ):
        """Test SQL uses LEFT(text, 100) for preview."""
        empty_df = pd.DataFrame(
            columns=[
                "note_id",
                "subject_id",
                "note_type",
                "note_length",
                "preview",
            ]
        )
        mock_backend.execute_query.return_value = QueryResult(
            dataframe=empty_df,
            row_count=0,
        )

        with patch(
            "m4.core.tools.notes.get_backend",
            return_value=mock_backend,
        ):
            tool = ListPatientNotesTool()
            params = ListPatientNotesInput(subject_id=10001, note_type="discharge")
            tool.invoke(notes_dataset, params)

            sql_arg = mock_backend.execute_query.call_args[0][0]
            assert "LEFT(text, 100)" in sql_arg

    def test_compatibility(self, notes_dataset, tabular_only_dataset):
        """Test compatibility with NOTES and TABULAR-only datasets."""
        tool = ListPatientNotesTool()
        assert tool.is_compatible(notes_dataset) is True
        assert tool.is_compatible(tabular_only_dataset) is False


class TestNoteToolProtocolConformance:
    """Tests that all notes tools conform to the Tool protocol."""

    def test_all_notes_tools_have_required_attributes(self):
        """Test that all notes tools have required protocol attributes."""
        tools = [
            SearchNotesTool(),
            GetNoteTool(),
            ListPatientNotesTool(),
        ]

        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_model")
            assert hasattr(tool, "required_modalities")
            assert hasattr(tool, "supported_datasets")
            assert hasattr(tool, "invoke")
            assert hasattr(tool, "is_compatible")
            assert isinstance(tool.required_modalities, frozenset)

    def test_all_notes_tools_require_notes_modality(self):
        """Test that all notes tools require NOTES modality."""
        tools = [
            SearchNotesTool(),
            GetNoteTool(),
            ListPatientNotesTool(),
        ]

        for tool in tools:
            assert Modality.NOTES in tool.required_modalities
