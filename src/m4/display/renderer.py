"""Object-to-card renderer for the display pipeline.

Converts Python objects (DataFrames, strings, dicts, etc.) into
CardDescriptor instances with optional artifact storage. This is
the central dispatch that determines how each object type is
represented in the display.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from m4.display._types import CardDescriptor, CardProvenance, CardType
from m4.display.artifacts import ArtifactStore
from m4.display.redaction import Redactor

# Maximum number of preview rows sent over the WebSocket for tables
_PREVIEW_ROWS = 20


def _make_card_id() -> str:
    """Generate a unique card ID."""
    return uuid.uuid4().hex[:12]


def _make_timestamp() -> str:
    """Generate an ISO-format UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _build_provenance(
    source: str | None = None,
    dataset: str | None = None,
) -> CardProvenance | None:
    """Build provenance metadata if any source info is provided."""
    if source is None and dataset is None:
        return None
    return CardProvenance(
        source=source,
        dataset=dataset,
        timestamp=_make_timestamp(),
    )


def _render_dataframe(
    df: pd.DataFrame,
    title: str | None,
    description: str | None,
    source: str | None,
    run_id: str | None,
    store: ArtifactStore,
    redactor: Redactor,
) -> CardDescriptor:
    """Render a DataFrame as a table card with Parquet artifact."""
    card_id = _make_card_id()

    # Apply redaction (currently pass-through)
    redacted_df = redactor.redact_dataframe(df)
    redacted_df, _was_truncated = redactor.enforce_row_limit(redacted_df)

    # Store full DataFrame as Parquet
    store.store_dataframe(card_id, redacted_df)

    # Build preview (first N rows)
    preview_df = redacted_df.head(_PREVIEW_ROWS)
    preview_rows = preview_df.values.tolist()
    columns = list(redacted_df.columns)
    dtypes = {col: str(redacted_df[col].dtype) for col in columns}

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.TABLE,
        title=title or "Table",
        description=description,
        timestamp=_make_timestamp(),
        run_id=run_id,
        artifact_id=card_id,
        artifact_type="parquet",
        preview={
            "columns": columns,
            "dtypes": dtypes,
            "shape": list(redacted_df.shape),
            "preview_rows": preview_rows,
        },
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_markdown(
    text: str,
    title: str | None,
    description: str | None,
    source: str | None,
    run_id: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Render a string as a markdown card (inlined, no artifact)."""
    card_id = _make_card_id()
    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.MARKDOWN,
        title=title,
        description=description,
        timestamp=_make_timestamp(),
        run_id=run_id,
        preview={"text": text},
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_dict(
    data: dict[str, Any],
    title: str | None,
    description: str | None,
    source: str | None,
    run_id: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Render a dict as a key-value card (inlined, no artifact)."""
    card_id = _make_card_id()

    # Convert values to strings for display
    items = {str(k): str(v) for k, v in data.items()}

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.KEYVALUE,
        title=title or "Key-Value",
        description=description,
        timestamp=_make_timestamp(),
        run_id=run_id,
        preview={"items": items},
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_repr(
    obj: object,
    title: str | None,
    description: str | None,
    source: str | None,
    run_id: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Fallback: render any object via repr() as a markdown code block."""
    text = f"```\n{obj!r}\n```"
    return _render_markdown(text, title, description, source, run_id, store)


def render(
    obj: object,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
    run_id: str | None = None,
    store: ArtifactStore | None = None,
    redactor: Redactor | None = None,
) -> CardDescriptor:
    """Convert a Python object to a CardDescriptor, storing artifacts as needed.

    Supported types:
    - pd.DataFrame → table card with Parquet artifact
    - str → inline markdown card
    - dict → inline key-value card
    - Other → repr() fallback as markdown code block

    Args:
        obj: The Python object to render.
        title: Card title shown in header.
        description: Subtitle or context line.
        source: Provenance string (e.g., table name).
        run_id: Group cards into a named run.
        store: ArtifactStore for persisting large objects.
        redactor: Redactor instance for PHI/PII masking.

    Returns:
        A CardDescriptor describing the rendered card.

    Raises:
        ValueError: If no artifact store is provided for types that need one.
    """
    if store is None:
        raise ValueError("An ArtifactStore is required for rendering")

    if redactor is None:
        redactor = Redactor()

    if isinstance(obj, pd.DataFrame):
        return _render_dataframe(
            obj, title, description, source, run_id, store, redactor
        )
    elif isinstance(obj, str):
        return _render_markdown(obj, title, description, source, run_id, store)
    elif isinstance(obj, dict):
        return _render_dict(obj, title, description, source, run_id, store)
    else:
        return _render_repr(obj, title, description, source, run_id, store)
