"""M4 Display: Visualization backend for code execution agents.

Provides a local display server that pushes visualizations to a browser tab.
Agents call show() to render DataFrames, charts, markdown, and more.

Quick Start:
    from m4.display import show

    show(df, title="Demographics")
    show("## Key Finding\\nMortality is 23%")
    show({"patients": 4238, "mortality": "23%"})
"""

from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state (thread-safe via _lock)
_lock = threading.Lock()
_server: Any = None  # DisplayServer | None
_store: Any = None  # ArtifactStore | None
_session_id: str | None = None


def _get_session_dir() -> Path:
    """Determine the session directory for artifact storage."""
    # Try to use M4's data directory
    try:
        from m4.config import get_m4_data_dir

        data_dir = get_m4_data_dir()
    except Exception:
        # Fallback to temp directory
        import tempfile

        data_dir = Path(tempfile.gettempdir()) / "m4_data"

    return data_dir / "display"


def _ensure_started(
    port: int = 7741,
    open_browser: bool = True,
) -> None:
    """Ensure the display server is running, starting it if needed."""
    global _server, _store, _session_id

    with _lock:
        if _server is not None and _server.is_running:
            return

        from m4.display.artifacts import ArtifactStore
        from m4.display.server import DisplayServer

        if _session_id is None:
            _session_id = uuid.uuid4().hex[:12]

        session_dir = _get_session_dir() / _session_id

        if _store is None:
            _store = ArtifactStore(session_dir=session_dir, session_id=_session_id)

        _server = DisplayServer(store=_store, port=port)
        _server.start(open_browser=open_browser)


def start(
    port: int = 7741,
    open_browser: bool = True,
    mode: str = "thread",
) -> None:
    """Start the display server.

    Called automatically on first show(). Call explicitly to customize settings.

    Args:
        port: Port to bind (auto-increments if taken).
        open_browser: Open browser tab on start.
        mode: "thread" (default) or "process" (separate daemon).
    """
    if mode == "process":
        _start_process(port=port, open_browser=open_browser)
    else:
        _ensure_started(port=port, open_browser=open_browser)


def _start_process(port: int = 7741, open_browser: bool = True) -> None:
    """Start the display server as a separate process."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "m4.display.server",
        "--port",
        str(port),
    ]
    if not open_browser:
        cmd.append("--no-open")

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def stop() -> None:
    """Stop the display server."""
    global _server

    with _lock:
        if _server is not None:
            _server.stop()
            _server = None


def show(
    obj: Any,
    title: str | None = None,
    description: str | None = None,
    *,
    run_id: str | None = None,
    source: str | None = None,
    replace: str | None = None,
    position: str | None = None,
) -> str:
    """Push any displayable object to the browser. Returns card_id.

    Supported types:
    - pd.DataFrame → interactive table (artifact-backed, paged)
    - str → markdown card
    - dict → formatted key-value card
    - Other → repr() fallback

    Auto-starts the display server on first call.

    Args:
        obj: Python object to display.
        title: Card title shown in header.
        description: Subtitle or context line.
        run_id: Group cards into a named run (for filtering).
        source: Provenance string (e.g., table name, query).
        replace: Card ID to update instead of appending.
        position: "top" to prepend instead of append.

    Returns:
        The card_id for the created/updated card.
    """
    _ensure_started()

    from m4.display.renderer import render

    if replace is not None:
        # Update an existing card
        card = render(
            obj,
            title=title,
            description=description,
            source=source,
            run_id=run_id,
            store=_store,
        )
        # Update the old card's entry
        _store.update_card(
            replace,
            **{
                "title": card.title,
                "description": card.description,
                "preview": card.preview,
                "artifact_id": card.artifact_id,
                "artifact_type": card.artifact_type,
            },
        )
        if _server is not None:
            _server.push_card(card)
        return card.card_id

    card = render(
        obj,
        title=title,
        description=description,
        source=source,
        run_id=run_id,
        store=_store,
    )

    if _server is not None:
        _server.push_card(card)

    return card.card_id


def clear(keep_pinned: bool = True) -> None:
    """Clear all cards from the display.

    Args:
        keep_pinned: If True, preserve pinned cards.
    """
    with _lock:
        if _store is not None:
            _store.clear(keep_pinned=keep_pinned)
        if _server is not None:
            _server.push_clear(keep_pinned=keep_pinned)


def section(title: str, run_id: str | None = None) -> None:
    """Insert a section divider in the display feed.

    Args:
        title: Section title.
        run_id: Optional run ID for grouping.
    """
    _ensure_started()

    from m4.display._types import CardDescriptor, CardType
    from m4.display.renderer import _make_card_id, _make_timestamp

    card = CardDescriptor(
        card_id=_make_card_id(),
        card_type=CardType.SECTION,
        title=title,
        timestamp=_make_timestamp(),
        run_id=run_id,
        preview={"title": title},
    )

    if _store is not None:
        _store.store_card(card)
    if _server is not None:
        _server.push_section(title, run_id=run_id)


def export(path: str, format: str = "html") -> None:
    """Export current session as a self-contained artifact.

    Args:
        path: Output file path.
        format: "html" (self-contained) or "json" (card index + artifacts).
    """
    raise NotImplementedError("Export is planned for Phase 5")


def on_event(callback: Any) -> None:
    """Register a callback for UI events (row click, point select, etc.).

    Args:
        callback: Function that receives DisplayEvent instances.
    """
    raise NotImplementedError("Event handling is planned for Phase 4")
