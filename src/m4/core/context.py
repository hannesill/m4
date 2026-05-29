"""Execution context passed through M4 tool and backend calls."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m4.core.datasets import DatasetDefinition


@dataclass(frozen=True)
class M4ExecutionContext:
    """Resolved execution context for one M4 client call path."""

    dataset: DatasetDefinition
    backend_name: str
    backend: Any
    interface: str
    study_id: str | None = None
    session_id: str | None = None
    actor: str | None = None
    project_id: str | None = None
    db_path: Path | None = None
    path_disclosure: bool = False

    def public_context(self) -> dict[str, str | None]:
        """Return non-path context fields suitable for JSON envelopes."""
        return {
            "dataset": self.dataset.name,
            "backend": self.backend_name,
            "study_id": self.study_id,
            "session_id": self.session_id,
            "actor": self.actor,
            "project_id": self.project_id,
        }
