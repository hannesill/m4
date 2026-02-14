"""M4: Multi-Dataset Infrastructure for LLM-Assisted Clinical Research.

M4 provides rigorous, auditable infrastructure for AI-assisted clinical research,
offering a safe interface for LLMs and autonomous agents to interact with EHR data.

Quick Start:
    from m4 import execute_query, set_dataset, get_schema

    set_dataset("mimic-iv")
    print(get_schema())
    result = execute_query("SELECT COUNT(*) FROM mimiciv_hosp.patients")

For MCP server usage, run: m4 serve
"""

__version__ = "0.4.2"

# Expose API functions at package level for easy imports
# Configure vitrine dispatch with m4's skill directory and task config
from pathlib import Path as _Path

from vitrine import show
from vitrine.dispatch import configure as _configure_dispatch

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

_skills_dir = _Path(__file__).parent / "skills" / "system"
if _skills_dir.is_dir():
    _configure_dispatch(
        skills_dir=_skills_dir,
        task_config={
            "reproduce": (
                "reproduce-study",
                "Reproducibility Audit",
                "Bash,Read,Glob,Grep",
            ),
            "report": ("export-report", "Study Report", "Read,Glob,Grep"),
            "paper": (
                "draft-paper",
                "Paper Draft",
                "Bash,Read,Glob,Grep,Write",
            ),
        },
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
    "show",
]
