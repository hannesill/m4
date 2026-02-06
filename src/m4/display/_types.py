"""Type definitions for the M4 display system.

Defines the core data structures used throughout the display pipeline:
card descriptors, provenance metadata, display events, and card types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CardType(str, Enum):
    """Types of display cards."""

    TABLE = "table"
    MARKDOWN = "markdown"
    KEYVALUE = "keyvalue"
    SECTION = "section"
    PLOTLY = "plotly"
    IMAGE = "image"


@dataclass
class CardProvenance:
    """Provenance metadata for a display card.

    Tracks the origin of displayed data for reproducibility.
    """

    source: str | None = None
    """Data source (e.g., table name like 'mimiciv_hosp.patients')."""

    query: str | None = None
    """SQL query that produced the data, if applicable."""

    code_hash: str | None = None
    """SHA-256 hash of the calling code frame, for traceability."""

    dataset: str | None = None
    """Active M4 dataset name when the card was created."""

    timestamp: str | None = None
    """ISO-format timestamp when the data was generated."""


@dataclass
class CardDescriptor:
    """Describes a display card and its associated data.

    This is the core data structure passed over the WebSocket to the frontend.
    For large objects (DataFrames), the actual data lives in the artifact store
    and is referenced by artifact_id. Small objects (markdown, key-value) are
    inlined in the preview dict.
    """

    card_id: str
    """Unique identifier for this card (UUID)."""

    card_type: CardType
    """Type of card (table, markdown, keyvalue, etc.)."""

    title: str | None = None
    """Card title shown in header."""

    description: str | None = None
    """Subtitle or context line."""

    timestamp: str = ""
    """ISO-format timestamp when the card was created."""

    run_id: str | None = None
    """Optional run ID for grouping related cards."""

    pinned: bool = False
    """Whether this card survives clear() operations."""

    artifact_id: str | None = None
    """Reference to artifact in the store (for large objects)."""

    artifact_type: str | None = None
    """Type of stored artifact ('parquet', 'json', 'svg')."""

    preview: dict[str, Any] = field(default_factory=dict)
    """Type-specific preview data (small enough for WebSocket)."""

    provenance: CardProvenance | None = None
    """Provenance metadata for reproducibility."""


@dataclass
class DisplayEvent:
    """An event sent from the browser UI to the Python client.

    Used for lightweight interactivity — row clicks, point selections,
    and "send to agent" actions.
    """

    event_type: str
    """Event type (e.g., 'row_click', 'point_select', 'send_to_agent')."""

    card_id: str
    """ID of the card that generated the event."""

    payload: dict[str, Any] = field(default_factory=dict)
    """Event-specific data (e.g., selected row, point coordinates)."""
