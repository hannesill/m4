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


# ---------------------------------------------------------------------------
# Form field primitives
# ---------------------------------------------------------------------------


@dataclass
class Dropdown:
    """Single-select dropdown."""

    name: str
    options: list[str]
    label: str | None = None
    default: str | None = None

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("Dropdown options must be non-empty")
        if self.default is not None and self.default not in self.options:
            raise ValueError(
                f"Dropdown default {self.default!r} not in options {self.options}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "dropdown",
            "name": self.name,
            "options": self.options,
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class MultiSelect:
    """Multi-select list."""

    name: str
    options: list[str]
    label: str | None = None
    default: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("MultiSelect options must be non-empty")
        for d in self.default:
            if d not in self.options:
                raise ValueError(
                    f"MultiSelect default {d!r} not in options {self.options}"
                )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "multiselect",
            "name": self.name,
            "options": self.options,
        }
        if self.label:
            d["label"] = self.label
        if self.default:
            d["default"] = self.default
        return d


@dataclass
class Slider:
    """Single-value slider."""

    name: str
    range: tuple[float, float]
    label: str | None = None
    default: float | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        if self.range[0] > self.range[1]:
            raise ValueError(
                f"Slider range min ({self.range[0]}) must be <= max ({self.range[1]})"
            )
        if self.default is not None:
            if self.default < self.range[0] or self.default > self.range[1]:
                raise ValueError(
                    f"Slider default {self.default} not in range {self.range}"
                )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "slider",
            "name": self.name,
            "min": self.range[0],
            "max": self.range[1],
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = self.default
        if self.step is not None:
            d["step"] = self.step
        return d


@dataclass
class RangeSlider:
    """Two-handle range slider."""

    name: str
    range: tuple[float, float]
    label: str | None = None
    default: tuple[float, float] | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        if self.range[0] > self.range[1]:
            raise ValueError(
                f"RangeSlider range min ({self.range[0]}) must be <= max ({self.range[1]})"
            )
        if self.default is not None:
            if self.default[0] > self.default[1]:
                raise ValueError(
                    f"RangeSlider default min ({self.default[0]}) must be <= max ({self.default[1]})"
                )
            if self.default[0] < self.range[0] or self.default[1] > self.range[1]:
                raise ValueError(
                    f"RangeSlider default {self.default} not within range {self.range}"
                )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "range_slider",
            "name": self.name,
            "min": self.range[0],
            "max": self.range[1],
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = list(self.default)
        if self.step is not None:
            d["step"] = self.step
        return d


@dataclass
class Checkbox:
    """Boolean checkbox."""

    name: str
    label: str | None = None
    default: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "checkbox",
            "name": self.name,
            "default": self.default,
        }
        if self.label:
            d["label"] = self.label
        return d


@dataclass
class Toggle:
    """Boolean toggle switch."""

    name: str
    label: str | None = None
    default: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "toggle",
            "name": self.name,
            "default": self.default,
        }
        if self.label:
            d["label"] = self.label
        return d


@dataclass
class RadioGroup:
    """Single-select radio button group."""

    name: str
    options: list[str]
    label: str | None = None
    default: str | None = None

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("RadioGroup options must be non-empty")
        if self.default is not None and self.default not in self.options:
            raise ValueError(
                f"RadioGroup default {self.default!r} not in options {self.options}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "radio",
            "name": self.name,
            "options": self.options,
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class TextInput:
    """Single-line text input."""

    name: str
    label: str | None = None
    default: str = ""
    placeholder: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "text",
            "name": self.name,
        }
        if self.label:
            d["label"] = self.label
        if self.default:
            d["default"] = self.default
        if self.placeholder:
            d["placeholder"] = self.placeholder
        return d


@dataclass
class DateRange:
    """Date range picker (two date inputs)."""

    name: str
    label: str | None = None
    default: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if self.default is not None and self.default[0] > self.default[1]:
            raise ValueError(
                f"DateRange default start ({self.default[0]}) must be <= end ({self.default[1]})"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "date_range",
            "name": self.name,
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = list(self.default)
        return d


@dataclass
class NumberInput:
    """Numeric input with optional min/max/step."""

    name: str
    label: str | None = None
    default: float | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(
                f"NumberInput min ({self.min}) must be <= max ({self.max})"
            )
        if self.default is not None:
            if self.min is not None and self.default < self.min:
                raise ValueError(
                    f"NumberInput default {self.default} is less than min {self.min}"
                )
            if self.max is not None and self.default > self.max:
                raise ValueError(
                    f"NumberInput default {self.default} is greater than max {self.max}"
                )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "number",
            "name": self.name,
        }
        if self.label:
            d["label"] = self.label
        if self.default is not None:
            d["default"] = self.default
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.step is not None:
            d["step"] = self.step
        return d


# Union of all field primitives
FormField = (
    Dropdown
    | MultiSelect
    | Slider
    | RangeSlider
    | Checkbox
    | Toggle
    | RadioGroup
    | TextInput
    | DateRange
    | NumberInput
)


@dataclass
class Form:
    """A group of form field primitives rendered as a single card.

    No nesting, no layout grid, no conditional visibility.
    Fields stack vertically within the card.
    """

    fields: list[FormField]

    def __post_init__(self) -> None:
        names = [f.name for f in self.fields]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                raise ValueError(f"Duplicate form field name: {name!r}")
            seen.add(name)

    def to_dict(self) -> dict[str, Any]:
        return {"fields": [f.to_dict() for f in self.fields]}


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

    study: str | None = None
    """Optional study name for grouping related cards."""

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

    timeout: float | None = None
    """Timeout in seconds for blocking show() cards (sent to frontend for countdown)."""

    actions: list[str] | None = None
    """Named action buttons for decision cards (replaces default Confirm button)."""

    response_action: str | None = None
    """Resolved action from the researcher (e.g. 'confirm', 'skip', 'Approve')."""

    response_message: str | None = None
    """Optional free-form text entered with the response."""

    response_values: dict[str, Any] = field(default_factory=dict)
    """Submitted form/control values captured at response time."""

    response_summary: str | None = None
    """Human-readable summary of any selected rows/points."""

    response_artifact_id: str | None = None
    """Artifact ID for response-backed selection data, if present."""

    response_timestamp: str | None = None
    """ISO timestamp of when the response was submitted."""


@dataclass
class DisplayEvent:
    """An event sent from the browser UI to the Python client.

    Used for lightweight interactivity — row clicks and point selections.
    """

    event_type: str
    """Event type (e.g., 'row_click', 'point_select')."""

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

    CONFIRM = "confirm"
    SKIP = "skip"
    TIMEOUT = "timeout"
    ERROR = "error"

    action: str
    """User action: 'confirm', 'skip', 'timeout', or 'error'."""

    card_id: str
    """ID of the card the response is for."""

    message: str | None = None
    """Optional text message from the user."""

    summary: str = ""
    """Brief summary of the selected data."""

    artifact_id: str | None = None
    """Artifact ID for the selected data (if any rows were selected)."""

    values: dict[str, Any] = field(default_factory=dict)
    """Form field values (populated when the card is a form or has controls)."""

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


class DisplayHandle(str):
    """String-like return value for non-blocking show() calls.

    Behaves like the historical card_id string while exposing `url`
    when a study-scoped deep link is available.
    """

    card_id: str
    url: str | None
    study: str | None

    def __new__(
        cls,
        card_id: str,
        url: str | None = None,
        study: str | None = None,
    ) -> DisplayHandle:
        obj = str.__new__(cls, card_id)
        obj.card_id = card_id
        obj.url = url
        obj.study = study
        return obj
