"""Display server: Starlette + WebSocket + REST for the display pipeline.

Runs in a background thread (default) or separate process, serving a browser
UI that renders cards pushed from the Python API. Uses Starlette (available
via fastmcp transitive dependency) instead of FastAPI.

Endpoints:
    GET  /                               → index.html
    GET  /static/{path}                  → static files (vendor JS, etc.)
    WS   /ws                             → bidirectional display channel
    GET  /api/cards?study=...             → list card descriptors
    GET  /api/table/{card_id}            → table page (offset, limit, sort)
    GET  /api/artifact/{card_id}         → raw artifact
    GET  /api/session                    → session metadata
    GET  /api/health                     → health check (returns session_id)
    POST /api/command                    → unified command endpoint (auth required)
    POST /api/shutdown                   → graceful shutdown (auth required)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from m4.vitrine._types import CardDescriptor
from m4.vitrine.artifacts import ArtifactStore, _serialize_card
from m4.vitrine.dispatch import (
    DispatchInfo,
    _dispatch_watchdog,
    _is_pid_alive,
    cancel_agent,
    cleanup_dispatches,
    create_agent_card,
    get_agent_status,
    reconcile_orphaned_agents,
    run_agent,
)
from m4.vitrine.study_manager import StudyManager

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 7741
_MAX_PORT = 7750
_DISPLAY_HOST = "vitrine.localhost"


def _check_health(url: str, session_id: str | None = None) -> bool:
    """GET /api/health and optionally validate session_id matches."""
    from m4.vitrine._utils import health_check

    return health_check(url, session_id=session_id)


def _get_vitrine_dir() -> Path:
    """Resolve the vitrine directory at {project_root}/.vitrine/."""
    from m4.vitrine._utils import get_vitrine_dir

    return get_vitrine_dir()


class DisplayServer:
    """WebSocket + REST server for the display pipeline.

    Manages the Starlette app, WebSocket connections, and study manager.
    Designed to run in a background thread via ``start()``.

    Args:
        store: ArtifactStore for persisting and reading artifacts (legacy).
        study_manager: StudyManager for study-centric storage (preferred).
        port: Port to bind to (auto-discovers if taken).
        host: Host to bind to (default: 127.0.0.1 for security).
    """

    def __init__(
        self,
        store: ArtifactStore | None = None,
        port: int = _DEFAULT_PORT,
        host: str = "127.0.0.1",
        token: str | None = None,
        session_id: str | None = None,
        study_manager: StudyManager | None = None,
    ) -> None:
        self.study_manager = study_manager
        # Backwards compat: if only store is passed, wrap it
        self.store = store
        self.host = host
        self.port = port
        self.token = token
        self.session_id = session_id or (store.session_id if store else "display")
        self._pid_path: Path | None = None
        self._connections: list[WebSocket] = []
        self._lock = threading.Lock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

        # Agent-human interaction state
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._event_callbacks: list[Callable] = []
        self._event_queue: list[dict[str, Any]] = []
        self._selections: dict[str, list[int]] = {}  # card_id -> selected indices

        # Selection persistence
        vitrine_dir = study_manager.display_dir if study_manager else None
        self._selections_path: Path | None = (
            vitrine_dir / "selections.json" if vitrine_dir else None
        )
        self._load_selections()
        self._selection_save_timer: threading.Timer | None = None

        # Agent dispatch state
        self._dispatches: dict[str, DispatchInfo] = {}
        self._watchdog_task: asyncio.Task | None = None

        # Fix agent cards orphaned by previous server crashes/restarts
        fixed = reconcile_orphaned_agents(self)
        if fixed:
            logger.info(f"Reconciled {fixed} orphaned agent card(s)")

        # Server start time for health endpoint
        self._started_at = datetime.now(timezone.utc)

        self._app = self._build_app()

    def _load_selections(self) -> None:
        """Load persisted selections from disk."""
        if self._selections_path and self._selections_path.exists():
            try:
                data = json.loads(self._selections_path.read_text())
                if isinstance(data, dict):
                    self._selections = data
            except (json.JSONDecodeError, OSError):
                pass

    def _save_selections(self) -> None:
        """Save selections to disk (debounced — max 1 write/sec)."""
        if not self._selections_path:
            return
        try:
            with self._lock:
                snapshot = dict(self._selections)
            self._selections_path.write_text(json.dumps(snapshot, default=str))
        except OSError:
            logger.debug("Failed to persist selections to disk")

    def _schedule_save_selections(self) -> None:
        """Schedule a debounced selection save (max 1 write/sec)."""
        if self._selection_save_timer is not None:
            self._selection_save_timer.cancel()
        self._selection_save_timer = threading.Timer(1.0, self._save_selections)
        self._selection_save_timer.daemon = True
        self._selection_save_timer.start()

    def _build_app(self) -> Starlette:
        """Build the Starlette application with all routes."""
        routes = [
            Route("/", self._index),
            Route("/api/health", self._api_health),
            Route("/api/cards", self._api_cards),
            Route("/api/table/{card_id}/selection", self._api_table_selection),
            Route("/api/table/{card_id}/stats", self._api_table_stats),
            Route("/api/table/{card_id}/export", self._api_table_export),
            Route("/api/table/{card_id}", self._api_table),
            Route("/api/card/{card_id}", self._api_card),
            Route("/api/artifact/{card_id}", self._api_artifact),
            Route("/api/session", self._api_session),
            Route("/api/command", self._api_command, methods=["POST"]),
            Route("/api/shutdown", self._api_shutdown, methods=["POST"]),
            Route(
                "/api/response/{card_id}",
                self._api_response,
                methods=["GET"],
            ),
            Route("/api/events", self._api_events, methods=["GET"]),
            Route("/api/studies", self._api_studies, methods=["GET"]),
            Route(
                "/api/studies/{study:path}/rename",
                self._api_study_rename,
                methods=["PATCH"],
            ),
            Route(
                "/api/studies/{study:path}/context",
                self._api_study_context,
                methods=["GET"],
            ),
            Route(
                "/api/studies/{study:path}/export",
                self._api_study_export,
                methods=["GET"],
            ),
            Route(
                "/api/studies/{study:path}/files",
                self._api_study_files,
                methods=["GET"],
            ),
            Route(
                "/api/studies/{study:path}/files-archive",
                self._api_study_files_archive,
                methods=["GET"],
            ),
            Route(
                "/api/studies/{study:path}/files/{filepath:path}",
                self._api_study_file,
                methods=["GET"],
            ),
            Route(
                "/api/studies/{study:path}/agents",
                self._api_create_agent,
                methods=["POST"],
            ),
            Route(
                "/api/agents/{card_id}/run",
                self._api_run_agent,
                methods=["POST"],
            ),
            Route(
                "/api/agents/{card_id}",
                self._api_agent_handler,
                methods=["GET", "DELETE"],
            ),
            Route(
                "/api/studies/{study:path}",
                self._api_study_delete,
                methods=["DELETE"],
            ),
            Route("/api/export", self._api_export, methods=["GET"]),
            Route("/api/files-archive", self._api_all_files_archive, methods=["GET"]),
            WebSocketRoute("/ws", self._ws_endpoint),
        ]

        # Mount static files if the directory exists
        if _STATIC_DIR.exists():
            routes.append(Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR))))

        return Starlette(routes=routes)

    # --- Store Resolution ---

    def _resolve_store(self, card_id: str | None = None) -> ArtifactStore | None:
        """Resolve the ArtifactStore for a given card_id.

        If study_manager is available, looks up the card in the cross-study index.
        Falls back to the legacy self.store. Refreshes from disk if not found.
        """
        if card_id and self.study_manager:
            store = self.study_manager.get_store_for_card(card_id)
            if store:
                return store
            # Card not in index — client may have created a new study
            self.study_manager.refresh()
            store = self.study_manager.get_store_for_card(card_id)
            if store:
                return store
        return self.store

    def _get_card_annotations(
        self, store: ArtifactStore, card_id: str
    ) -> list[dict[str, Any]]:
        """Return a copy of the annotations list for a card, or [] if not found."""
        for c in store.list_cards():
            if c.card_id == card_id:
                return list(c.annotations)
        return []

    # --- HTTP Endpoints ---

    async def _index(self, request: Request) -> Response:
        """Serve the main index.html page."""
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>vitrine</h1><p>index.html not found</p>")
        return HTMLResponse(index_path.read_text())

    async def _api_cards(self, request: Request) -> JSONResponse:
        """List card descriptors, optionally filtered by study."""
        study = request.query_params.get("study")
        if self.study_manager:
            self.study_manager.refresh()
            cards = self.study_manager.list_all_cards(study=study)
        elif self.store:
            cards = self.store.list_cards(study=study)
        else:
            cards = []
        return JSONResponse([_serialize_card(c) for c in cards])

    async def _api_card(self, request: Request) -> JSONResponse:
        """Return a single card descriptor by ID or prefix.

        Accepts full 12-char IDs, short prefixes, or slug-suffixed
        references like ``a1b2c3-my-title``.
        """
        raw = request.path_params["card_id"]
        # Strip slug suffix (everything after first dash)
        id_prefix = raw.split("-")[0]

        # Collect all cards to search
        if self.study_manager:
            self.study_manager.refresh()
            cards = self.study_manager.list_all_cards()
        elif self.store:
            cards = self.store.list_cards()
        else:
            cards = []

        for card in cards:
            if card.card_id.startswith(id_prefix):
                return JSONResponse(_serialize_card(card))
        return JSONResponse({"error": f"Card {raw} not found"}, status_code=404)

    async def _api_table(self, request: Request) -> JSONResponse:
        """Return a page of table data from a stored Parquet artifact."""
        card_id = request.path_params["card_id"]
        offset = max(0, int(request.query_params.get("offset", "0")))
        limit = max(1, min(int(request.query_params.get("limit", "50")), 10000))
        sort_col = request.query_params.get("sort")
        sort_asc = request.query_params.get("asc", "true").lower() == "true"
        search = request.query_params.get("search") or None

        store = self._resolve_store(card_id)
        if store is None:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )

        try:
            page = store.read_table_page(
                card_id=card_id,
                offset=offset,
                limit=limit,
                sort_col=sort_col,
                sort_asc=sort_asc,
                search=search,
            )
            return JSONResponse(page)
        except FileNotFoundError:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )

    async def _api_table_selection(self, request: Request) -> JSONResponse:
        """Return selected rows for a table card.

        Uses the in-memory selection state synced from the browser
        via WebSocket ``display.selection`` events.
        """
        card_id = request.path_params["card_id"]
        indices = self._selections.get(card_id, [])
        if not indices:
            return JSONResponse({"selected_indices": [], "columns": [], "rows": []})

        store = self._resolve_store(card_id)
        if store is None:
            return JSONResponse(
                {"selected_indices": indices, "columns": [], "rows": []}
            )

        path = store._artifacts_dir / f"{card_id}.parquet"
        if not path.exists():
            return JSONResponse(
                {"selected_indices": indices, "columns": [], "rows": []}
            )

        try:
            import duckdb

            con = duckdb.connect(":memory:")
            try:
                # Use ROW_NUMBER to select by 0-based index
                safe_path = str(path).replace("'", "''")
                idx_list = ", ".join(str(int(i)) for i in indices)
                query = (
                    f"SELECT * FROM ("
                    f"  SELECT *, ROW_NUMBER() OVER () - 1 AS _rn "
                    f"  FROM read_parquet('{safe_path}')"
                    f") WHERE _rn IN ({idx_list})"
                )
                result = con.execute(query)
                columns = [desc[0] for desc in result.description if desc[0] != "_rn"]
                rows = [
                    [v for v, d in zip(row, result.description) if d[0] != "_rn"]
                    for row in result.fetchall()
                ]
            finally:
                con.close()

            return JSONResponse(
                {"selected_indices": indices, "columns": columns, "rows": rows}
            )
        except Exception:
            return JSONResponse(
                {"selected_indices": indices, "columns": [], "rows": []}
            )

    async def _api_table_stats(self, request: Request) -> JSONResponse:
        """Return per-column statistics for a table artifact."""
        card_id = request.path_params["card_id"]
        store = self._resolve_store(card_id)
        if store is None:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )
        try:
            stats = store.table_stats(card_id)
            return JSONResponse(stats)
        except FileNotFoundError:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )

    async def _api_table_export(self, request: Request) -> Response:
        """Export a table artifact as CSV."""
        card_id = request.path_params["card_id"]
        sort_col = request.query_params.get("sort")
        sort_asc = request.query_params.get("asc", "true").lower() == "true"
        search = request.query_params.get("search") or None

        store = self._resolve_store(card_id)
        if store is None:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )

        try:
            csv_data = store.export_table_csv(
                card_id=card_id,
                sort_col=sort_col,
                sort_asc=sort_asc,
                search=search,
            )
            return Response(
                content=csv_data,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{card_id}.csv"',
                },
            )
        except FileNotFoundError:
            return JSONResponse(
                {"error": f"No table artifact for card {card_id}"}, status_code=404
            )

    async def _api_artifact(self, request: Request) -> Response:
        """Return a raw artifact by card ID."""
        card_id = request.path_params["card_id"]
        store = self._resolve_store(card_id)
        if store is None:
            return JSONResponse(
                {"error": f"No artifact for card {card_id}"}, status_code=404
            )
        try:
            data = store.get_artifact(card_id)
            if isinstance(data, dict):
                return JSONResponse(data)
            # Determine media type from file extension
            media_type = "application/octet-stream"
            for ext, mime in (
                ("svg", "image/svg+xml"),
                ("png", "image/png"),
            ):
                if (store._artifacts_dir / f"{card_id}.{ext}").exists():
                    media_type = mime
                    break
            return Response(content=data, media_type=media_type)
        except FileNotFoundError:
            return JSONResponse(
                {"error": f"No artifact for card {card_id}"}, status_code=404
            )

    async def _api_session(self, request: Request) -> JSONResponse:
        """Return session metadata."""
        if self.study_manager:
            studies = self.study_manager.list_studies()
            study_labels = [s["label"] for s in studies]
            return JSONResponse(
                {"session_id": self.session_id, "study_names": study_labels}
            )
        if self.store:
            meta_path = self.store._meta_path
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                return JSONResponse(meta)
            return JSONResponse(
                {"session_id": self.store.session_id, "study_names": []}
            )
        return JSONResponse({"session_id": self.session_id, "study_names": []})

    async def _api_health(self, request: Request) -> JSONResponse:
        """Health check endpoint. No auth required."""
        uptime_seconds = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        study_count = (
            len(self.study_manager.list_studies()) if self.study_manager else 0
        )
        return JSONResponse(
            {
                "status": "ok",
                "session_id": self.session_id,
                "uptime": round(uptime_seconds, 1),
                "version": "1.0",
                "study_count": study_count,
            }
        )

    def _check_auth(self, request: Request) -> bool:
        """Check Bearer token authorization."""
        if not self.token:
            return True
        auth = request.headers.get("authorization", "")
        return auth == f"Bearer {self.token}"

    async def _api_command(self, request: Request) -> JSONResponse:
        """Unified command endpoint for pushing cards/sections/clears.

        Requires Bearer token auth. Accepts JSON body with "type" field:
        - {"type": "card", "card": {...}}
        - {"type": "section", "title": "...", "study": "..."}
        """
        if not self._check_auth(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)

        cmd_type = body.get("type")

        if cmd_type == "card":
            card_data = body.get("card", {})
            message = {"type": "display.add", "card": card_data}
            # Register card in study_manager's card index if available
            card_id = card_data.get("card_id")
            study = card_data.get("study")
            if card_id and self.study_manager and study:
                dir_name = self.study_manager._label_to_dir.get(study)
                if not dir_name:
                    # Client may have created the study — pick it up from disk
                    self.study_manager.refresh()
                    dir_name = self.study_manager._label_to_dir.get(study)
                if dir_name:
                    self.study_manager.register_card(card_id, dir_name)
            await self._broadcast(message)
            return JSONResponse({"status": "ok"})

        elif cmd_type == "section":
            title = body.get("title", "")
            study = body.get("study")
            message = {
                "type": "display.section",
                "title": title,
                "study": study,
            }
            await self._broadcast(message)
            return JSONResponse({"status": "ok"})

        elif cmd_type == "update":
            card_id = body.get("card_id", "")
            card_data = body.get("card", {})
            message = {
                "type": "display.update",
                "card_id": card_id,
                "card": card_data,
            }
            await self._broadcast(message)
            return JSONResponse({"status": "ok"})

        return JSONResponse(
            {"error": f"unknown command type: {cmd_type}"}, status_code=400
        )

    async def _api_shutdown(self, request: Request) -> JSONResponse:
        """Gracefully shut down the server. Requires auth."""
        if not self._check_auth(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        # Schedule shutdown after returning the response
        if self._server:
            self._server.should_exit = True
        return JSONResponse({"status": "shutting_down"})

    async def _api_response(self, request: Request) -> JSONResponse:
        """Long-poll endpoint for blocking show() responses.

        Agent calls GET /api/response/{card_id}?timeout=N and the server
        holds the connection until the browser responds or timeout.
        Requires auth.
        """
        if not self._check_auth(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        card_id = request.path_params["card_id"]
        timeout = float(request.query_params.get("timeout", "300"))
        timeout = min(timeout, 1800)  # Cap at 30 minutes

        result = await self.wait_for_response(card_id, timeout)
        return JSONResponse(result)

    async def _api_events(self, request: Request) -> JSONResponse:
        """Return and drain queued UI events. Requires auth.

        Events (row_click, point_select, etc.) are queued by the WebSocket
        handler and consumed here by remote clients polling via on_event().
        """
        if not self._check_auth(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        with self._lock:
            events = list(self._event_queue)
            self._event_queue.clear()
        return JSONResponse(events)

    # --- Study Endpoints ---

    async def _api_studies(self, request: Request) -> JSONResponse:
        """List all studies with metadata and card counts."""
        if self.study_manager:
            self.study_manager.refresh()
            return JSONResponse(self.study_manager.list_studies())
        return JSONResponse([])

    async def _api_study_rename(self, request: Request) -> JSONResponse:
        """Rename a study by label."""
        study = request.path_params["study"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        new_label = body.get("new_label", "").strip()
        if not new_label:
            return JSONResponse({"error": "new_label is required"}, status_code=400)
        if self.study_manager:
            renamed = self.study_manager.rename_study(study, new_label)
            if renamed:
                return JSONResponse({"status": "ok"})
            return JSONResponse(
                {
                    "error": f"Cannot rename: '{study}' not found or '{new_label}' already exists"
                },
                status_code=409,
            )
        return JSONResponse({"error": "No study manager"}, status_code=400)

    async def _api_study_context(self, request: Request) -> JSONResponse:
        """Return a structured context summary for a study.

        Includes card list, pending/resolved decisions, and selection state.
        """
        study = request.path_params["study"]
        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        self.study_manager.refresh()
        ctx = self.study_manager.build_context(study)
        cards = ctx.get("cards", [])
        card_ids = [c.get("card_id", "") for c in cards]

        # Current selections for cards in this study
        current_selections = {}
        for cid in card_ids:
            sel = self._selections.get(cid, [])
            if sel:
                current_selections[cid] = sel

        # Enrich card summaries with selection details
        for card_summary in cards:
            cid = card_summary.get("card_id", "")
            sel = self._selections.get(cid, [])
            if sel:
                card_summary["selection_count"] = len(sel)
                card_summary["selected_indices"] = sel

        # Ensure pending responses includes unresolved in-memory futures
        pending_ids = {
            item.get("card_id", "")
            for item in ctx.get("pending_responses", [])
            if item.get("card_id")
        }
        for cid in card_ids:
            fut = self._pending_responses.get(cid)
            if fut and not fut.done() and cid not in pending_ids:
                pending_ids.add(cid)
                ctx.setdefault("pending_responses", []).append(
                    {"card_id": cid, "title": None, "prompt": None}
                )

        ctx["current_selections"] = current_selections
        ctx["decisions"] = ctx.get("pending_responses", [])
        return JSONResponse(ctx)

    async def _api_study_delete(self, request: Request) -> JSONResponse:
        """Delete a study by label.

        No auth required — server is localhost-only and the browser UI
        shows a confirmation dialog before calling this endpoint.
        """
        study = request.path_params["study"]
        if self.study_manager:
            deleted = self.study_manager.delete_study(study)
            if deleted:
                return JSONResponse({"status": "ok"})
            return JSONResponse(
                {"error": f"Study '{study}' not found"}, status_code=404
            )
        return JSONResponse({"error": "No study manager"}, status_code=400)

    async def _api_study_export(self, request: Request) -> Response:
        """Export a specific study as HTML or JSON.

        GET /api/studies/{study}/export?format=html|json
        """
        study = request.path_params["study"]
        fmt = request.query_params.get("format", "html")

        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        from m4.vitrine.export import export_html_string, export_json_bytes

        self.study_manager.refresh()

        if fmt == "json":
            data = export_json_bytes(self.study_manager, study=study)
            filename = f"m4-export-{study}.zip"
            return Response(
                content=data,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

        # Default: HTML
        html = export_html_string(self.study_manager, study=study)
        filename = f"m4-export-{study}.html"
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    async def _api_study_files(self, request: Request) -> JSONResponse:
        """List files in a study's output directory."""
        study = request.path_params["study"]
        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)
        self.study_manager.refresh()
        files = self.study_manager.list_output_files(study)
        return JSONResponse(files)

    async def _api_study_file(self, request: Request) -> Response:
        """Serve a file from a study's output directory.

        Query param: ?mode=preview (default) or ?mode=download.
        """
        study = request.path_params["study"]
        filepath = request.path_params["filepath"]
        mode = request.query_params.get("mode", "preview")

        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        self.study_manager.refresh()
        resolved = self.study_manager.get_output_file_path(study, filepath)
        if resolved is None:
            return JSONResponse({"error": "File not found"}, status_code=404)

        suffix = resolved.suffix.lower()

        # Download mode — always attachment
        if mode == "download":
            content = resolved.read_bytes()
            return Response(
                content=content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{resolved.name}"',
                },
            )

        # Preview mode — content-type dispatch
        from m4.vitrine._utils import IMAGE_MIME_TYPES, TEXT_EXTENSIONS

        _TEXT_EXTENSIONS = TEXT_EXTENSIONS
        _IMAGE_MIMES = IMAGE_MIME_TYPES

        if suffix == ".md":
            text = resolved.read_text(encoding="utf-8", errors="replace")
            return Response(content=text, media_type="text/plain; charset=utf-8")

        if suffix in _TEXT_EXTENSIONS:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            return Response(content=text, media_type="text/plain; charset=utf-8")

        if suffix in (".csv", ".parquet"):
            return self._preview_tabular_file(resolved, suffix)

        if suffix in _IMAGE_MIMES:
            content = resolved.read_bytes()
            return Response(content=content, media_type=_IMAGE_MIMES[suffix])

        if suffix == ".pdf":
            content = resolved.read_bytes()
            return Response(content=content, media_type="application/pdf")

        if suffix in (".html", ".htm"):
            content = resolved.read_bytes()
            return Response(content=content, media_type="text/html; charset=utf-8")

        # Fallback — binary download
        content = resolved.read_bytes()
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{resolved.name}"',
            },
        )

    def _preview_tabular_file(self, path: Path, suffix: str) -> Response:
        """Preview a CSV or Parquet file as JSON table (max 1000 rows)."""
        try:
            import duckdb

            con = duckdb.connect(":memory:")
            try:
                safe_path = str(path).replace("'", "''")
                if suffix == ".csv":
                    reader = f"read_csv_auto('{safe_path}')"
                else:
                    reader = f"read_parquet('{safe_path}')"

                total = con.execute(f"SELECT COUNT(*) FROM {reader}").fetchone()[0]
                result = con.execute(f"SELECT * FROM {reader} LIMIT 1000")
                columns = [desc[0] for desc in result.description]
                rows = [
                    [v.isoformat() if hasattr(v, "isoformat") else v for v in row]
                    for row in result.fetchall()
                ]
            finally:
                con.close()

            return JSONResponse(
                {
                    "columns": columns,
                    "rows": rows,
                    "total_rows": total,
                    "truncated": total > 1000,
                }
            )
        except Exception as e:
            return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=500)

    async def _api_study_files_archive(self, request: Request) -> Response:
        """Download all output files as a zip archive."""
        study = request.path_params["study"]
        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        self.study_manager.refresh()
        output_dir = self.study_manager.get_output_dir(study)
        if output_dir is None or not output_dir.exists():
            return JSONResponse({"error": "No output directory"}, status_code=404)

        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(output_dir.rglob("*")):
                if item.is_file() and not item.name.startswith("."):
                    arcname = str(item.relative_to(output_dir))
                    zf.write(item, arcname)

        filename = f"{study}-files.zip"
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    async def _api_export(self, request: Request) -> Response:
        """Export all studies as HTML or JSON.

        GET /api/export?format=html|json
        """
        fmt = request.query_params.get("format", "html")

        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        from m4.vitrine.export import export_html_string, export_json_bytes

        self.study_manager.refresh()

        if fmt == "json":
            data = export_json_bytes(self.study_manager)
            return Response(
                content=data,
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="m4-export-all.zip"',
                },
            )

        html = export_html_string(self.study_manager)
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Content-Disposition": 'attachment; filename="m4-export-all.html"',
            },
        )

    async def _api_all_files_archive(self, request: Request) -> Response:
        """Download output files from all studies as a zip archive."""
        if not self.study_manager:
            return JSONResponse({"error": "No study manager"}, status_code=400)

        import io
        import zipfile

        self.study_manager.refresh()
        studies = self.study_manager.list_studies()

        buf = io.BytesIO()
        file_count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for study_info in studies:
                label = study_info["label"]
                output_dir = self.study_manager.get_output_dir(label)
                if output_dir is None or not output_dir.exists():
                    continue
                for item in sorted(output_dir.rglob("*")):
                    if item.is_file() and not item.name.startswith("."):
                        arcname = f"{label}/{item.relative_to(output_dir)}"
                        zf.write(item, arcname)
                        file_count += 1

        if file_count == 0:
            return JSONResponse({"error": "No output files"}, status_code=404)

        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="m4-files-all.zip"',
            },
        )

    # --- Agent Endpoints ---

    async def _api_create_agent(self, request: Request) -> JSONResponse:
        """Create an agent card for a study.

        POST /api/studies/{study}/agents with {"task": "reproduce"|"report"}.
        """
        study = request.path_params["study"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        task = body.get("task")
        if task not in ("reproduce", "report", "paper"):
            return JSONResponse(
                {
                    "error": f"Unknown task: {task!r} (expected 'reproduce', 'report', or 'paper')"
                },
                status_code=400,
            )

        try:
            info = await create_agent_card(task, study, self)
            return JSONResponse(
                {
                    "status": "ok",
                    "task": task,
                    "study": study,
                    "card_id": info.card_id,
                }
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def _api_run_agent(self, request: Request) -> JSONResponse:
        """Start an agent for an existing agent card.

        POST /api/agents/{card_id}/run with optional config overrides.
        """
        card_id = request.path_params["card_id"]
        config = None
        try:
            body = await request.json()
            config = body if body else None
        except Exception:
            pass  # No body is fine — use defaults

        try:
            info = await run_agent(card_id, self, config=config)
            return JSONResponse(
                {
                    "status": "ok",
                    "card_id": card_id,
                    "pid": info.pid,
                }
            )
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def _api_agent_handler(self, request: Request) -> JSONResponse:
        """Handle GET (status) and DELETE (cancel) for an agent card."""
        card_id = request.path_params["card_id"]
        if request.method == "DELETE":
            cancelled = await cancel_agent(card_id, self)
            if cancelled:
                return JSONResponse({"status": "ok"})
            # Agent not in _dispatches — maybe orphaned after restart.
            # Force-update the stored card if it's still showing "running".
            if self.study_manager:
                from m4.vitrine._types import CardType

                for card in self.study_manager.list_all_cards():
                    if card.card_id != card_id:
                        continue
                    if card.card_type != CardType.AGENT:
                        break
                    status = card.preview.get("status") if card.preview else None
                    if status in ("running", "pending"):
                        new_preview = dict(card.preview)
                        new_preview["status"] = "failed"
                        new_preview["error"] = "Agent process no longer running"
                        _, store = self.study_manager.get_or_create_study(card.study)
                        if store:
                            store.update_card(card_id, preview=new_preview)
                        # Broadcast so UI updates immediately
                        await self._broadcast(
                            {
                                "type": "display.update",
                                "card_id": card_id,
                                "card": {
                                    "card_id": card_id,
                                    "card_type": CardType.AGENT.value,
                                    "study": card.study,
                                    "title": card.title,
                                    "preview": new_preview,
                                },
                            }
                        )
                        return JSONResponse({"status": "ok"})
                    break
            return JSONResponse(
                {"error": "No running agent for this card"}, status_code=404
            )
        # GET — status
        status = get_agent_status(card_id, self)
        if status is None:
            return JSONResponse({"status": "none", "card_id": card_id})
        return JSONResponse(status)

    # --- WebSocket ---

    async def _ws_endpoint(self, ws: WebSocket) -> None:
        """Handle a WebSocket connection."""
        await ws.accept()
        with self._lock:
            self._connections.append(ws)
        logger.debug("WebSocket client connected")

        # Replay existing cards on connect
        try:
            if self.study_manager:
                cards = self.study_manager.list_all_cards()
            elif self.store:
                cards = self.store.list_cards()
            else:
                cards = []
            for card in cards:
                msg = {
                    "type": "display.add",
                    "card": _serialize_card(card),
                }
                await ws.send_json(msg)
            await ws.send_json({"type": "display.replay_done"})
        except Exception:
            logger.exception("Error replaying cards on WebSocket connect")

        try:
            while True:
                data = await ws.receive_json()
                await self._handle_ws_event(data)
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception:
            logger.debug("WebSocket connection closed")
        finally:
            with self._lock:
                if ws in self._connections:
                    self._connections.remove(ws)

    async def _handle_ws_event(self, data: dict[str, Any]) -> None:
        """Route incoming WebSocket events from the browser."""
        msg_type = data.get("type")
        logger.debug(f"Received WebSocket message: {msg_type}")

        if msg_type != "vitrine.event":
            return

        event_type = data.get("event_type")
        card_id = data.get("card_id", "")
        payload = data.get("payload", {})

        if event_type == "response":
            # Resolve a pending blocking show() call
            action = payload.get("action", "confirm")
            message = payload.get("message")
            selected_rows = payload.get("selected_rows")
            columns = payload.get("columns")
            points = payload.get("points")
            form_values = payload.get("form_values", {})

            sel_store = self._resolve_store(card_id)
            artifact_id = None
            if selected_rows and columns:
                artifact_id = f"resp-{card_id}"
                if sel_store:
                    sel_store.store_selection(artifact_id, selected_rows, columns)
                elif self.study_manager:
                    self.study_manager.store_selection(
                        artifact_id, selected_rows, columns
                    )
            elif points:
                artifact_id = f"resp-{card_id}"
                if sel_store:
                    sel_store.store_selection_json(artifact_id, {"points": points})
                elif self.study_manager:
                    self.study_manager.store_selection_json(
                        artifact_id, {"points": points}
                    )

            summary = self._build_summary(card_id, selected_rows, points, columns)

            result = {
                "action": action,
                "card_id": card_id,
                "message": message,
                "artifact_id": artifact_id,
                "summary": summary,
                "values": form_values,
            }

            # Persist response metadata for study_context() and export provenance
            if sel_store is not None:
                sel_store.update_card(
                    card_id,
                    response_requested=False,
                    response_action=action,
                    response_message=message,
                    response_values=form_values,
                    response_summary=summary,
                    response_artifact_id=artifact_id,
                    response_timestamp=datetime.now(timezone.utc).isoformat(),
                )

            future = self._pending_responses.get(card_id)
            if future and not future.done():
                future.set_result(result)

        elif event_type == "annotation":
            # Researcher annotations: add, edit, delete
            action = payload.get("action")
            store = self._resolve_store(card_id)
            if store is None:
                return

            if action == "add":
                text = payload.get("text", "").strip()
                if not text:
                    return
                annotation_id = uuid.uuid4().hex[:8]
                annotation = {
                    "id": annotation_id,
                    "text": text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Read current annotations, append, persist
                current = self._get_card_annotations(store, card_id)
                current.append(annotation)
                updated = store.update_card(card_id, annotations=current)
                if updated:
                    await self._broadcast(
                        {
                            "type": "display.update",
                            "card_id": card_id,
                            "card": _serialize_card(updated),
                        }
                    )

            elif action == "edit":
                ann_id = payload.get("annotation_id", "")
                new_text = payload.get("text", "")
                current = self._get_card_annotations(store, card_id)
                for ann in current:
                    if ann.get("id") == ann_id:
                        ann["text"] = new_text
                        ann["timestamp"] = datetime.now(timezone.utc).isoformat()
                        break
                updated = store.update_card(card_id, annotations=current)
                if updated:
                    await self._broadcast(
                        {
                            "type": "display.update",
                            "card_id": card_id,
                            "card": _serialize_card(updated),
                        }
                    )

            elif action == "delete":
                ann_id = payload.get("annotation_id", "")
                current = self._get_card_annotations(store, card_id)
                current = [a for a in current if a.get("id") != ann_id]
                updated = store.update_card(card_id, annotations=current)
                if updated:
                    await self._broadcast(
                        {
                            "type": "display.update",
                            "card_id": card_id,
                            "card": _serialize_card(updated),
                        }
                    )

        elif event_type == "rename":
            new_title = (payload.get("new_title") or "").strip()
            if new_title:
                store = self._resolve_store(card_id)
                if store is not None:
                    updated = store.update_card(card_id, title=new_title)
                    if updated:
                        await self._broadcast(
                            {
                                "type": "display.update",
                                "card_id": card_id,
                                "card": _serialize_card(updated),
                            }
                        )

        elif event_type == "dismiss":
            dismissed = payload.get("dismissed", True)
            store = self._resolve_store(card_id)
            if store is not None:
                updated = store.update_card(card_id, dismissed=dismissed)
                if updated:
                    await self._broadcast(
                        {
                            "type": "display.update",
                            "card_id": card_id,
                            "card": _serialize_card(updated),
                        }
                    )

        elif event_type == "delete":
            deleted = payload.get("deleted", True)
            # Cancel running agent if this is an agent card being deleted
            if deleted and card_id in self._dispatches:
                from m4.vitrine.dispatch import cancel_agent

                await cancel_agent(card_id, self)
            store = self._resolve_store(card_id)
            if store is not None:
                updates: dict[str, Any] = {"deleted": deleted}
                if deleted:
                    updates["deleted_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    updates["deleted_at"] = None
                updated = store.update_card(card_id, **updates)
                if updated:
                    await self._broadcast(
                        {
                            "type": "display.update",
                            "card_id": card_id,
                            "card": _serialize_card(updated),
                        }
                    )

        elif event_type == "selection":
            # Passive selection tracking from browser checkboxes / chart selection
            self._selections[card_id] = payload.get("selected_indices", [])
            self._schedule_save_selections()

        else:
            # General events (row_click, point_select, etc.)
            from m4.vitrine._types import DisplayEvent

            event = DisplayEvent(
                event_type=event_type,
                card_id=card_id,
                payload=payload,
            )
            with self._lock:
                callbacks = list(self._event_callbacks)
            for cb in callbacks:
                try:
                    cb(event)
                except Exception:
                    logger.debug(f"Event callback error for {event_type}")

            # Queue for remote clients polling via GET /api/events
            with self._lock:
                self._event_queue.append(
                    {
                        "event_type": event_type,
                        "card_id": card_id,
                        "payload": payload,
                    }
                )
                # Bound the queue to prevent unbounded growth
                if len(self._event_queue) > 1000:
                    self._event_queue = self._event_queue[-500:]

    def _build_summary(
        self,
        card_id: str,
        selected_rows: list | None,
        points: list | None = None,
        columns: list | None = None,
    ) -> str:
        """Build a human-readable summary of a selection."""
        # Look up card title from store
        card_title = ""
        try:
            if self.study_manager:
                cards = self.study_manager.list_all_cards()
            elif self.store:
                cards = self.store.list_cards()
            else:
                cards = []
            for c in cards:
                if c.card_id == card_id:
                    card_title = c.title or ""
                    break
        except Exception:
            pass

        parts = []
        if selected_rows:
            n = len(selected_rows)
            ncols = len(columns) if columns else 0
            shape = f"{n} row{'s' if n != 1 else ''}"
            if ncols:
                shape += f" \u00d7 {ncols} col{'s' if ncols != 1 else ''}"
            parts.append(shape)
            if columns:
                col_str = ", ".join(str(c) for c in columns[:6])
                if len(columns) > 6:
                    col_str += ", \u2026"
                parts.append(f"({col_str})")
        if points:
            n = len(points)
            parts.append(f"{n} point{'s' if n != 1 else ''}")
        if card_title:
            parts.append(f"from '{card_title}'")
        return " ".join(parts) if parts else ""

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected WebSocket clients."""
        with self._lock:
            connections = list(self._connections)
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                with self._lock:
                    if ws in self._connections:
                        self._connections.remove(ws)

    # --- Blocking Response ---

    async def wait_for_response(self, card_id: str, timeout: float) -> dict[str, Any]:
        """Wait for a browser response to a blocking show() card.

        Args:
            card_id: The card ID to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            Dict with action, card_id, message, artifact_id.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_responses[card_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"action": "timeout", "card_id": card_id}
        finally:
            self._pending_responses.pop(card_id, None)

    def wait_for_response_sync(self, card_id: str, timeout: float) -> dict[str, Any]:
        """Sync wrapper for wait_for_response (called from Python API thread).

        Args:
            card_id: The card ID to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            Dict with action, card_id, message, artifact_id.
        """
        if self._loop is None:
            return {"action": "timeout", "card_id": card_id}
        future = asyncio.run_coroutine_threadsafe(
            self.wait_for_response(card_id, timeout), self._loop
        )
        try:
            return future.result(timeout=timeout + 1)
        except Exception:
            return {"action": "timeout", "card_id": card_id}

    def register_event_callback(self, callback: Callable) -> None:
        """Register a callback for UI events.

        Args:
            callback: Function that receives DisplayEvent instances.
        """
        with self._lock:
            self._event_callbacks.append(callback)

    # --- Lifecycle ---

    def _find_port(self) -> int:
        """Find an available port, starting from self.port."""
        for port in range(self.port, _MAX_PORT + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((self.host, port))
                    return port
            except OSError:
                continue
        raise RuntimeError(f"No available port in range {self.port}-{_MAX_PORT}")

    def start(
        self,
        open_browser: bool = True,
        pid_path: Path | None = None,
    ) -> None:
        """Start the server in a background daemon thread.

        Args:
            open_browser: Open a browser tab to the display.
            pid_path: If set, write a PID file after the server binds.
        """
        if self._thread and self._thread.is_alive():
            return

        self.port = self._find_port()

        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._started.set()
            self._loop.run_until_complete(self._server.serve())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)

        # Wait a moment for the server to fully bind
        self._wait_for_server()

        # Start dispatch watchdog
        if self._loop:
            self._loop.call_soon_threadsafe(
                lambda: setattr(
                    self,
                    "_watchdog_task",
                    self._loop.create_task(_dispatch_watchdog(self)),
                )
            )

        # Write PID file if requested
        if pid_path is not None:
            self._write_pid_file(pid_path)

        import sys

        print(
            f"vitrine: http://{_DISPLAY_HOST}:{self.port}",
            file=sys.stderr,
        )

        if open_browser:
            try:
                import webbrowser

                webbrowser.open(f"http://{_DISPLAY_HOST}:{self.port}")
            except Exception:
                pass

    def _wait_for_server(self, timeout: float = 3.0) -> None:
        """Wait for the server to accept connections."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    s.connect((self.host, self.port))
                    return
            except (ConnectionRefusedError, OSError):
                time.sleep(0.05)

    def stop(self) -> None:
        """Stop the server and remove PID file if set."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        cleanup_dispatches(self)
        self._remove_pid_file()
        # Flush pending selection save
        if self._selection_save_timer is not None:
            self._selection_save_timer.cancel()
            self._selection_save_timer = None
        self._save_selections()
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._server = None
        logger.debug("Display server stopped")

    def _write_pid_file(self, pid_path: Path) -> None:
        """Write the PID file with server metadata."""
        self._pid_path = pid_path
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        info = {
            "pid": os.getpid(),
            "port": self.port,
            "host": self.host,
            "url": self.url,
            "session_id": self.session_id,
            "token": self.token,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        pid_path.write_text(json.dumps(info, indent=2))
        logger.debug(f"PID file written: {pid_path}")

    def _remove_pid_file(self) -> None:
        """Remove the PID file only if it still belongs to this server.

        Another server may have overwritten the PID file after we started.
        Blindly deleting it would orphan that newer server, so we verify
        our own PID is still recorded before unlinking.
        """
        if not self._pid_path or not self._pid_path.exists():
            self._pid_path = None
            return
        try:
            info = json.loads(self._pid_path.read_text())
            if info.get("pid") != os.getpid():
                logger.debug(
                    "PID file belongs to pid=%s, not us (%s); leaving it",
                    info.get("pid"),
                    os.getpid(),
                )
                self._pid_path = None
                return
            self._pid_path.unlink()
            logger.debug(f"PID file removed: {self._pid_path}")
        except (json.JSONDecodeError, OSError):
            pass
        self._pid_path = None

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        """Return the server URL (using vitrine.localhost for display)."""
        return f"http://{_DISPLAY_HOST}:{self.port}"

    def push_card(self, card: CardDescriptor) -> None:
        """Push a card to all connected WebSocket clients.

        Called by the Python API after rendering + storing a card.
        """
        message = {
            "type": "display.add",
            "card": _serialize_card(card),
        }
        self._broadcast_from_thread(message)

    def push_update(self, card_id: str, card: CardDescriptor) -> None:
        """Push a card update to all connected WebSocket clients.

        Sends a display.update message with the full card data so
        the frontend can re-render the card in place.
        """
        message = {
            "type": "display.update",
            "card_id": card_id,
            "card": _serialize_card(card),
        }
        self._broadcast_from_thread(message)

    def push_section(self, title: str, study: str | None = None) -> None:
        """Push a section divider to all connected clients."""
        message = {
            "type": "display.section",
            "title": title,
            "study": study,
        }
        self._broadcast_from_thread(message)

    def _broadcast_from_thread(self, message: dict[str, Any]) -> None:
        """Broadcast a message from a sync context (called from Python API thread)."""
        with self._lock:
            connections = list(self._connections)
        if not connections:
            return
        try:
            loop = self._loop
            for ws in connections:
                asyncio.run_coroutine_threadsafe(ws.send_json(message), loop)
        except Exception:
            logger.debug("Could not broadcast message")


def _kill_orphaned_servers(host: str, port_lo: int, port_hi: int) -> None:
    """Kill any vitrine servers lingering on our port range without a PID file.

    These are servers whose PID file was lost (e.g. the process crashed
    before cleanup ran).  Without a PID file they are undiscoverable and
    block port allocation, so new servers keep bumping to higher ports.

    Strategy: probe each port for a vitrine health endpoint.  If found,
    use ``lsof`` to resolve the PID and send SIGTERM.
    """
    import subprocess
    import urllib.request

    for port in range(port_lo, port_hi + 1):
        # Quick probe — unoccupied ports fail instantly
        try:
            hreq = urllib.request.Request(
                f"http://{host}:{port}/api/health", method="GET"
            )
            with urllib.request.urlopen(hreq, timeout=0.5) as resp:
                data = json.loads(resp.read())
            if data.get("status") != "ok":
                continue
        except Exception:
            continue

        logger.debug(f"Found orphaned vitrine server on port {port}")

        # Resolve the PID owning this port via lsof
        try:
            out = subprocess.check_output(
                ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                text=True,
                timeout=2,
            ).strip()
        except Exception:
            logger.debug(f"Could not resolve PID for port {port}")
            continue

        for pid_str in out.splitlines():
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            logger.debug(f"Sending SIGTERM to orphaned vitrine pid={pid}")
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        # Wait for port to free up
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, port))
                break
            except OSError:
                time.sleep(0.1)


def _run_standalone(port: int = _DEFAULT_PORT, no_open: bool = False) -> None:
    """Run the display server as a standalone persistent process.

    Acquires a file lock to prevent duplicate servers, checks the
    PID file for an existing healthy server, then starts.
    """
    import atexit
    import fcntl
    import sys

    display_dir = _get_vitrine_dir()
    display_dir.mkdir(parents=True, exist_ok=True)

    lock_path = display_dir / ".server.lock"
    pid_path = display_dir / ".server.json"

    # Acquire cross-process file lock
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Another process holds the lock — a server is starting
        logger.debug("Another server process holds the lock, exiting")
        lock_fd.close()
        sys.exit(0)

    try:
        # Check PID file for an existing healthy server
        if pid_path.exists():
            try:
                info = json.loads(pid_path.read_text())
                pid = info.get("pid")
                host = info.get("host", "127.0.0.1")
                port_num = info.get("port")
                sid = info.get("session_id")
                api_url = f"http://{host}:{port_num}" if port_num else info.get("url")
                if (
                    pid
                    and api_url
                    and _is_pid_alive(pid)
                    and _check_health(api_url, sid)
                ):
                    logger.debug(f"Healthy server already running (pid={pid}), exiting")
                    sys.exit(0)
            except (json.JSONDecodeError, OSError):
                pass

        # Kill any orphaned servers occupying our port range.
        # These are leftovers from crashed sessions whose PID file was
        # lost — without this they'd force us onto a higher port and
        # accumulate indefinitely.
        _kill_orphaned_servers("127.0.0.1", port, _MAX_PORT)

        # No server found for this project — start one while holding the lock
        session_id = uuid.uuid4().hex[:12]
        token = secrets.token_hex(16)

        study_manager = StudyManager(display_dir)
        server = DisplayServer(
            study_manager=study_manager,
            port=port,
            host="127.0.0.1",
            token=token,
            session_id=session_id,
        )

        stop_event = threading.Event()

        def _shutdown(signum: int, frame: Any) -> None:
            logger.debug(f"Received signal {signum}, shutting down...")
            stop_event.set()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
        atexit.register(server.stop)

        # start() writes the PID file after binding — still inside the lock
        server.start(open_browser=not no_open, pid_path=pid_path)

    finally:
        # Release the lock after PID file is written (or on error)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

    # Block until signal (outside lock — other processes can now discover us)
    stop_event.wait()
    server.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="vitrine server")
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT, help="Port to bind to"
    )
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = parser.parse_args()
    _run_standalone(port=args.port, no_open=args.no_open)
