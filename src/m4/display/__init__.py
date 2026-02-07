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
_store: Any = None  # ArtifactStore | None (backwards-compat, resolves to current run)
_run_manager: Any = None  # RunManager | None
_current_run_id: str | None = None
_session_id: str | None = None
_remote_url: str | None = None
_auth_token: str | None = None

# Event polling state (for remote server mode)
_event_callbacks: list[Any] = []
_event_poll_thread: threading.Thread | None = None
_event_poll_stop = threading.Event()


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


def _lock_file_path() -> Path:
    """Return the path to the server lock file."""
    return _get_display_dir() / ".server.lock"


def _scan_port_range(
    host: str = "127.0.0.1",
    port_start: int = 7741,
    port_end: int = 7750,
) -> dict[str, Any] | None:
    """Probe each port in range for a live M4 display server.

    Returns server info dict if found, None otherwise.
    """
    import urllib.request

    for port in range(port_start, port_end + 1):
        url = f"http://{host}:{port}"
        try:
            req = urllib.request.Request(f"{url}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "ok":
                    return {
                        "url": url,
                        "host": host,
                        "port": port,
                        "session_id": data.get("session_id"),
                    }
        except Exception:
            continue
    return None


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


def _ensure_run_manager() -> Any:
    """Ensure a RunManager exists for local artifact storage."""
    global _run_manager
    if _run_manager is None:
        from m4.display.run_manager import RunManager

        _run_manager = RunManager(_get_display_dir())
    return _run_manager


def _ensure_started(
    port: int = 7741,
    open_browser: bool = True,
) -> None:
    """Ensure the display server is running, starting it if needed.

    Discovery flow:
    1. If _remote_url set → health check → if healthy, return
    2. If in-process _server running → return
    3. Acquire file lock
    4. Inside lock: _discover_server() → _scan_port_range() → _start_process()
    5. Release lock
    6. Fallback in-thread server if polling fails
    """
    import fcntl

    global _server, _store, _run_manager, _session_id, _remote_url, _auth_token

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

        # Ensure run manager exists for local artifact storage
        _ensure_run_manager()

        # Acquire cross-process file lock before discovery + start
        lock_path = _lock_file_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # Try to discover an existing persistent server (PID file)
            info = _discover_server()
            if info:
                _remote_url = info["url"]
                _auth_token = info.get("token")
                _session_id = info["session_id"]
                return

            # Port-range scan as fallback (catches servers without PID files).
            # If we find a server, try to get its token from the PID file.
            # Without a token we can't push cards, so only short-circuit
            # if we have a usable connection.
            found = _scan_port_range("127.0.0.1", 7741, 7750)
            if found:
                # Re-read PID file — it may have appeared after the scan
                pid_info = _discover_server()
                if pid_info and pid_info.get("url") == found["url"]:
                    _remote_url = pid_info["url"]
                    _auth_token = pid_info.get("token")
                    _session_id = pid_info["session_id"]
                    return
                # Server exists but no token — log and let _start_process
                # pick the next available port
                logger.debug(
                    f"Found server at {found['url']} but no auth token; "
                    "starting new server on next available port"
                )

            # No server found → start a new persistent process
            _start_process(port=port, open_browser=open_browser)

        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

        # Poll for the PID file to appear (server writes it after binding)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            info = _discover_server()
            if info:
                _remote_url = info["url"]
                _auth_token = info.get("token")
                _session_id = info["session_id"]
                return
            time.sleep(0.1)

        # Fallback: start in-thread if process discovery failed
        logger.debug("Process discovery failed, falling back to in-thread server")
        from m4.display.server import DisplayServer

        if _session_id is None:
            _session_id = uuid.uuid4().hex[:12]

        _server = DisplayServer(
            run_manager=_run_manager, port=port, session_id=_session_id
        )
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
    """Stop the in-process display server and event polling."""
    global _server, _event_poll_thread

    _event_poll_stop.set()
    if _event_poll_thread is not None:
        _event_poll_thread.join(timeout=2)
        _event_poll_thread = None
    _event_callbacks.clear()

    with _lock:
        if _server is not None:
            _server.stop()
            _server = None


def stop_server() -> bool:
    """Stop a running persistent display server via POST /api/shutdown.

    Run data persists on disk. Only the PID file is cleaned up.

    Returns True if a server was stopped.
    """
    global _remote_url, _auth_token, _store, _run_manager, _session_id

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

    # Clean up PID file only — run data persists
    pid_path = _pid_file_path()
    if pid_path.exists():
        try:
            pid_path.unlink()
        except OSError:
            pass

    # Stop event polling
    _event_poll_stop.set()
    if _event_poll_thread is not None:
        _event_poll_thread.join(timeout=2)
    _event_callbacks.clear()

    # Clear module state
    session_id = info.get("session_id")
    with _lock:
        _remote_url = None
        _auth_token = None
        if _session_id == session_id:
            _store = None
            _run_manager = None
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
    wait: bool = False,
    prompt: str | None = None,
    timeout: float = 300,
    on_send: str | None = None,
) -> Any:
    """Push any displayable object to the browser.

    Returns card_id (str) by default, or DisplayResponse when wait=True.

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
        wait: If True, block until user responds in the browser.
        prompt: Question shown to the user (requires wait=True).
        timeout: Seconds to wait for response (default 300).
        on_send: Instruction for the agent when user clicks 'Send to Agent'.

    Returns:
        str (card_id) when wait=False, DisplayResponse when wait=True.
    """
    _ensure_started()

    from m4.display._types import DisplayResponse
    from m4.display.artifacts import _serialize_card
    from m4.display.renderer import render

    # Resolve the store for this card via RunManager
    store = _store  # backwards-compat fallback
    if _run_manager is not None:
        _label, store = _run_manager.get_or_create_run(run_id)
        # Use the resolved label for the card's run_id
        run_id = _label

    if replace is not None:
        # Update an existing card in place
        # Resolve store for the card being replaced
        replace_store = store
        if _run_manager is not None:
            rs = _run_manager.get_store_for_card(replace)
            if rs:
                replace_store = rs
        card = render(
            obj,
            title=title,
            description=description,
            source=source,
            run_id=run_id,
            store=replace_store,
        )
        # Update the old card's entry in the store
        updated = replace_store.update_card(
            replace,
            **{
                "title": card.title,
                "description": card.description,
                "preview": card.preview,
                "artifact_id": card.artifact_id,
                "artifact_type": card.artifact_type,
            },
        )
        # Broadcast an update (not add) so frontend re-renders in place
        update_card = updated if updated else card
        if _remote_url:
            _remote_command(
                _remote_url,
                _auth_token,
                {
                    "type": "update",
                    "card_id": replace,
                    "card": _serialize_card(update_card),
                },
            )
        elif _server is not None:
            _server.push_update(replace, update_card)
        return card.card_id

    card = render(
        obj,
        title=title,
        description=description,
        source=source,
        run_id=run_id,
        store=store,
    )

    # Register the card in RunManager's cross-run index
    if _run_manager is not None and run_id:
        dir_name = _run_manager._label_to_dir.get(run_id)
        if dir_name:
            _run_manager.register_card(card.card_id, dir_name)

    # Set interaction fields and update the stored card
    interaction_updates = {}
    if wait:
        card.response_requested = True
        interaction_updates["response_requested"] = True
        card.timeout = timeout
        interaction_updates["timeout"] = timeout
    if prompt is not None:
        card.prompt = prompt
        interaction_updates["prompt"] = prompt
    if on_send is not None:
        card.on_send = on_send
        interaction_updates["on_send"] = on_send
    if interaction_updates:
        store.update_card(card.card_id, **interaction_updates)

    if _remote_url:
        _push_remote(_serialize_card(card))
    elif _server is not None:
        _server.push_card(card)

    if not wait:
        return card.card_id

    # Blocking flow: wait for user response
    result = _wait_for_card_response(card.card_id, timeout)
    return DisplayResponse(
        action=result.get("action", "timeout"),
        card_id=card.card_id,
        message=result.get("message"),
        summary=result.get("summary", ""),
        artifact_id=result.get("artifact_id"),
        _store=store,
    )


def _wait_for_card_response(card_id: str, timeout: float) -> dict[str, Any]:
    """Wait for a browser response to a blocking card.

    Uses in-process server if available, otherwise polls remote endpoint.
    """
    if _server is not None and hasattr(_server, "wait_for_response_sync"):
        return _server.wait_for_response_sync(card_id, timeout)

    if _remote_url and _auth_token:
        return _poll_remote_response(card_id, timeout)

    return {"action": "timeout", "card_id": card_id}


def _poll_remote_response(card_id: str, timeout: float) -> dict[str, Any]:
    """Poll the remote server for a blocking response via long-poll."""
    import urllib.request

    url = f"{_remote_url}/api/response/{card_id}?timeout={timeout}"
    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {_auth_token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"action": "timeout", "card_id": card_id}


def section(title: str, run_id: str | None = None) -> None:
    """Insert a section divider in the display feed.

    Args:
        title: Section title.
        run_id: Optional run ID for grouping.
    """
    _ensure_started()

    from m4.display._types import CardDescriptor, CardType
    from m4.display.renderer import _make_card_id, _make_timestamp

    # Resolve store via RunManager if available
    store = _store
    if _run_manager is not None:
        _label, store = _run_manager.get_or_create_run(run_id)
        run_id = _label

    card = CardDescriptor(
        card_id=_make_card_id(),
        card_type=CardType.SECTION,
        title=title,
        timestamp=_make_timestamp(),
        run_id=run_id,
        preview={"title": title},
    )

    if store is not None:
        store.store_card(card)
    if _remote_url and _auth_token:
        _remote_command(
            _remote_url,
            _auth_token,
            {"type": "section", "title": title, "run_id": run_id},
        )
    elif _server is not None:
        _server.push_section(title, run_id=run_id)


def list_runs() -> list[dict[str, Any]]:
    """List all display runs with metadata and card counts.

    Returns:
        List of dicts with label, dir_name, start_time, card_count.
    """
    _ensure_run_manager()
    if _run_manager is not None:
        return _run_manager.list_runs()
    return []


def delete_run(run_id: str) -> bool:
    """Delete a display run by label.

    Args:
        run_id: The run label to delete.

    Returns:
        True if the run was deleted, False if not found.
    """
    _ensure_run_manager()
    if _run_manager is not None:
        return _run_manager.delete_run(run_id)
    return False


def clean_runs(older_than: str = "7d") -> int:
    """Remove display runs older than a given age.

    Args:
        older_than: Age string (e.g., '7d', '24h', '0d' for all).

    Returns:
        Number of runs removed.
    """
    _ensure_run_manager()
    if _run_manager is not None:
        return _run_manager.clean_runs(older_than)
    return 0


def export(
    path: str,
    format: str = "html",
    run_id: str | None = None,
) -> str:
    """Export a run (or all runs) as a self-contained artifact.

    Args:
        path: Output file path.
        format: "html" (self-contained) or "json" (card index + artifacts zip).
        run_id: Specific run label to export, or None for all runs.

    Returns:
        Path to the written file.

    Raises:
        ValueError: If format is not "html" or "json".
    """
    if format not in ("html", "json"):
        raise ValueError(
            f"Unsupported export format: {format!r} (use 'html' or 'json')"
        )

    _ensure_run_manager()
    if _run_manager is None:
        raise RuntimeError("No run manager available for export")

    from m4.display.export import export_html, export_json

    if format == "html":
        result = export_html(_run_manager, path, run_id=run_id)
    else:
        result = export_json(_run_manager, path, run_id=run_id)

    return str(result)


def on_event(callback: Any) -> None:
    """Register a callback for UI events (row click, point select, etc.).

    The callback receives DisplayEvent instances with event_type, card_id,
    and payload fields. Common event types: 'row_click', 'point_select',
    'point_click'.

    Works in both in-process and remote server modes. For remote servers,
    starts a background polling thread that fetches events via REST.

    Args:
        callback: Function that receives DisplayEvent instances.
    """
    global _event_poll_thread

    _ensure_started()
    _event_callbacks.append(callback)

    if _server is not None and hasattr(_server, "register_event_callback"):
        # In-process server: register directly
        _server.register_event_callback(callback)
    elif _remote_url is not None:
        # Remote server: start polling thread if not already running
        if _event_poll_thread is None or not _event_poll_thread.is_alive():
            _event_poll_stop.clear()
            _event_poll_thread = threading.Thread(
                target=_poll_remote_events, daemon=True
            )
            _event_poll_thread.start()


def _poll_remote_events() -> None:
    """Background thread that polls a remote server for UI events."""
    import urllib.request

    from m4.display._types import DisplayEvent

    while not _event_poll_stop.is_set():
        try:
            url = f"{_remote_url}/api/events"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {_auth_token}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                events = json.loads(resp.read())
            for evt_data in events:
                event = DisplayEvent(
                    event_type=evt_data.get("event_type", ""),
                    card_id=evt_data.get("card_id", ""),
                    payload=evt_data.get("payload", {}),
                )
                for cb in _event_callbacks:
                    try:
                        cb(event)
                    except Exception:
                        pass
        except Exception:
            pass
        _event_poll_stop.wait(0.5)


def pending_requests() -> list:
    """Poll for user-initiated requests from the browser.

    Returns a list of DisplayRequest objects. Each request has:
    - request_id, card_id, prompt, artifact_id, timestamp, instruction
    - .data() method to load the selected DataFrame
    - .acknowledge() method to mark as handled

    Returns:
        List of DisplayRequest objects.
    """
    from m4.display._types import DisplayRequest

    _ensure_started()

    if _run_manager is not None:
        raw = _run_manager.list_requests(pending_only=True)
        ack_cb = _run_manager.acknowledge_request
        # Use first available store for artifact loading
        first_store = _store
        if first_store is None:
            stores = list(_run_manager._stores.values())
            first_store = stores[0] if stores else None
    elif _store is not None:
        raw = _store.list_requests(pending_only=True)
        ack_cb = _store.acknowledge_request
        first_store = _store
    else:
        return []

    requests = []
    for r in raw:
        # Try to find the right store for this request's artifact
        req_store = first_store
        if _run_manager and r.get("card_id"):
            card_store = _run_manager.get_store_for_card(r["card_id"])
            if card_store:
                req_store = card_store

        req = DisplayRequest(
            request_id=r["request_id"],
            card_id=r.get("card_id", ""),
            prompt=r.get("prompt", ""),
            summary=r.get("summary", ""),
            artifact_id=r.get("artifact_id"),
            timestamp=r.get("timestamp", ""),
            instruction=r.get("instruction"),
            _store=req_store,
            _ack_callback=ack_cb,
        )
        requests.append(req)
    return requests


def get_selection(artifact_id: str) -> Any:
    """Load a selection DataFrame from the artifact store by ID.

    Searches across all run stores and the display-level artifacts dir.

    Args:
        artifact_id: The artifact ID returned in a DisplayResponse or
            DisplayRequest.

    Returns:
        pd.DataFrame if found, None otherwise.
    """
    import pandas as pd

    # Search run_manager stores
    if _run_manager is not None:
        for store in _run_manager._stores.values():
            path = store._artifacts_dir / f"{artifact_id}.parquet"
            if path.exists():
                return pd.read_parquet(path)
        # Check display-level artifacts dir
        display_artifacts = _run_manager.display_dir / "artifacts"
        path = display_artifacts / f"{artifact_id}.parquet"
        if path.exists():
            return pd.read_parquet(path)

    # Legacy fallback
    if _store is not None:
        path = _store._artifacts_dir / f"{artifact_id}.parquet"
        if path.exists():
            return pd.read_parquet(path)

    return None
