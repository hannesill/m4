"""Object-to-card renderer for the display pipeline.

Converts Python objects (DataFrames, strings, dicts, Plotly figures,
matplotlib figures, etc.) into CardDescriptor instances with optional
artifact storage. This is the central dispatch that determines how
each object type is represented in the display.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from m4.vitrine._types import CardDescriptor, CardProvenance, CardType, Form
from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.redaction import Redactor

logger = logging.getLogger(__name__)

# Maximum number of preview rows sent over the WebSocket for tables
_PREVIEW_ROWS = 20

# Maximum SVG size (2 MB)
_MAX_SVG_BYTES = 2 * 1024 * 1024

# Maximum Plotly spec size (5 MB)
_MAX_PLOTLY_SPEC_BYTES = 5_000_000

# Maximum data array elements before truncation
_MAX_PLOTLY_DATA_ELEMENTS = 10_000

# Regex to strip <script> tags from SVG output
_SCRIPT_TAG_RE = re.compile(r"<script[\s>].*?</script>", re.IGNORECASE | re.DOTALL)


def _is_plotly_figure(obj: object) -> bool:
    """Check if obj is a Plotly figure without importing plotly."""
    typ = type(obj)
    module = getattr(typ, "__module__", "") or ""
    name = typ.__name__
    return module.startswith("plotly") and name in ("Figure", "FigureWidget")


def _is_matplotlib_figure(obj: object) -> bool:
    """Check if obj is a matplotlib Figure without importing matplotlib."""
    typ = type(obj)
    module = getattr(typ, "__module__", "") or ""
    return module.startswith("matplotlib") and typ.__name__ == "Figure"


def _sanitize_svg(svg_bytes: bytes) -> bytes:
    """Sanitize SVG by stripping script tags and enforcing size limit.

    Args:
        svg_bytes: Raw SVG bytes.

    Returns:
        Sanitized SVG bytes.

    Raises:
        ValueError: If SVG exceeds the size limit after sanitization.
    """
    text = svg_bytes.decode("utf-8", errors="replace")
    text = _SCRIPT_TAG_RE.sub("", text)
    # Strip javascript: URIs from href and xlink:href attributes
    text = re.sub(
        r'\b(xlink:)?href\s*=\s*["\']javascript:[^"\']*["\']',
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Also strip onXxx event attributes
    text = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', "", text)
    text = re.sub(r"\s+on\w+\s*=\s*'[^']*'", "", text)
    result = text.encode("utf-8")
    if len(result) > _MAX_SVG_BYTES:
        raise ValueError(
            f"SVG exceeds size limit: {len(result)} bytes > {_MAX_SVG_BYTES} bytes"
        )
    return result


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
    study: str | None,
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
        study=study,
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
    study: str | None,
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
        study=study,
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
    study: str | None,
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
        study=study,
        preview={"items": items},
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_plotly(
    fig: Any,
    title: str | None,
    description: str | None,
    source: str | None,
    study: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Render a Plotly figure as a chart card with JSON artifact.

    The full Plotly JSON spec is stored as an artifact and also inlined
    in the preview (specs are typically <500KB).
    """
    card_id = _make_card_id()

    # Get a JSON-safe Plotly spec.
    # Plotly Express can emit numpy arrays in fields like `customdata`,
    # which are not directly serializable by the card index writer.
    try:
        spec = fig.to_plotly_json()
    except Exception:
        logger.error(
            "fig.to_plotly_json() failed for %s.%s — card will be empty",
            type(fig).__module__,
            type(fig).__name__,
            exc_info=True,
        )
        spec = {"data": [], "layout": {}}

    try:
        from plotly.utils import PlotlyJSONEncoder

        spec = json.loads(json.dumps(spec, cls=PlotlyJSONEncoder))
    except (ImportError, TypeError) as exc:
        logger.warning(
            "PlotlyJSONEncoder unavailable (%s), using fallback serialization",
            exc,
        )
        spec = json.loads(json.dumps(spec, default=str))

    # Cap spec size: truncate data arrays if over limit
    spec_bytes = len(json.dumps(spec).encode())
    if spec_bytes > _MAX_PLOTLY_SPEC_BYTES:
        logger.warning(
            f"Plotly spec size ({spec_bytes} bytes) exceeds {_MAX_PLOTLY_SPEC_BYTES} "
            f"byte limit, truncating data arrays to {_MAX_PLOTLY_DATA_ELEMENTS} elements"
        )
        for trace in spec.get("data", []):
            for key in list(trace.keys()):
                val = trace[key]
                if isinstance(val, list) and len(val) > _MAX_PLOTLY_DATA_ELEMENTS:
                    trace[key] = val[:_MAX_PLOTLY_DATA_ELEMENTS]

    # Store as JSON artifact
    store.store_json(card_id, spec)

    # Infer title from the figure layout if not provided
    if title is None:
        layout_title = spec.get("layout", {}).get("title")
        if isinstance(layout_title, dict):
            title = layout_title.get("text")
        elif isinstance(layout_title, str):
            title = layout_title

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.PLOTLY,
        title=title or "Chart",
        description=description,
        timestamp=_make_timestamp(),
        study=study,
        artifact_id=card_id,
        artifact_type="json",
        preview={"spec": spec},
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_matplotlib(
    fig: Any,
    title: str | None,
    description: str | None,
    source: str | None,
    study: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Render a matplotlib Figure as an SVG image card.

    The figure is rendered to SVG, sanitized (script tags stripped,
    size capped at 2MB), and stored as an artifact. A base64 preview
    is included in the card descriptor for immediate display.
    """
    card_id = _make_card_id()

    # Render to SVG
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    svg_bytes = buf.getvalue()

    # Sanitize
    svg_bytes = _sanitize_svg(svg_bytes)

    # Store as SVG artifact
    store.store_image(card_id, svg_bytes, "svg")

    # Infer title from figure suptitle if not provided
    if title is None:
        suptitle = fig._suptitle
        if suptitle and suptitle.get_text():
            title = suptitle.get_text()

    # Build base64 preview
    b64_data = base64.b64encode(svg_bytes).decode("ascii")

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.IMAGE,
        title=title or "Figure",
        description=description,
        timestamp=_make_timestamp(),
        study=study,
        artifact_id=card_id,
        artifact_type="svg",
        preview={
            "data": b64_data,
            "format": "svg",
            "size_bytes": len(svg_bytes),
        },
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_decision(
    form: Form,
    title: str | None,
    description: str | None,
    source: str | None,
    study: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Render a Form as a decision card with field specs in preview.

    Forms are always decision cards (wait=True is forced by show()).
    """
    card_id = _make_card_id()
    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.DECISION,
        title=title or "Decision",
        description=description,
        timestamp=_make_timestamp(),
        study=study,
        preview=form.to_dict(),
        provenance=_build_provenance(source),
    )
    store.store_card(card)
    return card


def _render_repr(
    obj: object,
    title: str | None,
    description: str | None,
    source: str | None,
    study: str | None,
    store: ArtifactStore,
) -> CardDescriptor:
    """Fallback: render any object via repr() as a markdown code block."""
    module = getattr(type(obj), "__module__", "") or ""
    if module.startswith("plotly") or module.startswith("matplotlib"):
        logger.warning(
            "Object of type %s.%s fell through to repr() fallback — "
            "this figure was NOT rendered as a chart. "
            "Check that the object is a plotly.graph_objects.Figure "
            "or matplotlib.figure.Figure.",
            module,
            type(obj).__name__,
        )
    text = f"```\n{obj!r}\n```"
    return _render_markdown(text, title, description, source, study, store)


def render(
    obj: object,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
    study: str | None = None,
    store: ArtifactStore | None = None,
    redactor: Redactor | None = None,
) -> CardDescriptor:
    """Convert a Python object to a CardDescriptor, storing artifacts as needed.

    Supported types:
    - pd.DataFrame -> table card with Parquet artifact
    - plotly Figure -> interactive chart with JSON artifact
    - matplotlib Figure -> SVG image card
    - str -> inline markdown card
    - dict -> inline key-value card
    - Other -> repr() fallback as markdown code block

    Args:
        obj: The Python object to render.
        title: Card title shown in header.
        description: Subtitle or context line.
        source: Provenance string (e.g., table name).
        study: Group cards into a named study.
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

    if isinstance(obj, Form):
        return _render_decision(obj, title, description, source, study, store)
    elif isinstance(obj, pd.DataFrame):
        return _render_dataframe(
            obj, title, description, source, study, store, redactor
        )
    elif _is_plotly_figure(obj):
        return _render_plotly(obj, title, description, source, study, store)
    elif _is_matplotlib_figure(obj):
        return _render_matplotlib(obj, title, description, source, study, store)
    elif isinstance(obj, str):
        return _render_markdown(obj, title, description, source, study, store)
    elif isinstance(obj, dict):
        return _render_dict(obj, title, description, source, study, store)
    else:
        return _render_repr(obj, title, description, source, study, store)
