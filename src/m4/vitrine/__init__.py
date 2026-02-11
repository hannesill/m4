"""vitrine: Visualization backend for code execution agents.

Provides a local display server that pushes visualizations to a browser tab.
Agents call show() to render DataFrames, charts, markdown, and more.

Quick Start:
    from m4.vitrine import show

    show(df, title="Demographics")
    show("## Key Finding\\nMortality is 23%")
    show({"patients": 4238, "mortality": "23%"})
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from m4.vitrine._types import (
    CardDescriptor,
    DisplayEvent,
    DisplayHandle,
    DisplayResponse,
    Form,
    Question,
)

__all__ = [
    "DisplayEvent",
    "DisplayHandle",
    "DisplayResponse",
    "Form",
    "Question",
    "clean_studies",
    "delete_study",
    "export",
    "get_card",
    "get_selection",
    "list_annotations",
    "list_studies",
    "on_event",
    "register_output_dir",
    "register_session",
    "section",
    "server_status",
    "set_status",
    "show",
    "start",
    "stop",
    "stop_server",
    "study_context",
    "wait_for",
]

logger = logging.getLogger(__name__)

# Module-level state (thread-safe via _lock)
_lock = threading.Lock()
_server: Any = None  # DisplayServer | None
_store: Any = None  # ArtifactStore | None (backwards-compat)
_study_manager: Any = None  # StudyManager | None
_current_study: str | None = None
_session_id: str | None = None
_remote_url: str | None = None
_auth_token: str | None = None

# Event polling state (for remote server mode)
_event_callbacks: list[Any] = []
_event_poll_thread: threading.Thread | None = None
_event_poll_stop = threading.Event()


def _get_vitrine_dir() -> Path:
    """Resolve the vitrine directory at {project_root}/.vitrine/.

    Performs one-time migration from the old m4_data/vitrine/ location.
    """
    try:
        from m4.config import _PROJECT_ROOT

        vitrine_dir = _PROJECT_ROOT / ".vitrine"
    except Exception:
        import tempfile

        vitrine_dir = Path(tempfile.gettempdir()) / ".vitrine"

    _migrate_if_needed(vitrine_dir)
    return vitrine_dir


def _migrate_if_needed(vitrine_dir: Path) -> None:
    """Migrate storage from old layout to new layout if needed."""
    # 1. Move m4_data/vitrine/ → .vitrine/ (same parent)
    try:
        from m4.config import _PROJECT_DATA_DIR

        old_dir = _PROJECT_DATA_DIR / "vitrine"
    except Exception:
        old_dir = None

    if old_dir and old_dir.exists() and not vitrine_dir.exists():
        try:
            shutil.move(str(old_dir), str(vitrine_dir))
            logger.debug(f"Migrated {old_dir} → {vitrine_dir}")
        except OSError:
            logger.debug(f"Failed to migrate {old_dir} → {vitrine_dir}")
            return

    if not vitrine_dir.exists():
        return

    # 2. Rename runs/ → studies/
    old_runs_dir = vitrine_dir / "runs"
    new_studies_dir = vitrine_dir / "studies"
    if old_runs_dir.exists() and not new_studies_dir.exists():
        try:
            old_runs_dir.rename(new_studies_dir)
            logger.debug("Migrated runs/ → studies/")
        except OSError:
            pass

    # 3. Remove legacy registry files (runs.json / studies.json)
    for legacy in ("runs.json", "studies.json"):
        legacy_path = vitrine_dir / legacy
        if legacy_path.exists():
            try:
                legacy_path.unlink()
                logger.debug(f"Removed legacy {legacy}")
            except OSError:
                pass


def _pid_file_path() -> Path:
    """Return the path to the server PID file."""
    return _get_vitrine_dir() / ".server.json"


def _lock_file_path() -> Path:
    """Return the path to the server lock file."""
    return _get_vitrine_dir() / ".server.lock"


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
    host = info.get("host", "127.0.0.1")
    port = info.get("port")

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

    # Build an API-safe URL from host:port.  The "url" field uses
    # vitrine.localhost which Python's urllib can't always resolve,
    # so all programmatic access must go through 127.0.0.1.
    api_url = f"http://{host}:{port}" if port else url
    if not _health_check(api_url, session_id):
        logger.debug(f"Health check failed for {api_url}, removing stale PID file")
        try:
            pid_path.unlink()
        except OSError:
            pass
        return None

    info["api_url"] = api_url
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
        logger.warning(f"Remote command failed for {url}")
        return False


def _get_session_dir() -> Path:
    """Determine the session directory for artifact storage."""
    return _get_vitrine_dir()


def _ensure_study_manager() -> Any:
    """Ensure a StudyManager exists for local artifact storage."""
    global _study_manager
    if _study_manager is None:
        from m4.vitrine.study_manager import StudyManager

        _study_manager = StudyManager(_get_vitrine_dir())
    return _study_manager


def register_session(study: str | None = None) -> None:
    """Associate the current Claude Code session with a study.

    If CLAUDE_SESSION_ID is in the environment, stores it in the
    study's meta.json. Called automatically on first show() for a study.
    No-op if the env var is not set.
    """
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        return
    sm = _ensure_study_manager()
    if sm is None:
        return
    label = study or _current_study
    if label is None:
        return
    sm.set_session_id(label, session_id)


def _ensure_started(
    port: int = 7741,
    open_browser: bool = True,
) -> None:
    """Ensure the display server is running, starting it if needed.

    Discovery flow:
    1. If _remote_url set -> health check -> if healthy, return
    2. If in-process _server running -> return
    3. Acquire file lock
    4. Inside lock: _discover_server() -> _start_process()
    5. Release lock
    6. Fallback in-thread server if polling fails
    """
    import fcntl

    global _server, _store, _study_manager, _session_id, _remote_url, _auth_token

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

        # Ensure study manager exists for local artifact storage
        _ensure_study_manager()

        # Acquire cross-process file lock before discovery + start
        lock_path = _lock_file_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # Try to discover an existing persistent server (PID file).
            # The PID file is the sole authority — no port scanning.
            # Port scanning would risk connecting to a different project's
            # server when multiple projects run vitrine concurrently.
            info = _discover_server()
            if info:
                _remote_url = info.get("api_url", info["url"])
                _auth_token = info.get("token")
                _session_id = info["session_id"]
                return

            # No server found -> start a new persistent process
            _start_process(port=port, open_browser=open_browser)

        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

        # Poll for the PID file to appear (server writes it after binding)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            info = _discover_server()
            if info:
                _remote_url = info.get("api_url", info["url"])
                _auth_token = info.get("token")
                _session_id = info["session_id"]
                return
            time.sleep(0.1)

        # Fallback: start in-thread if process discovery failed
        logger.debug("Process discovery failed, falling back to in-thread server")
        from m4.vitrine.server import DisplayServer

        if _session_id is None:
            _session_id = uuid.uuid4().hex[:12]

        _server = DisplayServer(
            study_manager=_study_manager, port=port, session_id=_session_id
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
        "m4.vitrine.server",
        "--port",
        str(port),
    ]
    if not open_browser:
        cmd.append("--no-open")

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop() -> None:
    """Stop the display server and event polling.

    Stops an in-process server if present. If no in-process server is active
    but a persistent server is connected/discoverable, attempts to stop it.
    """
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
            return

    # No in-process server. If we have a remote connection hint, try stopping
    # the persistent server as well.
    with _lock:
        url = _remote_url

    if url is not None:
        stop_server()


def stop_server() -> bool:
    """Stop a running persistent display server via POST /api/shutdown.

    Study data persists on disk. Only the PID file is cleaned up.

    Returns True if a server was stopped.
    """
    global _remote_url, _auth_token, _store, _study_manager, _session_id
    global _event_poll_thread

    info = _discover_server()
    if not info:
        return False

    url = info.get("api_url", info["url"])
    token = info.get("token")

    shutdown_requested = False
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
            shutdown_requested = True
    except Exception:
        logger.debug(f"Failed to request shutdown for {url}")

    # Wait for process to exit if we have a PID; otherwise fall back to health.
    pid = info.get("pid")
    session_id = info.get("session_id")
    stopped = False
    if pid:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                stopped = True
                break
            time.sleep(0.1)
        if not stopped:
            stopped = not _health_check(url, session_id)
    else:
        stopped = not _health_check(url, session_id)

    # If still alive, keep PID metadata so status/stop can retry later.
    if not stopped:
        if shutdown_requested:
            logger.debug(f"Shutdown requested but server still healthy at {url}")
        return False

    # Clean up PID file only -- study data persists.
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
        _event_poll_thread = None
    _event_callbacks.clear()

    # Clear module state
    with _lock:
        _remote_url = None
        _auth_token = None
        if _session_id == session_id:
            _store = None
            _study_manager = None
            _session_id = None

    return True


def server_status() -> dict[str, Any] | None:
    """Return info about a running display server for this project, or None.

    Uses the PID file as the sole authority. No port scanning — that would
    risk reporting a different project's server as ours.
    """
    return _discover_server()


def _push_remote(card_data: dict[str, Any]) -> bool:
    """Push a card to the remote server. Returns True on success."""
    global _remote_url, _auth_token

    with _lock:
        url, token = _remote_url, _auth_token

    if url is None or token is None:
        return False

    ok = _remote_command(url, token, {"type": "card", "card": card_data})
    if not ok:
        # Retry once after re-discovery
        with _lock:
            _remote_url = None
            _auth_token = None
        info = _discover_server()
        if info:
            with _lock:
                _remote_url = info.get("api_url", info["url"])
                _auth_token = info.get("token")
                url, token = _remote_url, _auth_token
            ok = _remote_command(url, token, {"type": "card", "card": card_data})
            if not ok:
                logger.warning("Remote card push failed after re-discovery")
        else:
            logger.warning("Remote card push failed and server re-discovery failed")
    return ok


def show(
    obj: Any,
    title: str | None = None,
    description: str | None = None,
    *,
    study: str | None = None,
    source: str | None = None,
    replace: str | None = None,
    position: str | None = None,
    wait: bool = False,
    prompt: str | None = None,
    timeout: float = 600,
    actions: list[str] | None = None,
    controls: list[Any] | None = None,
) -> Any:
    """Push any displayable object to the browser.

    Returns a string-like card handle by default, or DisplayResponse when
    wait=True.

    Supported types:
    - pd.DataFrame -> interactive table (artifact-backed, paged)
    - plotly Figure -> interactive chart
    - matplotlib Figure -> static chart (SVG)
    - str -> markdown card
    - dict -> formatted key-value card
    - Form -> structured input card (freezes on confirm)
    - Other -> repr() fallback

    Auto-starts the display server on first call.

    Args:
        obj: Python object to display.
        title: Card title shown in header.
        description: Subtitle or context line.
        study: Group cards into a named study (for filtering).
        source: Provenance string (e.g., table name, query).
        replace: Card ID to update instead of appending.
        position: "top" to prepend instead of append.
        wait: If True, block until user responds in the browser.
        prompt: Question shown to the user (requires wait=True).
        timeout: Seconds to wait for response (default 600).
        actions: Named action buttons for decision cards. When provided,
            replaces the default Confirm button (requires wait=True).
        controls: List of form field primitives to attach as controls to
            a table or chart card. Creates a hybrid data+controls card.

    Returns:
        DisplayHandle (str subclass) when wait=False, DisplayResponse when
        wait=True.
    """
    # Wrap bare Question in a Form automatically
    if isinstance(obj, Question):
        obj = Form([obj])

    # Forms are always decision cards — force wait=True
    if isinstance(obj, Form):
        wait = True
        if prompt is None:
            prompt = title
    if controls:
        wait = True

    _ensure_started()

    from m4.vitrine.artifacts import _serialize_card
    from m4.vitrine.renderer import render

    # Resolve the store for this card via StudyManager
    store = _store  # backwards-compat fallback
    if _study_manager is not None:
        _label, store = _study_manager.get_or_create_study(study)
        # Use the resolved label for the card's study
        study = _label
        # Auto-register Claude session ID with this study
        register_session(study)

    if replace is not None:
        # Update an existing card in place
        # Resolve store for the card being replaced
        replace_store = store
        if _study_manager is not None:
            rs = _study_manager.get_store_for_card(replace)
            if rs:
                replace_store = rs
        card = render(
            obj,
            title=title,
            description=description,
            source=source,
            study=study,
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
        study=study,
        store=store,
    )

    # Attach controls to the card preview for hybrid data+controls cards
    if controls:
        card.preview["controls"] = [c.to_dict() for c in controls]
        store.update_card(card.card_id, preview=card.preview)

    # Register the card in StudyManager's cross-study index
    if _study_manager is not None and study:
        dir_name = _study_manager._label_to_dir.get(study)
        if dir_name:
            _study_manager.register_card(card.card_id, dir_name)

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
    if actions is not None:
        card.actions = actions
        interaction_updates["actions"] = actions
    if interaction_updates:
        store.update_card(card.card_id, **interaction_updates)

    if _remote_url:
        _push_remote(_serialize_card(card))
    elif _server is not None:
        _server.push_card(card)

    if not wait:
        return DisplayHandle(card.card_id, url=_study_url(study), study=study)

    # Signal in terminal that we're waiting for browser input
    _wait_label = title or prompt or "decision card"
    _wait_url = _study_url(study)
    if _wait_url:
        print(f'Waiting for response on "{_wait_label}" in vitrine → {_wait_url}')
    else:
        print(f'Waiting for response on "{_wait_label}" in vitrine')

    # Blocking flow: wait for user response
    result = _wait_for_card_response(card.card_id, timeout)
    action = result.get("action", "timeout")

    # Terminal notification so the agent (and researcher) sees the outcome
    if action == "timeout":
        print(
            f'Timed out waiting for "{_wait_label}" '
            f'-- use wait_for("{card.card_id}") to re-attach'
        )
    else:
        print(f'Response received: {action} on "{_wait_label}"')

    return DisplayResponse(
        action=action,
        card_id=card.card_id,
        message=result.get("message"),
        summary=result.get("summary", ""),
        artifact_id=result.get("artifact_id"),
        values=result.get("values", {}),
        _store=store,
    )


def _wait_for_card_response(card_id: str, timeout: float) -> dict[str, Any]:
    """Wait for a browser response to a blocking card.

    Uses in-process server if available, otherwise polls remote endpoint.
    """
    with _lock:
        server, url, token = _server, _remote_url, _auth_token

    if server is not None and hasattr(server, "wait_for_response_sync"):
        return server.wait_for_response_sync(card_id, timeout)

    if url and token:
        return _poll_remote_response(card_id, timeout)

    return {"action": "timeout", "card_id": card_id}


def _study_url(study: str | None) -> str | None:
    """Build a browser URL deep link for a study, when available."""
    if not study:
        return None
    from urllib.parse import quote

    with _lock:
        url, server = _remote_url, _server

    if url:
        return f"{url}/#study={quote(study, safe='')}"
    if server is not None:
        from m4.vitrine.server import _DISPLAY_HOST

        port = getattr(server, "port", 7741)
        return f"http://{_DISPLAY_HOST}:{port}/#study={quote(study, safe='')}"
    return None


def _poll_remote_response(card_id: str, timeout: float) -> dict[str, Any]:
    """Poll the remote server for a blocking response via long-poll."""
    import urllib.error
    import urllib.request

    with _lock:
        url, token = _remote_url, _auth_token

    poll_url = f"{url}/api/response/{card_id}?timeout={timeout}"
    try:
        req = urllib.request.Request(
            poll_url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        logger.warning(f"Remote response poll HTTP error {e.code} for card {card_id}")
        return {"action": "error", "card_id": card_id}
    except urllib.error.URLError as e:
        logger.warning(f"Remote response poll connection error for card {card_id}: {e}")
        return {"action": "timeout", "card_id": card_id}
    except Exception:
        return {"action": "timeout", "card_id": card_id}


def wait_for(card_id: str, timeout: float = 600) -> DisplayResponse:
    """Re-attach to a previously posted blocking card and wait for its response.

    Use this after a ``show(..., wait=True)`` call has timed out. If the
    researcher has already responded (after the original timeout expired),
    the stored response is returned immediately. Otherwise the card's
    response UI is re-enabled in the browser and the call blocks until the
    researcher responds or the new timeout expires.

    Args:
        card_id: Card identifier (from ``DisplayResponse.card_id`` or
            ``DisplayHandle``).
        timeout: Seconds to wait for response (default 600).

    Returns:
        DisplayResponse with the researcher's action, message, and values.
    """
    from m4.vitrine.artifacts import _serialize_card

    # Strip slug suffix (e.g. "a1b2c3-protocol" → "a1b2c3")
    id_prefix = card_id.split("-")[0]

    # Look up the card
    card = get_card(id_prefix)
    if card is None:
        return DisplayResponse(
            action="error",
            card_id=card_id,
            message=f"Card not found: {card_id}",
        )

    # If the researcher already responded (after the original timeout),
    # return the stored response immediately.
    if card.response_action is not None:
        _label = card.title or card.prompt or card_id
        print(f'Response already received: {card.response_action} on "{_label}"')
        # Find the store for _store parameter
        _ensure_study_manager()
        store = None
        if _study_manager is not None:
            store = _study_manager.get_store_for_card(id_prefix)
        if store is None:
            store = _store
        return DisplayResponse(
            action=card.response_action,
            card_id=card.card_id,
            message=card.response_message,
            summary=card.response_summary or "",
            artifact_id=card.response_artifact_id,
            values=card.response_values or {},
            _store=store,
        )

    # No response yet — re-enable the response UI and wait again.
    _ensure_study_manager()
    store = None
    if _study_manager is not None:
        store = _study_manager.get_store_for_card(id_prefix)
    if store is None:
        store = _store

    # Update card metadata to re-enable blocking
    if store is not None:
        store.update_card(
            card.card_id,
            response_requested=True,
            timeout=timeout,
        )
        card.response_requested = True
        card.timeout = timeout

    # Push update to frontend so it re-shows the response UI
    with _lock:
        server, url, token = _server, _remote_url, _auth_token

    if url and token:
        _remote_command(
            url,
            token,
            {
                "type": "update",
                "card_id": card.card_id,
                "card": _serialize_card(card),
            },
        )
    elif server is not None:
        server.push_update(card.card_id, card)

    _label = card.title or card.prompt or card_id
    print(f'Re-waiting for response on "{_label}" in vitrine')

    # Block again
    result = _wait_for_card_response(card.card_id, timeout)
    action = result.get("action", "timeout")

    if action == "timeout":
        print(
            f'Timed out waiting for "{_label}" '
            f'-- use wait_for("{card.card_id}") to re-attach'
        )
    else:
        print(f'Response received: {action} on "{_label}"')

    return DisplayResponse(
        action=action,
        card_id=card.card_id,
        message=result.get("message"),
        summary=result.get("summary", ""),
        artifact_id=result.get("artifact_id"),
        values=result.get("values", {}),
        _store=store,
    )


def section(title: str, study: str | None = None) -> None:
    """Insert a section divider in the display feed.

    Args:
        title: Section title.
        study: Optional study name for grouping.
    """
    _ensure_started()

    from m4.vitrine._types import CardDescriptor, CardType
    from m4.vitrine.renderer import _make_card_id, _make_timestamp

    # Resolve store via StudyManager if available
    store = _store
    if _study_manager is not None:
        _label, store = _study_manager.get_or_create_study(study)
        study = _label

    card = CardDescriptor(
        card_id=_make_card_id(),
        card_type=CardType.SECTION,
        title=title,
        timestamp=_make_timestamp(),
        study=study,
        preview={"title": title},
    )

    if store is not None:
        store.store_card(card)
    if _remote_url and _auth_token:
        _remote_command(
            _remote_url,
            _auth_token,
            {"type": "section", "title": title, "study": study},
        )
    elif _server is not None:
        _server.push_section(title, study=study)


def set_status(message: str) -> None:
    """Set the agent status bar message in the browser.

    Displays a short status message (e.g., "Analyzing cohort...",
    "Waiting for your response") in the vitrine header bar.
    Pass an empty string to clear the status.

    Args:
        message: Status text to display.
    """
    _ensure_started()

    if _remote_url and _auth_token:
        _remote_command(
            _remote_url, _auth_token, {"type": "status", "message": message}
        )
    elif _server is not None and hasattr(_server, "push_status"):
        _server.push_status(message)


def study_context(study: str) -> dict[str, Any]:
    """Get a structured context summary for agent re-orientation.

    Returns study metadata, cards, decisions made, pending responses,
    and current selections. Useful at the start of a new conversation
    turn to understand what has happened so far.

    Args:
        study: The study label to summarize.

    Returns:
        Dict with study, card_count, cards, decisions_made,
        pending_responses, and current_selections.
    """
    _ensure_study_manager()
    if _study_manager is not None:
        ctx = _study_manager.build_context(study)
        # In-process enrichment with live selection + pending response state
        if _server is not None:
            card_ids = [c.get("card_id", "") for c in ctx.get("cards", [])]
            current_selections = {}
            for cid in card_ids:
                sel = _server._selections.get(cid, [])
                if sel:
                    current_selections[cid] = sel
            ctx["current_selections"] = current_selections

            pending_ids = {
                item.get("card_id", "")
                for item in ctx.get("pending_responses", [])
                if item.get("card_id")
            }
            for cid in card_ids:
                pending = getattr(_server, "_pending_responses", {})
                fut = pending.get(cid) if isinstance(pending, dict) else None
                if fut and not fut.done() and cid not in pending_ids:
                    ctx.setdefault("pending_responses", []).append(
                        {"card_id": cid, "title": None, "prompt": None}
                    )
            ctx["decisions"] = ctx.get("pending_responses", [])

        # If remote server, try to get enriched version with selection counts
        with _lock:
            url = _remote_url

        if url:
            try:
                import urllib.request

                ctx_url = f"{url}/api/studies/{study}/context"
                req = urllib.request.Request(ctx_url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read())
            except Exception:
                pass

        return ctx
    return {
        "study": study,
        "card_count": 0,
        "cards": [],
        "decisions": [],
        "pending_responses": [],
        "decisions_made": [],
        "current_selections": {},
    }


def list_studies() -> list[dict[str, Any]]:
    """List all studies with metadata and card counts.

    Returns:
        List of dicts with label, dir_name, start_time, card_count.
    """
    _ensure_study_manager()
    if _study_manager is not None:
        return _study_manager.list_studies()
    return []


def delete_study(study: str) -> bool:
    """Delete a study by label.

    Args:
        study: The study label to delete.

    Returns:
        True if the study was deleted, False if not found.
    """
    _ensure_study_manager()
    if _study_manager is not None:
        return _study_manager.delete_study(study)
    return False


def clean_studies(older_than: str = "7d") -> int:
    """Remove studies older than a given age.

    Args:
        older_than: Age string (e.g., '7d', '24h', '0d' for all).

    Returns:
        Number of studies removed.
    """
    _ensure_study_manager()
    if _study_manager is not None:
        return _study_manager.clean_studies(older_than)
    return 0


def export(
    path: str,
    format: str = "html",
    study: str | None = None,
) -> str:
    """Export a study (or all studies) as a self-contained artifact.

    Args:
        path: Output file path.
        format: "html" (self-contained) or "json" (card index + artifacts zip).
        study: Specific study label to export, or None for all studies.

    Returns:
        Path to the written file.

    Raises:
        ValueError: If format is not "html" or "json".
    """
    if format not in ("html", "json"):
        raise ValueError(
            f"Unsupported export format: {format!r} (use 'html' or 'json')"
        )

    _ensure_study_manager()
    if _study_manager is None:
        raise RuntimeError("No study manager available for export")

    from m4.vitrine.export import export_html, export_json

    if format == "html":
        result = export_html(_study_manager, path, study=study)
    else:
        result = export_json(_study_manager, path, study=study)

    return str(result)


def register_output_dir(
    path: str | Path | None = None,
    study: str | None = None,
) -> Path:
    """Register an output directory for a study.

    If path is None, creates and returns ``{study_dir}/output/``
    (self-contained alongside the study's cards). If path is a
    string/Path, stores it as an external reference and returns it.

    Args:
        path: External directory path, or None for self-contained.
        study: Study label. Creates the study if it doesn't exist.

    Returns:
        Path to the output directory (created if needed).
    """
    sm = _ensure_study_manager()
    label, _store = sm.get_or_create_study(study)
    return sm.register_output_dir(label, path)


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

    with _lock:
        server, url = _server, _remote_url

    if server is not None and hasattr(server, "register_event_callback"):
        # In-process server: register directly
        server.register_event_callback(callback)
    elif url is not None:
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

    while not _event_poll_stop.is_set():
        with _lock:
            url, token = _remote_url, _auth_token

        if not url or not token:
            _event_poll_stop.wait(0.5)
            continue

        try:
            events_url = f"{url}/api/events"
            req = urllib.request.Request(
                events_url,
                headers={"Authorization": f"Bearer {token}"},
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


def get_card(card_id: str) -> CardDescriptor | None:
    """Look up a card descriptor by ID or prefix.

    Accepts full 12-char IDs, short prefixes, or slug-suffixed
    references like ``a1b2c3-my-title`` (the slug is stripped).

    Args:
        card_id: Card identifier, prefix, or slug-suffixed reference.

    Returns:
        CardDescriptor or None.
    """
    # Strip slug suffix (everything after first dash)
    id_prefix = card_id.split("-")[0]

    _ensure_study_manager()
    if _study_manager is not None:
        # Try the cross-study index first (exact match)
        store = _study_manager.get_store_for_card(id_prefix)
        if store:
            for card in store.list_cards():
                if card.card_id.startswith(id_prefix):
                    return card
        # Prefix didn't hit the index — scan all cards
        for card in _study_manager.list_all_cards():
            if card.card_id.startswith(id_prefix):
                return card
    # Fallback to legacy store
    if _store is not None:
        for card in _store.list_cards():
            if card.card_id.startswith(id_prefix):
                return card
    return None


def list_annotations(
    study: str | None = None,
) -> list[dict[str, Any]]:
    """List all annotations, optionally filtered by study.

    Each returned dict contains the annotation fields (id, text, timestamp)
    plus ``card_id`` and ``card_title`` for context.

    Args:
        study: If provided, only include annotations from this study.

    Returns:
        List of annotation dicts, newest first.
    """
    _ensure_study_manager()
    cards: list[CardDescriptor] = []
    if _study_manager is not None:
        cards = _study_manager.list_all_cards(study=study)
    elif _store is not None:
        cards = _store.list_cards()

    annotations: list[dict[str, Any]] = []
    for card in cards:
        for ann in card.annotations:
            annotations.append(
                {
                    **ann,
                    "card_id": card.card_id,
                    "card_title": card.title,
                }
            )

    annotations.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
    return annotations


def get_selection(card_id: str) -> Any:
    """Get the currently selected rows for a table card.

    Reads the browser's checkbox/chart selection state that is passively
    synced to the server via WebSocket. Returns the matching rows as a
    DataFrame.

    Args:
        card_id: The card_id of the table or chart card.

    Returns:
        pd.DataFrame of selected rows, or empty DataFrame if nothing selected.
    """
    import pandas as pd

    _ensure_started()

    # In-process server: read directly from memory
    if _server is not None and hasattr(_server, "_selections"):
        indices = _server._selections.get(card_id, [])
        if not indices:
            return pd.DataFrame()
        # Find the store that holds this card's parquet
        store = None
        if _study_manager is not None:
            store = _study_manager.get_store_for_card(card_id)
        if store is None:
            store = _store
        if store is None:
            return pd.DataFrame()
        path = store._artifacts_dir / f"{card_id}.parquet"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(path)
        valid = [i for i in indices if 0 <= i < len(df)]
        if not valid:
            return pd.DataFrame()
        return df.iloc[valid].reset_index(drop=True)

    # Remote server: use REST endpoint
    with _lock:
        url = _remote_url

    if url:
        try:
            import urllib.request

            sel_url = f"{url}/api/table/{card_id}/selection"
            req = urllib.request.Request(sel_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            if data.get("rows") and data.get("columns"):
                return pd.DataFrame(data["rows"], columns=data["columns"])
        except Exception:
            logger.warning(f"Failed to fetch selection for card {card_id} from remote")

    return pd.DataFrame()
