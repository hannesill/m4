from __future__ import annotations

from m4.config import (
    detect_available_local_datasets,  # noqa: F401 - compatibility patch target
    get_active_backend,  # noqa: F401 - compatibility patch target
    set_active_dataset,  # noqa: F401 - compatibility patch target
)
from m4.services.results import (
    CommandError,
)


def set_active_dataset_service(target: str) -> CommandError:
    """Return migration guidance for the removed active dataset command."""
    return CommandError(
        command="use",
        code="active_dataset_removed",
        message=(
            "Global active dataset state has been removed. Commands and APIs now "
            "require an explicit dataset."
        ),
        hint=(
            "Use --dataset on CLI commands, M4Client(dataset=...) in Python, or "
            "dataset=... on MCP tool calls."
        ),
    )
