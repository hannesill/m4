"""M4 Core - MCP-agnostic clinical data platform core.

This package contains the core abstractions for M4, including:
- Dataset definitions with semantic capabilities
- Tool protocol and registry
- Backend abstractions
- SQL validation utilities

The core is intentionally MCP-agnostic to enable testing and reuse.
"""

from m4.core.datasets import (
    Capability,
    DatasetDefinition,
    DatasetRegistry,
    Modality,
)
from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
    validate_limit,
)

__all__ = [
    "Capability",
    "DatasetDefinition",
    "DatasetRegistry",
    "Modality",
    "format_error_with_guidance",
    "is_safe_query",
    "validate_limit",
]
