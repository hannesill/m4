"""Tests for m4.display.server.

Tests cover:
- DisplayServer creation and port finding
- REST endpoints (cards, table paging, clear, session)
- WebSocket connection and card replay
- Static file serving
- Health, command, and shutdown endpoints
- Auth token enforcement
"""

import pandas as pd
import pytest

from m4.display.artifacts import ArtifactStore
from m4.display.renderer import render
from m4.display.server import DisplayServer

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
        assert server.url == "http://127.0.0.1:7799"


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

    def test_api_cards_filter_by_run_id(self, app, store):
        from starlette.testclient import TestClient

        render("text1", run_id="run-a", store=store)
        render("text2", run_id="run-b", store=store)
        render("text3", run_id="run-a", store=store)

        client = TestClient(app)

        # All cards
        resp = client.get("/api/cards")
        assert len(resp.json()) == 3

        # Filter by run-a
        resp = client.get("/api/cards?run_id=run-a")
        cards = resp.json()
        assert len(cards) == 2
        assert all(c["run_id"] == "run-a" for c in cards)

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

    def test_api_clear(self, app, store):
        from starlette.testclient import TestClient

        render("card 1", store=store)
        render("card 2", store=store)
        assert len(store.list_cards()) == 2

        client = TestClient(app)
        resp = client.post(
            "/api/clear",
            json={"keep_pinned": False},
        )
        assert resp.status_code == 200
        assert store.list_cards() == []

    def test_api_clear_keeps_pinned(self, app, store):
        from starlette.testclient import TestClient

        render("card 1", store=store)
        card2 = render("card 2", store=store)
        store.update_card(card2.card_id, pinned=True)
        assert len(store.list_cards()) == 2

        client = TestClient(app)
        resp = client.post(
            "/api/clear",
            json={"keep_pinned": True},
        )
        assert resp.status_code == 200
        remaining = store.list_cards()
        assert len(remaining) == 1
        assert remaining[0].card_id == card2.card_id

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
        assert "M4 Display" in resp.text

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
            json={"type": "section", "title": "Results", "run_id": "r1"},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_command_clear(self, app, store):
        from starlette.testclient import TestClient

        render("card 1", store=store)
        assert len(store.list_cards()) == 1

        client = TestClient(app)
        resp = client.post(
            "/api/command",
            json={"type": "clear", "keep_pinned": False},
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
        assert resp.status_code == 200
        assert store.list_cards() == []

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
