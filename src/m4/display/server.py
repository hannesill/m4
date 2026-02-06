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
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
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
    ) -> None:
        self.store = store
        self.host = host
        self.port = port
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
            Route("/api/cards", self._api_cards),
            Route("/api/table/{card_id}", self._api_table),
            Route("/api/artifact/{card_id}", self._api_artifact),
            Route("/api/clear", self._api_clear, methods=["POST"]),
            Route("/api/session", self._api_session),
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

        try:
            page = self.store.read_table_page(
                card_id=card_id,
                offset=offset,
                limit=limit,
                sort_col=sort_col,
                sort_asc=sort_asc,
            )
            return JSONResponse(page)
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
            # Binary data (parquet, svg, png)
            return Response(content=data, media_type="application/octet-stream")
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

    def start(self, open_browser: bool = True) -> None:
        """Start the server in a background daemon thread.

        Args:
            open_browser: Open a browser tab to the display.
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
        """Stop the server."""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._server = None
        logger.debug("Display server stopped")

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
