"""Tests for MCP server serialization helpers.

These functions transform tool return values (dicts with DataFrames)
into user-facing MCP strings. A bug here silently corrupts all output
that LLMs see, making these tests critical for reliability.

Tests cover:
- _serialize_schema_result: Table listing output
- _serialize_table_info_result: Column info + sample data
- _serialize_datasets_result: Multi-dataset status display
- _serialize_set_dataset_result: Switch confirmation with warnings
- _serialize_search_notes_result: Note search snippets
- _serialize_get_note_result: Full note text with truncation
- _serialize_list_patient_notes_result: Patient note metadata
"""

import pandas as pd

from m4.mcp_server import (
    _serialize_datasets_result,
    _serialize_get_note_result,
    _serialize_list_patient_notes_result,
    _serialize_schema_result,
    _serialize_search_notes_result,
    _serialize_set_dataset_result,
    _serialize_table_info_result,
)


class TestSerializeSchemaResult:
    """Test _serialize_schema_result output formatting."""

    def test_schema_with_tables(self):
        """Schema result with tables lists them line by line."""
        result = _serialize_schema_result(
            {
                "backend_info": "Backend: DuckDB (local)",
                "tables": ["mimiciv_hosp.patients", "mimiciv_icu.icustays"],
            }
        )
        assert "DuckDB" in result
        assert "mimiciv_hosp.patients" in result
        assert "mimiciv_icu.icustays" in result
        assert "Available Tables" in result

    def test_schema_no_tables(self):
        """Schema result with no tables shows 'No tables found'."""
        result = _serialize_schema_result(
            {"backend_info": "Backend: DuckDB", "tables": []}
        )
        assert "No tables found" in result

    def test_schema_empty_result(self):
        """Schema result with missing keys uses defaults."""
        result = _serialize_schema_result({})
        assert "No tables found" in result


class TestSerializeTableInfoResult:
    """Test _serialize_table_info_result output formatting."""

    def test_table_info_with_schema_and_sample(self):
        """Table info with both schema and sample data."""
        schema_df = pd.DataFrame(
            {"name": ["subject_id", "gender"], "type": ["INTEGER", "VARCHAR"]}
        )
        sample_df = pd.DataFrame({"subject_id": [1, 2], "gender": ["M", "F"]})

        result = _serialize_table_info_result(
            {
                "backend_info": "Backend: DuckDB",
                "table_name": "mimiciv_hosp.patients",
                "schema": schema_df,
                "sample": sample_df,
            }
        )
        assert "mimiciv_hosp.patients" in result
        assert "Column Information" in result
        assert "subject_id" in result
        assert "Sample Data" in result
        assert "M" in result

    def test_table_info_no_sample(self):
        """Table info without sample data omits sample section."""
        schema_df = pd.DataFrame({"name": ["id"], "type": ["INT"]})
        result = _serialize_table_info_result(
            {
                "backend_info": "Backend: DuckDB",
                "table_name": "test",
                "schema": schema_df,
                "sample": None,
            }
        )
        assert "Sample Data" not in result
        assert "Column Information" in result

    def test_table_info_no_schema(self):
        """Table info without schema shows placeholder."""
        result = _serialize_table_info_result(
            {
                "backend_info": "Backend: DuckDB",
                "table_name": "test",
                "schema": None,
                "sample": None,
            }
        )
        assert "no schema information" in result


class TestSerializeDatasetsResult:
    """Test _serialize_datasets_result output formatting."""

    def test_no_datasets(self):
        """No datasets returns simple message."""
        result = _serialize_datasets_result({"active_dataset": None, "datasets": {}})
        assert "No datasets detected" in result

    def test_single_active_dataset(self):
        """Single active dataset shows status correctly."""
        result = _serialize_datasets_result(
            {
                "active_dataset": "mimic-iv-demo",
                "backend": "duckdb",
                "datasets": {
                    "mimic-iv-demo": {
                        "is_active": True,
                        "parquet_present": True,
                        "db_present": True,
                        "bigquery_support": False,
                        "derived": None,
                    }
                },
            }
        )
        assert "Active dataset: mimic-iv-demo" in result
        assert "(Active)" in result
        assert "DuckDB" in result

    def test_dataset_with_derived_tables(self):
        """Derived table info is included when present."""
        result = _serialize_datasets_result(
            {
                "active_dataset": "mimic-iv",
                "backend": "duckdb",
                "datasets": {
                    "mimic-iv": {
                        "is_active": True,
                        "parquet_present": True,
                        "db_present": True,
                        "bigquery_support": True,
                        "derived": {
                            "supported": True,
                            "total": 63,
                            "materialized": 63,
                        },
                    }
                },
            }
        )
        assert "Derived Tables" in result
        assert "63/63" in result

    def test_dataset_with_partial_derived(self):
        """Partial derived tables show init hint."""
        result = _serialize_datasets_result(
            {
                "active_dataset": "mimic-iv",
                "backend": "duckdb",
                "datasets": {
                    "mimic-iv": {
                        "is_active": True,
                        "parquet_present": True,
                        "db_present": True,
                        "bigquery_support": True,
                        "derived": {
                            "supported": True,
                            "total": 63,
                            "materialized": 10,
                        },
                    }
                },
            }
        )
        assert "10/63" in result
        assert "m4 init-derived" in result

    def test_bigquery_backend_label(self):
        """BigQuery backend shows 'cloud (BigQuery)' label."""
        result = _serialize_datasets_result(
            {
                "active_dataset": "mimic-iv",
                "backend": "bigquery",
                "datasets": {
                    "mimic-iv": {
                        "is_active": True,
                        "parquet_present": False,
                        "db_present": False,
                        "bigquery_support": True,
                        "derived": None,
                    }
                },
            }
        )
        assert "BigQuery" in result


class TestSerializeSetDatasetResult:
    """Test _serialize_set_dataset_result output formatting."""

    def test_successful_switch(self):
        """Successful switch shows confirmation."""
        result = _serialize_set_dataset_result(
            {"dataset_name": "mimic-iv-demo", "warnings": []}
        )
        assert "mimic-iv-demo" in result
        assert "switched" in result.lower()

    def test_switch_with_warnings(self):
        """Switch with warnings appends warning messages."""
        result = _serialize_set_dataset_result(
            {
                "dataset_name": "mimic-iv",
                "warnings": ["Local database not found."],
            }
        )
        assert "mimic-iv" in result
        assert "Local database not found" in result


class TestSerializeSearchNotesResult:
    """Test _serialize_search_notes_result output formatting."""

    def test_no_matches(self):
        """No matches shows 'No matches found' message."""
        result = _serialize_search_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "query": "pneumonia",
                "snippet_length": 300,
                "results": {
                    "mimiciv_note.discharge": pd.DataFrame(),
                },
            }
        )
        assert "No matches found" in result
        assert "pneumonia" in result

    def test_with_matches(self):
        """Matches show snippets and tip."""
        df = pd.DataFrame(
            {
                "note_id": ["123"],
                "subject_id": [456],
                "snippet": ["...found pneumonia in patient..."],
                "note_length": [5000],
            }
        )
        result = _serialize_search_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "query": "pneumonia",
                "snippet_length": 300,
                "results": {"mimiciv_note.discharge": df},
            }
        )
        assert "pneumonia" in result
        assert "123" in result
        assert "get_note" in result  # Tip is included

    def test_empty_results_dict(self):
        """Empty results dict shows no matches."""
        result = _serialize_search_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "query": "test",
                "snippet_length": 300,
                "results": {},
            }
        )
        assert "No matches found" in result


class TestSerializeGetNoteResult:
    """Test _serialize_get_note_result output formatting."""

    def test_full_note(self):
        """Full note shows note text and metadata."""
        result = _serialize_get_note_result(
            {
                "backend_info": "Backend: DuckDB",
                "note_id": "10000032_DS-1",
                "subject_id": 10000032,
                "text": "Patient presented with chest pain...",
                "note_length": 35,
                "truncated": False,
            }
        )
        assert "10000032_DS-1" in result
        assert "Patient presented" in result
        assert "truncated" not in result.lower()

    def test_truncated_note(self):
        """Truncated note shows truncation indicator."""
        result = _serialize_get_note_result(
            {
                "backend_info": "Backend: DuckDB",
                "note_id": "123",
                "subject_id": 456,
                "text": "First 500 chars of a long note...",
                "note_length": 10000,
                "truncated": True,
            }
        )
        assert "truncated" in result.lower()
        assert "10000" in result


class TestSerializeListPatientNotesResult:
    """Test _serialize_list_patient_notes_result output formatting."""

    def test_no_notes_found(self):
        """No notes for patient shows helpful message."""
        result = _serialize_list_patient_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "subject_id": 99999,
                "notes": {},
            }
        )
        assert "No notes found" in result
        assert "99999" in result
        assert "Verify" in result  # Tip about verifying subject_id

    def test_notes_found(self):
        """Notes found shows metadata and get_note tip."""
        df = pd.DataFrame(
            {
                "note_id": ["DS-1", "DS-2"],
                "subject_id": [123, 123],
                "note_type": ["discharge", "discharge"],
                "note_length": [5000, 3000],
                "preview": ["Patient...", "Admitted..."],
            }
        )
        result = _serialize_list_patient_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "subject_id": 123,
                "notes": {"mimiciv_note.discharge": df},
            }
        )
        assert "123" in result
        assert "DS-1" in result
        assert "get_note" in result  # Tip is included

    def test_all_empty_dataframes(self):
        """All empty DataFrames shows 'no notes found'."""
        result = _serialize_list_patient_notes_result(
            {
                "backend_info": "Backend: DuckDB",
                "subject_id": 123,
                "notes": {
                    "mimiciv_note.discharge": pd.DataFrame(),
                    "mimiciv_note.radiology": pd.DataFrame(),
                },
            }
        )
        assert "No notes found" in result
