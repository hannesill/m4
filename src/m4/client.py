"""First-class Python client for M4 data access."""

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from m4.config import (
    _ensure_custom_datasets_loaded,
    get_active_backend,
    get_bigquery_project_id,
)
from m4.core.backends import Backend, get_backend
from m4.core.context import M4ExecutionContext
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.exceptions import DatasetError, ModalityError
from m4.core.telemetry import invoke_tracked
from m4.core.tools import ToolRegistry, ToolSelector, init_tools
from m4.core.tools.management import ListDatasetsInput
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


class M4Client:
    """Resolved M4 client for Python, CLI, and MCP adapters."""

    def __init__(
        self,
        dataset: str | DatasetDefinition | None = None,
        backend: str | Backend | None = None,
        study_id: str | None = None,
        session_id: str | None = None,
        actor: str | None = None,
        interface: str = "python_api",
        project_id: str | None = None,
        db_path: str | Path | None = None,
        path_disclosure: bool = False,
    ) -> None:
        init_tools()
        _ensure_custom_datasets_loaded()

        self.dataset = self._resolve_dataset(dataset)
        self.backend_name, self.backend = self._resolve_backend(backend)
        self.context = M4ExecutionContext(
            dataset=self.dataset,
            backend_name=self.backend_name,
            backend=self.backend,
            interface=interface,
            study_id=study_id,
            session_id=session_id,
            actor=actor,
            project_id=project_id,
            db_path=Path(db_path).expanduser() if db_path else None,
            path_disclosure=path_disclosure,
        )
        self._tool_selector = ToolSelector()

    @classmethod
    def from_active(cls, interface: str = "python_api") -> "M4Client":
        """Create a client from active runtime configuration and environment."""
        path_disclosure = os.getenv("M4_PATH_DISCLOSURE", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
            "paths",
        }
        return cls(
            interface=interface,
            study_id=os.getenv("M4_STUDY_ID"),
            session_id=os.getenv("M4_SESSION_ID"),
            actor=os.getenv("M4_ACTOR"),
            project_id=get_bigquery_project_id(),
            db_path=os.getenv("M4_DB_PATH"),
            path_disclosure=path_disclosure,
        )

    def schema(self) -> dict[str, Any]:
        """Return backend information and available table names."""
        return self._invoke("get_database_schema", GetDatabaseSchemaInput())

    def table_info(self, table_name: str, show_sample: bool = True) -> dict[str, Any]:
        """Return schema and optional sample rows for a table."""
        return self._invoke(
            "get_table_info",
            GetTableInfoInput(table_name=table_name, show_sample=show_sample),
        )

    def query(self, sql: str) -> pd.DataFrame:
        """Execute a read-only SQL query."""
        return self._invoke("execute_query", ExecuteQueryInput(sql_query=sql))

    def list_datasets(self) -> list[str]:
        """Return registered dataset names."""
        _ensure_custom_datasets_loaded()
        return [ds.name for ds in DatasetRegistry.list_all()]

    def dataset_status(self) -> dict[str, Any]:
        """Return detailed dataset availability information."""
        return self._invoke("list_datasets", ListDatasetsInput())

    def search_notes(
        self,
        query: str,
        note_type: str = "all",
        limit: int = 5,
        snippet_length: int = 300,
    ) -> dict[str, Any]:
        """Search clinical notes by keyword."""
        return self._invoke(
            "search_notes",
            SearchNotesInput(
                query=query,
                note_type=note_type,
                limit=limit,
                snippet_length=snippet_length,
            ),
        )

    def get_note(self, note_id: str, max_length: int | None = None) -> dict[str, Any]:
        """Retrieve a clinical note by note ID."""
        return self._invoke(
            "get_note",
            GetNoteInput(note_id=note_id, max_length=max_length),
        )

    def list_patient_notes(
        self,
        subject_id: int,
        note_type: str = "all",
        limit: int = 20,
    ) -> dict[str, Any]:
        """List clinical notes for a patient."""
        return self._invoke(
            "list_patient_notes",
            ListPatientNotesInput(
                subject_id=subject_id,
                note_type=note_type,
                limit=limit,
            ),
        )

    def cohort_builder(self) -> dict[str, Any]:
        """Return cohort builder launch metadata."""
        from m4.apps.cohort_builder.tool import CohortBuilderInput

        return self._invoke("cohort_builder", CohortBuilderInput())

    def query_cohort(self, **criteria: Any) -> dict[str, Any]:
        """Query cohort counts and demographics."""
        from m4.apps.cohort_builder.query_builder import QueryCohortInput

        return self._invoke("query_cohort", QueryCohortInput(**criteria))

    def invoke_tool(self, tool_name: str, params: Any) -> Any:
        """Invoke a registered tool through this client's context."""
        return self._invoke(tool_name, params)

    def _invoke(self, tool_name: str, params: Any) -> Any:
        tool = ToolRegistry.get(tool_name)
        if tool is None:
            raise DatasetError(f"Unknown tool: {tool_name}")

        compat = self._tool_selector.check_compatibility(tool_name, self.dataset)
        if not compat.compatible:
            raise ModalityError(compat.error_message)

        self._ensure_backend()
        return invoke_tracked(tool, self.dataset, params, self.context)

    def _resolve_dataset(
        self, dataset: str | DatasetDefinition | None
    ) -> DatasetDefinition:
        if isinstance(dataset, DatasetDefinition):
            return dataset

        if dataset is None:
            return DatasetRegistry.get_active()

        resolved = DatasetRegistry.get(dataset.lower())
        if resolved is None:
            supported = ", ".join(ds.name for ds in DatasetRegistry.list_all())
            raise DatasetError(
                f"Dataset '{dataset}' not found. Available datasets: {supported}",
                dataset_name=dataset,
            )
        return resolved

    def _resolve_backend(
        self, backend: str | Backend | None
    ) -> tuple[str, Backend | None]:
        if backend is not None and not isinstance(backend, str):
            return backend.name, backend

        backend_name = (backend or get_active_backend()).lower()
        return backend_name, None

    def _ensure_backend(self) -> None:
        if self.backend is not None:
            return

        self.backend = get_backend(self.backend_name)
        self.context = replace(self.context, backend=self.backend)
