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

    response_requested: bool = False
    """True when the agent is waiting for a user response (wait=True)."""

    prompt: str | None = None
    """Question shown to the user when response_requested is True."""

    on_send: str | None = None
    """Instruction for the agent when user clicks 'Send to Agent'."""

    timeout: float | None = None
    """Timeout in seconds for blocking show() cards (sent to frontend for countdown)."""


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

    def __repr__(self) -> str:
        card_short = self.card_id[:8] if self.card_id else ""
        detail = ""
        if self.event_type == "row_click":
            row = self.payload.get("row", {})
            if row:
                keys = list(row.keys())[:4]
                preview = ", ".join(f"{k}={row[k]!r}" for k in keys)
                if len(row) > 4:
                    preview += ", \u2026"
                detail = f" {{{preview}}}"
        elif self.event_type == "point_select":
            points = self.payload.get("points", [])
            detail = f" ({len(points)} points)"
        return f"DisplayEvent({self.event_type}, card={card_short}{detail})"


@dataclass
class DisplayResponse:
    """Response returned from a blocking show() call.

    Contains the user's action and optional selected data (artifact-backed).
    """

    action: str
    """User action: 'confirm', 'skip', or 'timeout'."""

    card_id: str
    """ID of the card the response is for."""

    message: str | None = None
    """Optional text message from the user."""

    summary: str = ""
    """Brief summary of the selected data."""

    artifact_id: str | None = None
    """Artifact ID for the selected data (if any rows were selected)."""

    _store: Any = field(default=None, repr=False)
    """Reference to artifact store (internal, for lazy data loading)."""

    def data(self) -> Any:
        """Load the selected DataFrame from the artifact store.

        Returns None if no selection was made.
        """
        if self.artifact_id and self._store:
            path = self._store._artifacts_dir / f"{self.artifact_id}.parquet"
            if path.exists():
                import pandas as pd

                return pd.read_parquet(path)
        return None

    @property
    def artifact_path(self) -> str | None:
        """Resolved path to the selection artifact on disk, or None."""
        if self.artifact_id and self._store:
            path = self._store._artifacts_dir / f"{self.artifact_id}.parquet"
            if path.exists():
                return str(path)
        return None

    def __repr__(self) -> str:
        lines = [f"DisplayResponse(action={self.action!r}"]
        if self.message:
            lines[0] += f", message={self.message!r}"
        lines[0] += ")"
        if self.summary:
            lines.append(f"  Selection: {self.summary}")
        path = self.artifact_path
        if path:
            lines.append(f"  Artifact:  {path}")
        elif self.artifact_id:
            lines.append(f"  Artifact:  {self.artifact_id} (not on disk)")
        return "\n".join(lines)


@dataclass
class DisplayRequest:
    """A user-initiated request from the browser ('Send to Agent').

    Agents poll for these via pending_requests().
    """

    request_id: str
    """Unique identifier for this request."""

    card_id: str
    """ID of the card the request originated from."""

    prompt: str
    """User's message/question."""

    summary: str = ""
    """Brief summary of the selected data."""

    artifact_id: str | None = None
    """Artifact ID for the selected data (if any)."""

    timestamp: str = ""
    """ISO-format timestamp when the request was created."""

    instruction: str | None = None
    """The card's on_send instruction for the agent."""

    _store: Any = field(default=None, repr=False)
    """Reference to artifact store (internal, for lazy data loading)."""

    _ack_callback: Any = field(default=None, repr=False)
    """Callback to acknowledge/consume this request (internal)."""

    def data(self) -> Any:
        """Load the selected DataFrame from the artifact store.

        Returns None if no selection was made.
        """
        if self.artifact_id and self._store:
            path = self._store._artifacts_dir / f"{self.artifact_id}.parquet"
            if path.exists():
                import pandas as pd

                return pd.read_parquet(path)
        return None

    @property
    def artifact_path(self) -> str | None:
        """Resolved path to the selection artifact on disk, or None."""
        if self.artifact_id and self._store:
            path = self._store._artifacts_dir / f"{self.artifact_id}.parquet"
            if path.exists():
                return str(path)
        return None

    def acknowledge(self) -> None:
        """Mark this request as handled so it won't appear in future polls."""
        if self._ack_callback:
            self._ack_callback(self.request_id)

    def __repr__(self) -> str:
        lines = [f"DisplayRequest(prompt={self.prompt!r}"]
        if self.instruction:
            lines[0] += f", instruction={self.instruction!r}"
        lines[0] += ")"
        if self.summary:
            lines.append(f"  Selection: {self.summary}")
        path = self.artifact_path
        if path:
            lines.append(f"  Artifact:  {path}")
        elif self.artifact_id:
            lines.append(f"  Artifact:  {self.artifact_id} (not on disk)")
        return "\n".join(lines)
