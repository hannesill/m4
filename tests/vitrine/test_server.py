"""Tests for m4.vitrine.server.

Tests cover:
- DisplayServer creation and port finding
- REST endpoints (cards, table paging, session)
- WebSocket connection and card replay
- Static file serving
- Health, command, and shutdown endpoints
- Auth token enforcement
- Event routing via WebSocket
- Blocking response flow
"""

import pandas as pd
import pytest

from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.renderer import render
from m4.vitrine.server import DisplayServer
from m4.vitrine.study_manager import StudyManager

_TEST_TOKEN = "test-secret-token-1234"


@pytest.fixture
def store(tmp_path):
    session_dir = tmp_path / "server_session"
    return ArtifactStore(session_dir=session_dir, session_id="server-test")


@pytest.fixture
def server(store):
    srv = DisplayServer(
        store=store,
        port=7799,
        host="127.0.0.1",
        token=_TEST_TOKEN,
        session_id="server-test",
    )
    return srv


@pytest.fixture
def study_mgr(tmp_path):
    """Create a StudyManager for testing."""
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    return StudyManager(display_dir)


@pytest.fixture
def rm_server(study_mgr):
    """Create a DisplayServer backed by StudyManager (no legacy store)."""
    srv = DisplayServer(
        study_manager=study_mgr,
        port=7798,
        host="127.0.0.1",
        token=_TEST_TOKEN,
        session_id="rm-server-test",
    )
    return srv


class TestServerCreation:
    def test_creates_with_store(self, store):
        srv = DisplayServer(store=store)
        assert srv.store is store

    def test_default_port(self, store):
        srv = DisplayServer(store=store)
        assert srv.port == 7741

    def test_custom_port(self, store):
        srv = DisplayServer(store=store, port=7745)
        assert srv.port == 7745

    def test_host_defaults_to_localhost(self, store):
        srv = DisplayServer(store=store)
        assert srv.host == "127.0.0.1"

    def test_not_running_initially(self, server):
        assert not server.is_running

    def test_url_property(self, server):
        assert server.url == "http://vitrine.localhost:7799"


class TestPortDiscovery:
    def test_find_port_returns_available(self, store):
        srv = DisplayServer(store=store, port=7741)
        port = srv._find_port()
        assert 7741 <= port <= 7750


class TestStarletteApp:
    """Test the Starlette app directly using httpx without starting the server."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_api_cards_empty(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/cards")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_api_cards_with_data(self, app, store):
        from starlette.testclient import TestClient

        # Store a card
        df = pd.DataFrame({"x": [1, 2, 3]})
        card = render(df, title="Test Table", store=store)

        client = TestClient(app)
        resp = client.get("/api/cards")
        assert resp.status_code == 200
        cards = resp.json()
        assert len(cards) == 1
        assert cards[0]["card_id"] == card.card_id
        assert cards[0]["title"] == "Test Table"
        assert cards[0]["card_type"] == "table"

    def test_api_cards_filter_by_study(self, app, store):
        from starlette.testclient import TestClient

        render("text1", study="study-a", store=store)
        render("text2", study="study-b", store=store)
        render("text3", study="study-a", store=store)

        client = TestClient(app)

        # All cards
        resp = client.get("/api/cards")
        assert len(resp.json()) == 3

        # Filter by study-a
        resp = client.get("/api/cards?study=study-a")
        cards = resp.json()
        assert len(cards) == 2
        assert all(c["study"] == "study-a" for c in cards)

    def test_api_table_paging(self, app, store):
        from starlette.testclient import TestClient

        df = pd.DataFrame({"val": range(100)})
        card = render(df, store=store)

        client = TestClient(app)
        resp = client.get(f"/api/table/{card.artifact_id}?offset=10&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rows"]) == 5
        assert data["total_rows"] == 100
        assert data["offset"] == 10
        assert data["rows"][0][0] == 10

    def test_api_table_sorting(self, app, store):
        from starlette.testclient import TestClient

        df = pd.DataFrame({"val": [3, 1, 2]})
        card = render(df, store=store)

        client = TestClient(app)
        resp = client.get(
            f"/api/table/{card.artifact_id}?offset=0&limit=10&sort=val&asc=true"
        )
        data = resp.json()
        vals = [row[0] for row in data["rows"]]
        assert vals == [1, 2, 3]

    def test_api_table_not_found(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/table/nonexistent")
        assert resp.status_code == 404

    def test_api_artifact_json(self, app, store):
        from starlette.testclient import TestClient

        # Store a JSON artifact (via a dict card, which stores in index but not as artifact)
        # Instead, use store directly
        store.store_json("test-json", {"foo": "bar"})

        client = TestClient(app)
        resp = client.get("/api/artifact/test-json")
        assert resp.status_code == 200
        assert resp.json() == {"foo": "bar"}

    def test_api_artifact_not_found(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/artifact/nonexistent")
        assert resp.status_code == 404

    def test_api_session(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "server-test"

    def test_index_page(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "vitrine" in resp.text

    def test_websocket_connection(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws"):
            pass  # Just test that it connects and disconnects cleanly

    def test_websocket_replays_cards(self, app, store):
        from starlette.testclient import TestClient

        # Store cards before connecting
        render("first card", title="Card 1", store=store)
        render("second card", title="Card 2", store=store)

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            # Should receive 2 replay messages
            msg1 = ws.receive_json()
            assert msg1["type"] == "display.add"
            assert msg1["card"]["title"] == "Card 1"

            msg2 = ws.receive_json()
            assert msg2["type"] == "display.add"
            assert msg2["card"]["title"] == "Card 2"


class TestHealthEndpoint:
    @pytest.fixture
    def app(self, server):
        return server._app

    def test_health_returns_ok(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["session_id"] == "server-test"


class TestCommandEndpoint:
    @pytest.fixture
    def app(self, server):
        return server._app

    def test_command_push_card(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "card", "card": {"card_id": "c1", "title": "Test"}},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_command_section(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "section", "title": "Results", "study": "r1"},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_command_requires_auth(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        # No auth header
        resp = client.post(
            "/api/command",
            json={"type": "card", "card": {"card_id": "c1"}},
        )
        assert resp.status_code == 401

    def test_command_rejects_wrong_token(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "card", "card": {"card_id": "c1"}},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_command_unknown_type(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "unknown"},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 400


class TestStatusCommand:
    @pytest.fixture
    def app(self, server):
        return server._app

    def test_status_command(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "status", "message": "Analyzing cohort..."},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_status_broadcast_via_websocket(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws"):
            # Send status command
            client.post(
                "/api/command",
                json={"type": "status", "message": "Working..."},
                headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
            )
            import time

            time.sleep(0.1)
            # The WS should have received the status message
            # (after replay of any existing cards)


class TestShutdownEndpoint:
    @pytest.fixture
    def app(self, server):
        return server._app

    def test_shutdown_requires_auth(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/shutdown")
        assert resp.status_code == 401

    def test_shutdown_with_auth(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/shutdown",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "shutting_down"


class TestPidFile:
    def test_write_and_remove_pid_file(self, store, tmp_path):
        import json

        pid_path = tmp_path / ".server.json"
        srv = DisplayServer(
            store=store,
            port=7799,
            token="tok",
            session_id="sess-1",
        )
        srv._write_pid_file(pid_path)
        assert pid_path.exists()

        data = json.loads(pid_path.read_text())
        assert data["port"] == 7799
        assert data["session_id"] == "sess-1"
        assert data["token"] == "tok"
        assert "pid" in data

        srv._remove_pid_file()
        assert not pid_path.exists()


class TestSelectionTracker:
    """Test passive selection tracking via WebSocket and REST API."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_ws_selection_updates_state(self, app, server):
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "selection",
                    "card_id": "c1",
                    "payload": {"selected_indices": [0, 2, 5]},
                }
            )
            import time

            time.sleep(0.1)

        assert server._selections.get("c1") == [0, 2, 5]

    def test_selection_api_returns_rows(self, app, server, store):
        from starlette.testclient import TestClient

        df = pd.DataFrame({"x": [10, 20, 30, 40]})
        card_id = "sel-card"
        store.store_dataframe(card_id, df)

        # Set selection state
        server._selections[card_id] = [1, 3]

        client = TestClient(app)
        resp = client.get(f"/api/table/{card_id}/selection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_indices"] == [1, 3]
        assert data["columns"] == ["x"]
        assert len(data["rows"]) == 2
        # Rows at index 1 and 3
        vals = [row[0] for row in data["rows"]]
        assert 20 in vals
        assert 40 in vals

    def test_selection_api_empty_when_no_selection(self, app, server):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/table/no-card/selection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_indices"] == []
        assert data["rows"] == []

    def test_selection_overwrites_previous(self, app, server):
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "selection",
                    "card_id": "c1",
                    "payload": {"selected_indices": [0, 1]},
                }
            )
            import time

            time.sleep(0.1)
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "selection",
                    "card_id": "c1",
                    "payload": {"selected_indices": [3]},
                }
            )
            time.sleep(0.1)

        assert server._selections.get("c1") == [3]


class TestEventRouting:
    """Test WebSocket event routing to callbacks and event queue."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_ws_event_dispatches_to_callback(self, app, server):
        from starlette.testclient import TestClient

        events_received = []
        server.register_event_callback(lambda e: events_received.append(e))

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "row_click",
                    "card_id": "c1",
                    "payload": {"row_index": 0},
                }
            )
            # Give the server a moment to process
            import time

            time.sleep(0.1)

        assert len(events_received) == 1
        assert events_received[0].event_type == "row_click"
        assert events_received[0].card_id == "c1"

    def test_ws_event_queued_for_remote_poll(self, app, server):
        """General events are queued for remote clients via GET /api/events."""
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "row_click",
                    "card_id": "c1",
                    "payload": {"row_index": 3, "row": {"id": 42}},
                }
            )
            import time

            time.sleep(0.1)

        # Poll events via REST
        resp = client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["event_type"] == "row_click"
        assert events[0]["card_id"] == "c1"
        assert events[0]["payload"]["row_index"] == 3

        # Second poll should be empty (queue drained)
        resp = client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.json() == []

    def test_events_endpoint_requires_auth(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/events")
        assert resp.status_code == 401


class TestBlockingResponse:
    """Test WebSocket response resolves pending future."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_ws_response_resolves_future(self, app, server, store):
        """Browser response via WS resolves the blocking show() future."""
        import asyncio
        import threading

        from starlette.testclient import TestClient

        client = TestClient(app)

        # Start the server event loop in a thread for async operations
        loop = asyncio.new_event_loop()
        server._loop = loop

        result_holder = {}

        async def wait_and_collect():
            result_holder["result"] = await server.wait_for_response(
                "test-card", timeout=5
            )

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(wait_and_collect())

        t = threading.Thread(target=run_loop)
        t.start()

        # Give the future time to be registered
        import time

        time.sleep(0.2)

        # Resolve via WebSocket
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "response",
                    "card_id": "test-card",
                    "payload": {
                        "action": "confirm",
                        "message": "Selected these",
                    },
                }
            )
            time.sleep(0.3)

        t.join(timeout=5)
        assert "result" in result_holder
        assert result_holder["result"]["action"] == "confirm"
        assert result_holder["result"]["message"] == "Selected these"

    def test_timeout_returns_timeout_action(self, server):
        """If no response comes, wait_for_response returns timeout."""
        import asyncio

        loop = asyncio.new_event_loop()
        server._loop = loop

        result = loop.run_until_complete(
            server.wait_for_response("no-card", timeout=0.1)
        )
        loop.close()
        assert result["action"] == "timeout"
        assert result["card_id"] == "no-card"


class TestSummaryGeneration:
    """Test _build_summary generates human-readable summaries."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_summary_with_rows(self, server, store):
        render("text", title="My Table", store=store)
        card = store.list_cards()[0]
        summary = server._build_summary(
            card.card_id, [[1, 2], [3, 4]], None, ["id", "val"]
        )
        assert "2 rows" in summary
        assert "2 cols" in summary
        assert "id, val" in summary
        assert "My Table" in summary

    def test_summary_with_points(self, server, store):
        render("text", title="Chart", store=store)
        card = store.list_cards()[0]
        summary = server._build_summary(
            card.card_id, None, [{"x": 1}, {"x": 2}, {"x": 3}]
        )
        assert "3 points" in summary
        assert "Chart" in summary

    def test_summary_no_selection(self, server):
        summary = server._build_summary("nonexistent", None, None)
        assert summary == ""


class TestUpdateCommand:
    """Test the update command via /api/command."""

    @pytest.fixture
    def app(self, server):
        return server._app

    def test_command_update(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={
                "type": "update",
                "card_id": "c1",
                "card": {"card_id": "c1", "title": "Updated"},
            },
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStudyManagerServer:
    """Test server endpoints backed by StudyManager."""

    @pytest.fixture
    def app(self, rm_server):
        return rm_server._app

    def test_api_studies_empty(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/studies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_api_studies_lists_studies(self, app, study_mgr):
        from starlette.testclient import TestClient

        study_mgr.get_or_create_study("study-a")
        study_mgr.get_or_create_study("study-b")

        client = TestClient(app)
        resp = client.get("/api/studies")
        assert resp.status_code == 200
        studies = resp.json()
        assert len(studies) == 2
        labels = {r["label"] for r in studies}
        assert labels == {"study-a", "study-b"}

    def test_api_study_delete(self, app, study_mgr):
        from starlette.testclient import TestClient

        study_mgr.get_or_create_study("to-delete")

        client = TestClient(app)
        resp = client.delete(
            "/api/studies/to-delete",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify study is gone
        resp = client.get("/api/studies")
        assert resp.json() == []

    def test_api_study_delete_nonexistent(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.delete(
            "/api/studies/nonexistent",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 404

    def test_api_study_delete_no_auth_required(self, app, study_mgr):
        """Study delete is accessible without auth (localhost-only, UI confirmation)."""
        from starlette.testclient import TestClient

        study_mgr.get_or_create_study("deletable")

        client = TestClient(app)
        resp = client.delete("/api/studies/deletable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_api_cards_via_study_manager(self, app, study_mgr):
        from starlette.testclient import TestClient

        _, store_a = study_mgr.get_or_create_study("study-a")
        _, store_b = study_mgr.get_or_create_study("study-b")

        render("card-a", study="study-a", store=store_a)
        render("card-b", study="study-b", store=store_b)

        client = TestClient(app)

        # All cards
        resp = client.get("/api/cards")
        assert len(resp.json()) == 2

        # Filter by study
        resp = client.get("/api/cards?study=study-a")
        cards = resp.json()
        assert len(cards) == 1
        assert cards[0]["study"] == "study-a"

    def test_api_session_includes_study_names(self, app, study_mgr):
        from starlette.testclient import TestClient

        study_mgr.get_or_create_study("session-study")

        client = TestClient(app)
        resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert "study_names" in data
        assert "session-study" in data["study_names"]

    def test_api_study_context(self, app, study_mgr, rm_server):
        from starlette.testclient import TestClient

        _, store = study_mgr.get_or_create_study("ctx-study")
        card = render("hello", title="Card 1", study="ctx-study", store=store)
        store.update_card(
            card.card_id,
            response_action="Approve",
            response_message="ok",
            response_values={"k": 1},
        )
        rm_server._selections[card.card_id] = [1, 3]

        client = TestClient(app)
        resp = client.get("/api/studies/ctx-study/context")
        assert resp.status_code == 200
        ctx = resp.json()
        assert ctx["study"] == "ctx-study"
        assert ctx["card_count"] == 1
        assert len(ctx["cards"]) == 1
        assert ctx["cards"][0]["title"] == "Card 1"
        assert ctx["cards"][0]["selection_count"] == 2
        assert ctx["current_selections"][card.card_id] == [1, 3]
        assert ctx["decisions_made"][0]["action"] == "Approve"

    def test_api_study_context_nonexistent(self, app):
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/studies/nonexistent/context")
        assert resp.status_code == 200
        ctx = resp.json()
        assert ctx["card_count"] == 0

    def test_websocket_replays_study_manager_cards(self, app, study_mgr):
        from starlette.testclient import TestClient

        _, store = study_mgr.get_or_create_study("ws-study")
        render("hello", title="WS Card", store=store)

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "display.add"
            assert msg["card"]["title"] == "WS Card"


class TestSingletonGuard:
    """Test helpers that prevent duplicate server instances."""

    def test_is_pid_alive_current_process(self):
        """Current process PID should be alive."""
        import os

        from m4.vitrine.server import _is_pid_alive

        assert _is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_dead_pid(self):
        """Non-existent PID should not be alive."""
        from m4.vitrine.server import _is_pid_alive

        assert _is_pid_alive(999999999) is False

    def test_check_health_on_running_server(self, store):
        """_check_health returns True for a running server."""
        from m4.vitrine.server import _check_health

        srv = DisplayServer(
            store=store,
            port=7748,
            host="127.0.0.1",
            session_id="health-test",
        )
        srv.start(open_browser=False)
        actual_port = srv.port
        url = f"http://127.0.0.1:{actual_port}"
        try:
            assert _check_health(url, "health-test") is True
            # Wrong session_id should fail
            assert _check_health(url, "wrong-id") is False
            # No session_id check should pass
            assert _check_health(url) is True
        finally:
            srv.stop()

    def test_check_health_on_dead_port(self):
        """_check_health returns False for a port with no server."""
        from m4.vitrine.server import _check_health

        assert _check_health("http://127.0.0.1:7790") is False


class TestSelectionPersistence:
    """Test that selections are persisted to disk and loaded on restart."""

    def test_selections_saved_and_loaded(self, tmp_path):
        """Selections are saved to JSON and reloaded on new server."""
        from starlette.testclient import TestClient

        mgr = StudyManager(tmp_path / "sel_display")
        _, store = mgr.get_or_create_study("sel-test")
        dir_name = mgr._label_to_dir["sel-test"]

        srv = DisplayServer(
            study_manager=mgr,
            port=7796,
            host="127.0.0.1",
            session_id="sel-test",
        )

        # Store a card so selection has a target
        card_desc = render("text", title="T", store=store, study="sel-test")
        mgr.register_card(card_desc.card_id, dir_name)

        client = TestClient(srv._app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # drain replay
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "selection",
                    "card_id": card_desc.card_id,
                    "payload": {"selected_indices": [0, 2, 4]},
                }
            )
            import time

            time.sleep(0.3)

        assert srv._selections[card_desc.card_id] == [0, 2, 4]

        # Force flush
        srv._save_selections()

        # Verify file exists
        assert srv._selections_path.exists()

        # Create new server instance -- should load persisted selections
        srv2 = DisplayServer(
            study_manager=mgr,
            port=7796,
            host="127.0.0.1",
            session_id="sel-test",
        )
        assert srv2._selections.get(card_desc.card_id) == [0, 2, 4]

    def test_empty_selections_saved(self, tmp_path):
        """Empty selections are saved as empty dict."""
        mgr = StudyManager(tmp_path / "empty_sel_display")
        srv = DisplayServer(
            study_manager=mgr,
            port=7795,
            host="127.0.0.1",
            session_id="empty-sel-test",
        )
        srv._save_selections()
        # File should exist with empty dict
        assert srv._selections_path.exists()
        import json

        data = json.loads(srv._selections_path.read_text())
        assert data == {}


class TestExportEndpoints:
    """Test /api/export/html and /api/export/json REST endpoints."""

    @pytest.fixture
    def export_server(self, tmp_path):
        mgr = StudyManager(tmp_path / "export_display")
        _, s = mgr.get_or_create_study("export-test")
        render("# Export content", title="Doc", store=s, study="export-test")
        dir_name = mgr._label_to_dir["export-test"]
        card = s.list_cards()[0]
        mgr.register_card(card.card_id, dir_name)
        srv = DisplayServer(
            study_manager=mgr,
            port=7794,
            host="127.0.0.1",
            token="export-tok",
            session_id="export-test",
        )
        return srv

    def test_export_html_endpoint(self, export_server):
        from starlette.testclient import TestClient

        client = TestClient(export_server._app)
        resp = client.get(
            "/api/studies/export-test/export?format=html",
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Export content" in resp.text

    def test_export_json_endpoint(self, export_server):
        from starlette.testclient import TestClient

        client = TestClient(export_server._app)
        resp = client.get(
            "/api/studies/export-test/export?format=json",
        )
        assert resp.status_code == 200
        assert "application/zip" in resp.headers.get("content-type", "")


class TestConcurrentBlocking:
    """Test concurrent blocking show() calls."""

    def test_two_concurrent_responses(self, store):
        """Two pending responses can be resolved independently."""
        import asyncio
        import threading

        srv = DisplayServer(
            store=store,
            port=7793,
            host="127.0.0.1",
            session_id="concurrent-test",
        )

        loop = asyncio.new_event_loop()
        srv._loop = loop
        results = {}

        async def wait_both():
            """Wait for two responses concurrently on the same loop."""

            async def wait_card(card_id, key):
                r = await srv.wait_for_response(card_id, timeout=5.0)
                results[key] = r

            # Schedule both waits concurrently
            task_a = asyncio.ensure_future(wait_card("card-a", "a"))
            task_b = asyncio.ensure_future(wait_card("card-b", "b"))

            # Give futures time to register
            await asyncio.sleep(0.1)

            # Resolve them
            future_a = srv._pending_responses.get("card-a")
            if future_a and not future_a.done():
                future_a.set_result({"action": "confirm", "card_id": "card-a"})
            future_b = srv._pending_responses.get("card-b")
            if future_b and not future_b.done():
                future_b.set_result({"action": "skip", "card_id": "card-b"})

            await task_a
            await task_b

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(wait_both())

        t = threading.Thread(target=run_loop)
        t.start()
        t.join(timeout=10)
        loop.close()

        assert results["a"]["action"] == "confirm"
        assert results["b"]["action"] == "skip"


class TestWebSocketDisconnect:
    """Test WebSocket disconnect during pending response."""

    def test_disconnect_leaves_future_unresolved(self, store):
        """Disconnecting client leaves pending future unresolved; server doesn't crash."""
        import asyncio

        srv = DisplayServer(
            store=store,
            port=7792,
            host="127.0.0.1",
            session_id="disconnect-test",
        )

        loop = asyncio.new_event_loop()
        srv._loop = loop

        # Manually register a pending future (simulating wait_for_response)
        future = loop.create_future()
        srv._pending_responses["disc-card"] = future

        # Future should not be resolved since no one responded
        assert not future.done()

        # Verify timeout behavior works
        result = loop.run_until_complete(
            srv.wait_for_response("disc-card-2", timeout=0.1)
        )
        assert result["action"] == "timeout"
        loop.close()
