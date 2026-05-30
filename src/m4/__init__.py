"""M4: Multi-Dataset Infrastructure for LLM-Assisted Clinical Research.

M4 provides rigorous, auditable infrastructure for AI-assisted clinical research,
offering a safe interface for LLMs and autonomous agents to interact with EHR data.

Quick Start:
    from m4 import execute_query, get_schema

    print(get_schema(dataset="mimic-iv"))
    result = execute_query(
        "SELECT COUNT(*) FROM mimiciv_hosp.patients",
        dataset="mimic-iv",
    )

For MCP server usage, run: m4 serve
"""

__version__ = "0.5.2"

# Expose API functions at package level for easy imports
from vitrine import show

from m4.api import (
    # Exceptions
    DatasetError,
    M4Client,
    M4Error,
    ModalityError,
    QueryError,
    # Tabular data
    execute_query,
    # Dataset management
    get_active_dataset,
    get_capabilities,
    # Clinical notes
    get_note,
    get_schema,
    get_table_info,
    # Telemetry
    get_telemetry_path,
    list_datasets,
    list_patient_notes,
    search_notes,
    set_dataset,
)
from m4.core.telemetry import set_agent_id

__all__ = [
    "DatasetError",
    "M4Client",
    "M4Error",
    "ModalityError",
    "QueryError",
    "__version__",
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
    "set_agent_id",
    "set_dataset",
    "show",
]
