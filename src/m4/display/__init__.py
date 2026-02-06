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

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state (thread-safe via _lock)
_lock = threading.Lock()
_server: Any = None  # DisplayServer | None
_store: Any = None  # ArtifactStore | None
_session_id: str | None = None
_remote_url: str | None = None
_auth_token: str | None = None


def _get_display_dir() -> Path:
    """Resolve the display directory under {m4_data}/display/."""
    try:
        from m4.config import _PROJECT_DATA_DIR

        return _PROJECT_DATA_DIR / "display"
    except Exception:
        import tempfile

        return Path(tempfile.gettempdir()) / "m4_data" / "display"


def _pid_file_path() -> Path:
    """Return the path to the server PID file."""
    return _get_display_dir() / ".server.json"


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health_check(url: str, expected_session_id: str) -> bool:
    """GET /api/health and validate session_id matches."""
    try:
        import urllib.request

        req = urllib.request.Request(f"{url}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return (
                data.get("status") == "ok"
                and data.get("session_id") == expected_session_id
            )
    except Exception:
        return False


def _discover_server() -> dict[str, Any] | None:
    """Read PID file, validate process and health, return server info or None.

    Cleans up stale PID files automatically.
    """
    pid_path = _pid_file_path()
    if not pid_path.exists():
        return None

    try:
        info = json.loads(pid_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    pid = info.get("pid")
    session_id = info.get("session_id")
    url = info.get("url")

    if not all([pid, session_id, url]):
        return None

    # Check if process is alive
    if not _is_process_alive(pid):
        logger.debug(f"Stale PID file (pid={pid} not alive), removing")
        try:
            pid_path.unlink()
        except OSError:
            pass
        return None

    # Validate health endpoint matches session_id
    if not _health_check(url, session_id):
        logger.debug(f"Health check failed for {url}, removing stale PID file")
        try:
            pid_path.unlink()
        except OSError:
            pass
        return None

    return info


def _remote_command(url: str, token: str, payload: dict[str, Any]) -> bool:
    """POST /api/command with Bearer auth. Returns True on success."""
    try:
        import urllib.request

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{url}/api/command",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        logger.debug(f"Remote command failed for {url}")
        return False


def _get_session_dir() -> Path:
    """Determine the session directory for artifact storage."""
    return _get_display_dir()


def _ensure_started(
    port: int = 7741,
    open_browser: bool = True,
) -> None:
    """Ensure the display server is running, starting it if needed.

    Discovery flow:
    1. If _remote_url set → health check → if healthy, return
    2. If in-process _server running → return
    3. _discover_server() → if found, set _remote_url, _auth_token, return
    4. No server → _start_process(), poll discovery with backoff for up to 5s
    """
    global _server, _store, _session_id, _remote_url, _auth_token

    with _lock:
        # Fast path: already connected to remote
        if _remote_url is not None:
            info = _discover_server()
            if info and info.get("url") == _remote_url:
                return
            # Stale remote, clear it
            _remote_url = None
            _auth_token = None

        # In-process server running
        if _server is not None and _server.is_running:
            return

        # Try to discover an existing persistent server
        info = _discover_server()
        if info:
            _remote_url = info["url"]
            _auth_token = info.get("token")
            _session_id = info["session_id"]
            # Create a local store for rendering artifacts to disk
            if _store is None:
                from m4.display.artifacts import ArtifactStore

                session_dir = _get_display_dir() / _session_id
                _store = ArtifactStore(session_dir=session_dir, session_id=_session_id)
            return

        # No server found → start a new persistent process
        _start_process(port=port, open_browser=open_browser)

        # Poll for the PID file to appear (server writes it after binding)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            info = _discover_server()
            if info:
                _remote_url = info["url"]
                _auth_token = info.get("token")
                _session_id = info["session_id"]
                if _store is None:
                    from m4.display.artifacts import ArtifactStore

                    session_dir = _get_display_dir() / _session_id
                    _store = ArtifactStore(
                        session_dir=session_dir, session_id=_session_id
                    )
                return
            time.sleep(0.1)

        # Fallback: start in-thread if process discovery failed
        logger.debug("Process discovery failed, falling back to in-thread server")
        from m4.display.artifacts import ArtifactStore
        from m4.display.server import DisplayServer

        if _session_id is None:
            _session_id = uuid.uuid4().hex[:12]

        session_dir = _get_display_dir() / _session_id

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
    """Stop the in-process display server."""
    global _server

    with _lock:
        if _server is not None:
            _server.stop()
            _server = None


def stop_server() -> bool:
    """Stop a running persistent display server via POST /api/shutdown.

    Returns True if a server was stopped.
    """
    global _remote_url, _auth_token, _store, _session_id

    info = _discover_server()
    if not info:
        return False

    url = info["url"]
    token = info.get("token")

    try:
        import urllib.request

        data = json.dumps({}).encode()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(
            f"{url}/api/shutdown",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass

    # Wait for process to exit
    pid = info.get("pid")
    if pid:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                break
            time.sleep(0.1)

    # Clean up PID file
    pid_path = _pid_file_path()
    if pid_path.exists():
        try:
            pid_path.unlink()
        except OSError:
            pass

    # Clean up session directory
    session_id = info.get("session_id")
    if session_id:
        import shutil

        session_dir = _get_display_dir() / session_id
        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
            except OSError:
                pass

    # Clear module state
    with _lock:
        _remote_url = None
        _auth_token = None
        if _session_id == session_id:
            _store = None
            _session_id = None

    return True


def server_status() -> dict[str, Any] | None:
    """Return info about a running persistent display server, or None."""
    return _discover_server()


def _push_remote(card_data: dict[str, Any]) -> bool:
    """Push a card to the remote server. Returns True on success."""
    global _remote_url, _auth_token

    if _remote_url is None or _auth_token is None:
        return False

    ok = _remote_command(_remote_url, _auth_token, {"type": "card", "card": card_data})
    if not ok:
        # Retry once after re-discovery
        _remote_url = None
        _auth_token = None
        info = _discover_server()
        if info:
            _remote_url = info["url"]
            _auth_token = info.get("token")
            return _remote_command(
                _remote_url, _auth_token, {"type": "card", "card": card_data}
            )
    return ok


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

    from m4.display.artifacts import _serialize_card
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
        if _remote_url:
            _push_remote(_serialize_card(card))
        elif _server is not None:
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

    if _remote_url:
        _push_remote(_serialize_card(card))
    elif _server is not None:
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
        if _remote_url and _auth_token:
            _remote_command(
                _remote_url,
                _auth_token,
                {"type": "clear", "keep_pinned": keep_pinned},
            )
        elif _server is not None:
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
    if _remote_url and _auth_token:
        _remote_command(
            _remote_url,
            _auth_token,
            {"type": "section", "title": title, "run_id": run_id},
        )
    elif _server is not None:
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
