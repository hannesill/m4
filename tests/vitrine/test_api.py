"""Tests for m4.vitrine public API (show, start, stop, section).

Tests cover:
- show() returns a card_id
- show() stores cards in artifact store
- show() with different object types
- section() creates section cards
- Module state management
- Server discovery and client mode
- Blocking show (wait=True)
- get_selection()
- on_event() callback registration
- RunManager integration: list_runs, delete_run, clean_runs
- Multi-run show() calls
- Auto-run creation
- stop_server() preserves run data
"""

import json

import pandas as pd
import pytest

import m4.vitrine as display
from m4.vitrine._types import CardType, DisplayResponse
from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.run_manager import RunManager


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    display._server = None
    display._store = None
    display._run_manager = None
    display._current_run_id = None
    display._session_id = None
    display._remote_url = None
    display._auth_token = None
    yield
    # Clean up
    if display._server is not None:
        try:
            display._server.stop()
        except Exception:
            pass
    display._server = None
    display._store = None
    display._run_manager = None
    display._current_run_id = None
    display._session_id = None
    display._remote_url = None
    display._auth_token = None


@pytest.fixture
def store(tmp_path):
    """Create a store and inject it into the module state."""
    session_dir = tmp_path / "api_session"
    store = ArtifactStore(session_dir=session_dir, session_id="api-test")
    display._store = store
    display._session_id = "api-test"
    return store


@pytest.fixture
def run_manager(tmp_path):
    """Create a RunManager and inject it into module state."""
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    mgr = RunManager(display_dir)
    display._run_manager = mgr
    display._session_id = "rm-test"
    return mgr


@pytest.fixture
def mock_server(store, monkeypatch):
    """Mock the server to avoid actually starting it."""

    class MockServer:
        is_running = True

        def __init__(self):
            self.pushed_cards = []
            self.pushed_sections = []
            self.event_callbacks = []
            self._mock_response = {"action": "timeout", "card_id": ""}
            self._selections = {}

        def start(self, open_browser=True):
            pass

        def stop(self):
            self.is_running = False

        def push_card(self, card):
            self.pushed_cards.append(card)

        def push_update(self, card_id, card):
            self.pushed_cards.append(card)

        def push_section(self, title, run_id=None):
            self.pushed_sections.append((title, run_id))

        def wait_for_response_sync(self, card_id, timeout):
            return self._mock_response

        def register_event_callback(self, callback):
            self.event_callbacks.append(callback)

    mock = MockServer()
    display._server = mock
    return mock


class TestShow:
    def test_returns_card_id(self, store, mock_server):
        card_id = display.show("hello")
        assert isinstance(card_id, str)
        assert len(card_id) > 0

    def test_stores_markdown(self, store, mock_server):
        display.show("## Title")
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.MARKDOWN

    def test_stores_dataframe(self, store, mock_server):
        df = pd.DataFrame({"x": [1, 2, 3]})
        display.show(df, title="My Table")
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.TABLE
        assert cards[0].title == "My Table"

    def test_stores_dict(self, store, mock_server):
        display.show({"key": "value"})
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.KEYVALUE

    def test_with_title(self, store, mock_server):
        display.show("text", title="Finding")
        cards = store.list_cards()
        assert cards[0].title == "Finding"

    def test_with_run_id(self, store, mock_server):
        handle = display.show("text", run_id="my-run")
        cards = store.list_cards()
        assert cards[0].run_id == "my-run"
        assert getattr(handle, "url", None) is not None
        assert "#run=my-run" in handle.url

    def test_with_source(self, store, mock_server):
        display.show("text", source="mimiciv_hosp.patients")
        cards = store.list_cards()
        assert cards[0].provenance is not None
        assert cards[0].provenance.source == "mimiciv_hosp.patients"

    def test_pushes_to_server(self, store, mock_server):
        display.show("hello")
        assert len(mock_server.pushed_cards) == 1

    def test_multiple_cards(self, store, mock_server):
        display.show("card 1")
        display.show("card 2")
        display.show("card 3")
        assert len(store.list_cards()) == 3
        assert len(mock_server.pushed_cards) == 3


class TestSection:
    def test_creates_section_card(self, store, mock_server):
        display.section("Results")
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.SECTION
        assert cards[0].title == "Results"

    def test_section_with_run_id(self, store, mock_server):
        display.section("Analysis", run_id="run-1")
        cards = store.list_cards()
        assert cards[0].run_id == "run-1"

    def test_pushes_to_server(self, store, mock_server):
        display.section("Title")
        assert len(mock_server.pushed_sections) == 1
        assert mock_server.pushed_sections[0] == ("Title", None)


class TestReplace:
    def test_replace_creates_new_card(self, store, mock_server):
        card_id = display.show("original")
        new_id = display.show("updated", replace=card_id)
        # replace creates a new card and updates the old one
        assert new_id != card_id

    def test_replace_pushes_to_server(self, store, mock_server):
        card_id = display.show("original")
        display.show("updated", replace=card_id)
        # Should push both the original and the replacement
        assert len(mock_server.pushed_cards) == 2


class TestModuleState:
    def test_initial_state(self):
        assert display._server is None
        assert display._store is None
        assert display._remote_url is None
        assert display._auth_token is None

    def test_stop_when_not_started(self):
        # Should not raise
        display.stop()


class TestDiscovery:
    def test_discover_no_pid_file(self, monkeypatch, tmp_path):
        """Discovery returns None when no PID file exists."""
        monkeypatch.setattr(
            display, "_pid_file_path", lambda: tmp_path / ".server.json"
        )
        result = display._discover_server()
        assert result is None

    def test_discover_stale_pid(self, monkeypatch, tmp_path):
        """Discovery cleans up PID file when process is dead."""
        pid_path = tmp_path / ".server.json"
        pid_path.write_text(
            json.dumps(
                {
                    "pid": 999999999,  # Very unlikely to be a real PID
                    "port": 7741,
                    "host": "127.0.0.1",
                    "url": "http://127.0.0.1:7741",
                    "session_id": "dead-session",
                    "token": "tok",
                }
            )
        )
        monkeypatch.setattr(display, "_pid_file_path", lambda: pid_path)
        monkeypatch.setattr(display, "_is_process_alive", lambda pid: False)

        result = display._discover_server()
        assert result is None
        assert not pid_path.exists()

    def test_discover_health_check_fails(self, monkeypatch, tmp_path):
        """Discovery cleans up PID file when health check fails."""
        import os

        pid_path = tmp_path / ".server.json"
        pid_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "port": 7741,
                    "host": "127.0.0.1",
                    "url": "http://127.0.0.1:7741",
                    "session_id": "bad-session",
                    "token": "tok",
                }
            )
        )
        monkeypatch.setattr(display, "_pid_file_path", lambda: pid_path)
        monkeypatch.setattr(display, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(display, "_health_check", lambda url, sid: False)

        result = display._discover_server()
        assert result is None

    def test_discover_valid_server(self, monkeypatch, tmp_path):
        """Discovery returns info when process alive and health check passes."""
        import os

        info = {
            "pid": os.getpid(),
            "port": 7741,
            "host": "127.0.0.1",
            "url": "http://127.0.0.1:7741",
            "session_id": "valid-session",
            "token": "secret-tok",
        }
        pid_path = tmp_path / ".server.json"
        pid_path.write_text(json.dumps(info))
        monkeypatch.setattr(display, "_pid_file_path", lambda: pid_path)
        monkeypatch.setattr(display, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(display, "_health_check", lambda url, sid: True)

        result = display._discover_server()
        assert result is not None
        assert result["session_id"] == "valid-session"
        assert result["token"] == "secret-tok"

    def test_is_process_alive_current_pid(self):
        """Current process should be alive."""
        import os

        assert display._is_process_alive(os.getpid()) is True

    def test_is_process_alive_dead_pid(self):
        """Non-existent PID should not be alive."""
        assert display._is_process_alive(999999999) is False

    def test_server_status_returns_none(self, monkeypatch, tmp_path):
        """server_status() returns None when no server running."""
        monkeypatch.setattr(
            display, "_pid_file_path", lambda: tmp_path / ".server.json"
        )
        assert display.server_status() is None


class TestClientMode:
    """Test that show/section push via HTTP when _remote_url is set.

    _ensure_started is monkeypatched to a no-op since we're testing the
    push path, not the discovery/startup flow.
    """

    def test_show_uses_remote_command(self, store, monkeypatch):
        """show() pushes via _remote_command when _remote_url is set."""
        commands_sent = []

        def mock_remote_command(url, token, payload):
            commands_sent.append((url, token, payload))
            return True

        display._remote_url = "http://127.0.0.1:7741"
        display._auth_token = "test-token"
        monkeypatch.setattr(display, "_ensure_started", lambda **kw: None)
        monkeypatch.setattr(display, "_remote_command", mock_remote_command)

        card_id = display.show("hello")
        assert isinstance(card_id, str)
        assert len(commands_sent) == 1
        assert commands_sent[0][0] == "http://127.0.0.1:7741"
        assert commands_sent[0][1] == "test-token"
        assert commands_sent[0][2]["type"] == "card"

    def test_section_uses_remote_command(self, store, monkeypatch):
        """section() pushes via _remote_command when _remote_url is set."""
        commands_sent = []

        def mock_remote_command(url, token, payload):
            commands_sent.append(payload)
            return True

        display._remote_url = "http://127.0.0.1:7741"
        display._auth_token = "test-token"
        monkeypatch.setattr(display, "_ensure_started", lambda **kw: None)
        monkeypatch.setattr(display, "_remote_command", mock_remote_command)

        display.section("Results", run_id="r1")
        assert len(commands_sent) == 1
        assert commands_sent[0]["type"] == "section"
        assert commands_sent[0]["title"] == "Results"
        assert commands_sent[0]["run_id"] == "r1"


class TestBlockingShow:
    def test_wait_returns_display_response(self, store, mock_server):
        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "message": "Looks good",
            "artifact_id": None,
        }
        result = display.show("hello", wait=True)
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"
        assert result.message == "Looks good"

    def test_wait_timeout_returns_timeout_action(self, store, mock_server):
        mock_server._mock_response = {
            "action": "timeout",
            "card_id": "test",
        }
        result = display.show("hello", wait=True, timeout=1)
        assert isinstance(result, DisplayResponse)
        assert result.action == "timeout"

    def test_wait_skip_returns_skip_action(self, store, mock_server):
        mock_server._mock_response = {
            "action": "skip",
            "card_id": "test",
        }
        result = display.show("hello", wait=True)
        assert isinstance(result, DisplayResponse)
        assert result.action == "skip"

    def test_wait_sets_response_requested(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        display.show("hello", wait=True)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].response_requested is True

    def test_prompt_stored_in_card(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        display.show("hello", wait=True, prompt="Pick patients")
        cards = store.list_cards()
        assert cards[0].prompt == "Pick patients"

    def test_response_data_accessor(self, store, mock_server):
        """DisplayResponse.data() loads artifact when available."""
        # Store a selection artifact manually
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        store.store_dataframe("resp-sel1", df)

        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "artifact_id": "resp-sel1",
        }
        result = display.show("hello", wait=True)
        assert result.artifact_id == "resp-sel1"
        loaded = result.data()
        assert loaded is not None
        assert len(loaded) == 2
        assert list(loaded.columns) == ["id", "name"]

    def test_response_data_returns_none_without_artifact(self, store, mock_server):
        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "artifact_id": None,
        }
        result = display.show("hello", wait=True)
        assert result.data() is None

    def test_non_wait_returns_card_id_string(self, store, mock_server):
        result = display.show("hello", wait=False)
        assert isinstance(result, str)


class TestActions:
    def test_actions_stored_in_card(self, store, mock_server):
        mock_server._mock_response = {"action": "Approve", "card_id": "x"}
        display.show("hello", wait=True, actions=["Approve", "Reject"])
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].actions == ["Approve", "Reject"]

    def test_actions_in_serialized_card(self, store, mock_server):
        from m4.vitrine.artifacts import _serialize_card

        mock_server._mock_response = {"action": "Run", "card_id": "x"}
        display.show("hello", wait=True, actions=["Run", "Skip"])
        card = store.list_cards()[0]
        serialized = _serialize_card(card)
        assert serialized["actions"] == ["Run", "Skip"]

    def test_actions_response_carries_action_name(self, store, mock_server):
        mock_server._mock_response = {
            "action": "Reject",
            "card_id": "test",
        }
        result = display.show("hello", wait=True, actions=["Approve", "Reject"])
        assert isinstance(result, DisplayResponse)
        assert result.action == "Reject"


class TestGetSelection:
    def test_get_selection_returns_selected_rows(self, store, mock_server):
        """get_selection returns selected rows from in-process server."""
        df = pd.DataFrame({"a": [10, 20, 30]})
        card_id = "sel-card"
        store.store_dataframe(card_id, df)
        # Simulate selection state on mock server
        mock_server._selections = {card_id: [0, 2]}
        result = display.get_selection(card_id)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert list(result["a"]) == [10, 30]

    def test_get_selection_empty_when_no_selection(self, store, mock_server):
        mock_server._selections = {}
        result = display.get_selection("any-card")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_get_selection_empty_without_server(self, monkeypatch):
        """get_selection returns empty DataFrame when no server available."""
        monkeypatch.setattr(display, "_ensure_started", lambda **kw: None)
        result = display.get_selection("anything")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


class TestOnEvent:
    def test_on_event_registers_callback(self, store, mock_server):
        def my_callback(event):
            pass

        display.on_event(my_callback)
        assert len(mock_server.event_callbacks) == 1
        assert mock_server.event_callbacks[0] is my_callback

    def test_on_event_multiple_callbacks(self, store, mock_server):
        display.on_event(lambda e: None)
        display.on_event(lambda e: None)
        assert len(mock_server.event_callbacks) == 2


class TestListRuns:
    def test_list_runs_empty(self, run_manager):
        assert display.list_runs() == []

    def test_list_runs_after_show(self, run_manager, mock_server):
        display.show("hello", run_id="test-run")
        runs = display.list_runs()
        assert len(runs) == 1
        assert runs[0]["label"] == "test-run"
        assert runs[0]["card_count"] == 1

    def test_list_runs_multiple(self, run_manager, mock_server):
        display.show("card-a", run_id="run-a")
        display.show("card-b", run_id="run-b")
        runs = display.list_runs()
        assert len(runs) == 2
        labels = {r["label"] for r in runs}
        assert labels == {"run-a", "run-b"}


class TestDeleteRun:
    def test_delete_existing_run(self, run_manager, mock_server):
        display.show("hello", run_id="to-delete")
        assert len(display.list_runs()) == 1
        result = display.delete_run("to-delete")
        assert result is True
        assert display.list_runs() == []

    def test_delete_nonexistent_run(self, run_manager):
        assert display.delete_run("nope") is False


class TestSetStatus:
    def test_set_status_in_process(self, store, mock_server):
        """set_status pushes to in-process server."""
        mock_server.push_status = lambda msg: None  # Add method to mock
        display.set_status("Analyzing...")
        # Should not raise

    def test_set_status_remote(self, store, monkeypatch):
        """set_status pushes via remote command when remote."""
        commands_sent = []

        def mock_remote_command(url, token, payload):
            commands_sent.append(payload)
            return True

        display._remote_url = "http://127.0.0.1:7741"
        display._auth_token = "test-token"
        monkeypatch.setattr(display, "_ensure_started", lambda **kw: None)
        monkeypatch.setattr(display, "_remote_command", mock_remote_command)

        display.set_status("Working...")
        assert len(commands_sent) == 1
        assert commands_sent[0]["type"] == "status"
        assert commands_sent[0]["message"] == "Working..."


class TestRunContext:
    def test_run_context_with_cards(self, run_manager, mock_server):
        display.show("hello", run_id="ctx-test", title="Card 1")
        ctx = display.run_context("ctx-test")
        assert ctx["run_id"] == "ctx-test"
        assert ctx["card_count"] == 1
        assert len(ctx["cards"]) == 1
        assert ctx["cards"][0]["title"] == "Card 1"
        assert "pending_responses" in ctx
        assert "decisions_made" in ctx
        assert "current_selections" in ctx

    def test_run_context_nonexistent(self, run_manager):
        ctx = display.run_context("nonexistent")
        assert ctx["card_count"] == 0
        assert ctx["cards"] == []


class TestCleanRuns:
    def test_clean_removes_all(self, run_manager, mock_server):
        display.show("card-a", run_id="old-a")
        display.show("card-b", run_id="old-b")
        removed = display.clean_runs("0d")
        assert removed == 2
        assert display.list_runs() == []

    def test_clean_keeps_recent(self, run_manager, mock_server):
        display.show("card", run_id="recent")
        removed = display.clean_runs("1d")
        assert removed == 0
        assert len(display.list_runs()) == 1


class TestAutoRun:
    def test_show_without_run_id_creates_auto(self, run_manager, mock_server):
        display.show("hello")
        runs = display.list_runs()
        assert len(runs) == 1
        assert runs[0]["label"].startswith("auto-")

    def test_multiple_shows_without_run_id(self, run_manager, mock_server):
        """Multiple show() calls without run_id reuse the same auto-run."""
        display.show("card 1")
        display.show("card 2")
        runs = display.list_runs()
        # Both cards go into the same auto-run (same timestamp within test)
        assert len(runs) == 1
        assert runs[0]["card_count"] == 2


class TestMultiRunShow:
    def test_different_run_ids_create_separate_runs(self, run_manager, mock_server):
        display.show("card-a", run_id="run-a")
        display.show("card-b", run_id="run-b")
        display.show("card-a2", run_id="run-a")

        runs = display.list_runs()
        assert len(runs) == 2

        # run-a should have 2 cards
        run_a = next(r for r in runs if r["label"] == "run-a")
        assert run_a["card_count"] == 2

        # run-b should have 1 card
        run_b = next(r for r in runs if r["label"] == "run-b")
        assert run_b["card_count"] == 1


class TestStopServerPreservesData:
    def test_stop_preserves_run_data(self, run_manager, mock_server, tmp_path):
        """stop_server() should not delete run data."""
        display.show("persistent", run_id="keep-me")
        runs_before = display.list_runs()
        assert len(runs_before) == 1

        # Verify the run directory exists
        run_dir = run_manager._runs_dir / run_manager._label_to_dir["keep-me"]
        assert run_dir.exists()

        # Simulate stop (stop the mock server)
        display.stop()

        # Run directory should still exist on disk
        assert run_dir.exists()

        # Create a new RunManager (simulates restart) — data should be discovered
        mgr2 = RunManager(run_manager.display_dir)
        assert "keep-me" in mgr2._label_to_dir
        runs_after = mgr2.list_runs()
        assert len(runs_after) == 1
        assert runs_after[0]["label"] == "keep-me"


class TestFileLocking:
    """Test file lock and port scan helpers in the display module."""

    def test_lock_file_path(self, tmp_path, monkeypatch):
        """_lock_file_path returns correct path."""
        monkeypatch.setattr(display, "_get_vitrine_dir", lambda: tmp_path / "vitrine")
        path = display._lock_file_path()
        assert path == tmp_path / "vitrine" / ".server.lock"

    def test_scan_port_range_returns_none_when_empty(self):
        """Scanning unused ports returns None."""
        result = display._scan_port_range("127.0.0.1", 7790, 7792)
        assert result is None
