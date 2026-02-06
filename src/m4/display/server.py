"""Display server: Starlette + WebSocket + REST for the display pipeline.

Runs in a background thread (default) or separate process, serving a browser
UI that renders cards pushed from the Python API. Uses Starlette (available
via fastmcp transitive dependency) instead of FastAPI.

Endpoints:
    GET  /                               → index.html
    GET  /static/{path}                  → static files (vendor JS, etc.)
    WS   /ws                             → bidirectional display channel
    GET  /api/cards?run_id=...           → list card descriptors
    GET  /api/table/{card_id}            → table page (offset, limit, sort)
    GET  /api/artifact/{card_id}         → raw artifact
    POST /api/clear                      → clear display
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

from m4.display._types import CardDescriptor
from m4.display.artifacts import ArtifactStore, _serialize_card

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 7741
_MAX_PORT = 7750


def _get_display_dir() -> Path:
    """Resolve the display directory under {m4_data}/display/."""
    try:
        from m4.config import _PROJECT_DATA_DIR

        return _PROJECT_DATA_DIR / "display"
    except Exception:
        import tempfile

        return Path(tempfile.gettempdir()) / "m4_data" / "display"


class DisplayServer:
    """WebSocket + REST server for the display pipeline.

    Manages the Starlette app, WebSocket connections, and artifact store.
    Designed to run in a background thread via ``start()``.

    Args:
        store: ArtifactStore for persisting and reading artifacts.
        port: Port to bind to (auto-discovers if taken).
        host: Host to bind to (default: 127.0.0.1 for security).
    """

    def __init__(
        self,
        store: ArtifactStore,
        port: int = _DEFAULT_PORT,
        host: str = "127.0.0.1",
        token: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.token = token
        self.session_id = session_id or store.session_id
        self._pid_path: Path | None = None
        self._connections: list[WebSocket] = []
        self._lock = threading.Lock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._app = self._build_app()

    def _build_app(self) -> Starlette:
        """Build the Starlette application with all routes."""
        routes = [
            Route("/", self._index),
            Route("/api/health", self._api_health),
            Route("/api/cards", self._api_cards),
            Route("/api/table/{card_id}/stats", self._api_table_stats),
            Route("/api/table/{card_id}/export", self._api_table_export),
            Route("/api/table/{card_id}", self._api_table),
            Route("/api/artifact/{card_id}", self._api_artifact),
            Route("/api/clear", self._api_clear, methods=["POST"]),
            Route("/api/session", self._api_session),
            Route("/api/command", self._api_command, methods=["POST"]),
            Route("/api/shutdown", self._api_shutdown, methods=["POST"]),
            WebSocketRoute("/ws", self._ws_endpoint),
        ]

        # Mount static files if the directory exists
        if _STATIC_DIR.exists():
            routes.append(Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR))))

        return Starlette(routes=routes)

    # --- HTTP Endpoints ---

    async def _index(self, request: Request) -> Response:
        """Serve the main index.html page."""
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>M4 Display</h1><p>index.html not found</p>")
        return HTMLResponse(index_path.read_text())

    async def _api_cards(self, request: Request) -> JSONResponse:
        """List card descriptors, optionally filtered by run_id."""
        run_id = request.query_params.get("run_id")
        cards = self.store.list_cards(run_id=run_id)
        return JSONResponse([_serialize_card(c) for c in cards])

    async def _api_table(self, request: Request) -> JSONResponse:
        """Return a page of table data from a stored Parquet artifact."""
        card_id = request.path_params["card_id"]
        offset = int(request.query_params.get("offset", "0"))
        limit = int(request.query_params.get("limit", "50"))
        sort_col = request.query_params.get("sort")
        sort_asc = request.query_params.get("asc", "true").lower() == "true"
        search = request.query_params.get("search") or None

        try:
            page = self.store.read_table_page(
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

    async def _api_table_stats(self, request: Request) -> JSONResponse:
        """Return per-column statistics for a table artifact."""
        card_id = request.path_params["card_id"]
        try:
            stats = self.store.table_stats(card_id)
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

        try:
            csv_data = self.store.export_table_csv(
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
        try:
            data = self.store.get_artifact(card_id)
            if isinstance(data, dict):
                return JSONResponse(data)
            # Determine media type from file extension
            media_type = "application/octet-stream"
            for ext, mime in (
                ("svg", "image/svg+xml"),
                ("png", "image/png"),
            ):
                if (self.store._artifacts_dir / f"{card_id}.{ext}").exists():
                    media_type = mime
                    break
            return Response(content=data, media_type=media_type)
        except FileNotFoundError:
            return JSONResponse(
                {"error": f"No artifact for card {card_id}"}, status_code=404
            )

    async def _api_clear(self, request: Request) -> JSONResponse:
        """Clear all cards from the display."""
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            pass
        keep_pinned = body.get("keep_pinned", True)
        self.store.clear(keep_pinned=keep_pinned)
        # Broadcast clear to all connected clients
        await self._broadcast({"type": "display.clear", "keep_pinned": keep_pinned})
        return JSONResponse({"status": "ok"})

    async def _api_session(self, request: Request) -> JSONResponse:
        """Return session metadata."""
        meta_path = self.store._meta_path
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            return JSONResponse(meta)
        return JSONResponse({"session_id": self.store.session_id, "run_ids": []})

    async def _api_health(self, request: Request) -> JSONResponse:
        """Health check endpoint. No auth required."""
        return JSONResponse({"status": "ok", "session_id": self.session_id})

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
        - {"type": "section", "title": "...", "run_id": "..."}
        - {"type": "clear", "keep_pinned": true}
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
            # Also store the card in the artifact store index if it has card_id
            await self._broadcast(message)
            return JSONResponse({"status": "ok"})

        elif cmd_type == "section":
            title = body.get("title", "")
            run_id = body.get("run_id")
            message = {
                "type": "display.section",
                "title": title,
                "run_id": run_id,
            }
            await self._broadcast(message)
            return JSONResponse({"status": "ok"})

        elif cmd_type == "clear":
            keep_pinned = body.get("keep_pinned", True)
            self.store.clear(keep_pinned=keep_pinned)
            await self._broadcast({"type": "display.clear", "keep_pinned": keep_pinned})
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

    # --- WebSocket ---

    async def _ws_endpoint(self, ws: WebSocket) -> None:
        """Handle a WebSocket connection."""
        await ws.accept()
        with self._lock:
            self._connections.append(ws)
        logger.debug("WebSocket client connected")

        # Replay existing cards on connect
        try:
            cards = self.store.list_cards()
            for card in cards:
                msg = {
                    "type": "display.add",
                    "card": _serialize_card(card),
                }
                await ws.send_json(msg)
        except Exception:
            logger.exception("Error replaying cards on WebSocket connect")

        try:
            while True:
                data = await ws.receive_json()
                # Handle client events (future: on_event callbacks)
                logger.debug(f"Received WebSocket message: {data.get('type')}")
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception:
            logger.debug("WebSocket connection closed")
        finally:
            with self._lock:
                if ws in self._connections:
                    self._connections.remove(ws)

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

        # Write PID file if requested
        if pid_path is not None:
            self._write_pid_file(pid_path)

        import sys

        print(
            f"M4 Display: http://{self.host}:{self.port}",
            file=sys.stderr,
        )

        if open_browser:
            try:
                import webbrowser

                webbrowser.open(f"http://{self.host}:{self.port}")
            except Exception:
                pass

    def _wait_for_server(self, timeout: float = 3.0) -> None:
        """Wait for the server to accept connections."""
        import time

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
        self._remove_pid_file()
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
        """Remove the PID file if it exists and was written by this server."""
        if self._pid_path and self._pid_path.exists():
            try:
                self._pid_path.unlink()
                logger.debug(f"PID file removed: {self._pid_path}")
            except OSError:
                pass
            self._pid_path = None

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        """Return the server URL."""
        return f"http://{self.host}:{self.port}"

    def push_card(self, card: CardDescriptor) -> None:
        """Push a card to all connected WebSocket clients.

        Called by the Python API after rendering + storing a card.
        """
        message = {
            "type": "display.add",
            "card": _serialize_card(card),
        }
        self._broadcast_from_thread(message)

    def push_section(self, title: str, run_id: str | None = None) -> None:
        """Push a section divider to all connected clients."""
        message = {
            "type": "display.section",
            "title": title,
            "run_id": run_id,
        }
        self._broadcast_from_thread(message)

    def push_clear(self, keep_pinned: bool = True) -> None:
        """Push a clear command to all connected clients."""
        message = {
            "type": "display.clear",
            "keep_pinned": keep_pinned,
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


def _run_standalone(port: int = _DEFAULT_PORT, no_open: bool = False) -> None:
    """Run the display server as a standalone persistent process.

    Generates a session_id and auth token, creates ArtifactStore +
    DisplayServer, writes a PID file, and blocks until terminated.
    """
    import uuid

    session_id = uuid.uuid4().hex[:12]
    token = secrets.token_hex(16)

    display_dir = _get_display_dir()
    session_dir = display_dir / session_id

    store = ArtifactStore(session_dir=session_dir, session_id=session_id)
    server = DisplayServer(
        store=store,
        port=port,
        host="127.0.0.1",
        token=token,
        session_id=session_id,
    )

    pid_path = display_dir / ".server.json"
    stop_event = threading.Event()

    def _shutdown(signum: int, frame: Any) -> None:
        logger.debug(f"Received signal {signum}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import atexit

    atexit.register(server.stop)

    server.start(open_browser=not no_open, pid_path=pid_path)

    # Block until signal
    stop_event.wait()
    server.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="M4 Display Server")
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT, help="Port to bind to"
    )
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = parser.parse_args()
    _run_standalone(port=args.port, no_open=args.no_open)
