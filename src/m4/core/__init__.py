"""M4 Core - MCP-agnostic clinical data platform core.

This package contains the core abstractions for M4, including:
- Dataset definitions with semantic capabilities
- Tool protocol and registry
- Backend abstractions

The core is intentionally MCP-agnostic to enable testing and reuse.
"""

from m4.core.datasets import (
    Modality,
    Capability,
    DatasetDefinition,
    DatasetRegistry,
)

__all__ = [
    "Modality",
    "Capability",
    "DatasetDefinition",
    "DatasetRegistry",
]
