"""M4: Multi-Dataset Infrastructure for LLM-Assisted Clinical Research.

M4 provides rigorous, auditable infrastructure for AI-assisted clinical research,
offering a safe interface for LLMs and autonomous agents to interact with EHR data.

Quick Start:
    from m4 import execute_query, set_dataset, get_schema

    set_dataset("mimic-iv")
    print(get_schema())
    result = execute_query("SELECT COUNT(*) FROM hosp_patients")

For MCP server usage, run: m4 serve
"""

__version__ = "0.3.0"

# Expose API functions at package level for easy imports
from m4.api import (
    # Exceptions
    DatasetError,
    M4Error,
    ModalityError,
    QueryError,
    # Tabular data
    execute_query,
    # Dataset management
    get_active_dataset,
    # Clinical notes
    get_note,
    get_schema,
    get_table_info,
    list_datasets,
    list_patient_notes,
    search_notes,
    set_dataset,
)

__all__ = [
    "DatasetError",
    "M4Error",
    "ModalityError",
    "QueryError",
    "__version__",
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
