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
- StudyManager integration: list_studies, delete_study, clean_studies
- Multi-study show() calls
- Auto-study creation
- stop_server() preserves study data
"""

import json

import pandas as pd
import pytest

import m4.vitrine as display
from m4.vitrine._types import CardType, DisplayResponse
from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.study_manager import StudyManager


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    display._server = None
    display._store = None
    display._study_manager = None
    display._current_study = None
    display._session_id = None
    display._remote_url = None
    display._auth_token = None
    display._event_callbacks.clear()
    display._event_poll_thread = None
    display._event_poll_stop.clear()
    yield
    # Clean up
    if display._server is not None:
        try:
            display._server.stop()
        except Exception:
            pass
    display._server = None
    display._store = None
    display._study_manager = None
    display._current_study = None
    display._session_id = None
    display._remote_url = None
    display._auth_token = None
    display._event_callbacks.clear()
    display._event_poll_thread = None
    display._event_poll_stop.clear()


@pytest.fixture
def store(tmp_path):
    """Create a store and inject it into the module state."""
    session_dir = tmp_path / "api_session"
    store = ArtifactStore(session_dir=session_dir, session_id="api-test")
    display._store = store
    display._session_id = "api-test"
    return store


@pytest.fixture
def study_manager(tmp_path):
    """Create a StudyManager and inject it into module state."""
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    mgr = StudyManager(display_dir)
    display._study_manager = mgr
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

        def push_section(self, title, study=None):
            self.pushed_sections.append((title, study))

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

    def test_with_study(self, store, mock_server):
        handle = display.show("text", study="my-study")
        cards = store.list_cards()
        assert cards[0].study == "my-study"
        assert getattr(handle, "url", None) is not None
        assert "#study=my-study" in handle.url

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

    def test_section_with_study(self, store, mock_server):
        display.section("Analysis", study="study-1")
        cards = store.list_cards()
        assert cards[0].study == "study-1"

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


class TestServerLifecycle:
    def test_server_status_returns_none_without_pid_file(self, monkeypatch):
        """server_status() returns None when PID file is absent (no port scan)."""
        monkeypatch.setattr(display, "_discover_server", lambda: None)
        assert display.server_status() is None

    def test_stop_server_keeps_pid_file_when_shutdown_fails(
        self, monkeypatch, tmp_path
    ):
        """stop_server() should not remove PID metadata if server is still healthy."""
        pid_path = tmp_path / ".server.json"
        pid_path.write_text("{}")
        monkeypatch.setattr(display, "_pid_file_path", lambda: pid_path)
        monkeypatch.setattr(
            display,
            "_discover_server",
            lambda: {
                "url": "http://127.0.0.1:7741",
                "session_id": "sess-1",
                "token": "tok",
                "pid": None,
            },
        )
        monkeypatch.setattr(display, "_health_check", lambda url, sid: True)

        import urllib.request

        def _raise(*args, **kwargs):
            raise OSError("network down")

        monkeypatch.setattr(urllib.request, "urlopen", _raise)

        assert display.stop_server() is False
        assert pid_path.exists()

    def test_stop_server_removes_pid_file_after_success(self, monkeypatch, tmp_path):
        """stop_server() should clean up PID metadata once server stops."""
        pid_path = tmp_path / ".server.json"
        pid_path.write_text("{}")
        monkeypatch.setattr(display, "_pid_file_path", lambda: pid_path)
        monkeypatch.setattr(
            display,
            "_discover_server",
            lambda: {
                "url": "http://127.0.0.1:7741",
                "session_id": "sess-1",
                "token": "tok",
                "pid": None,
            },
        )
        monkeypatch.setattr(display, "_health_check", lambda url, sid: False)

        import urllib.request

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _Resp())

        assert display.stop_server() is True
        assert not pid_path.exists()

    def test_stop_delegates_to_persistent_server_when_remote(self, monkeypatch):
        """stop() should stop the persistent server when connected remotely."""
        calls = []
        display._remote_url = "http://127.0.0.1:7741"
        monkeypatch.setattr(
            display,
            "stop_server",
            lambda: calls.append("called") or True,
        )
        display.stop()
        assert calls == ["called"]

    def test_start_process_uses_devnull_stderr(self, monkeypatch):
        """_start_process should not leave stderr pipe unread."""
        import subprocess

        captured = {}

        def _fake_popen(cmd, stdout=None, stderr=None, start_new_session=None):
            captured["cmd"] = cmd
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            captured["start_new_session"] = start_new_session
            return None

        monkeypatch.setattr(subprocess, "Popen", _fake_popen)
        display._start_process(port=7749, open_browser=False)

        assert captured["stdout"] is subprocess.DEVNULL
        assert captured["stderr"] is subprocess.DEVNULL
        assert captured["start_new_session"] is True
        assert "--no-open" in captured["cmd"]


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

        display.section("Results", study="r1")
        assert len(commands_sent) == 1
        assert commands_sent[0]["type"] == "section"
        assert commands_sent[0]["title"] == "Results"
        assert commands_sent[0]["study"] == "r1"


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


class TestFormAutoWait:
    def test_form_auto_blocks(self, store, mock_server):
        """show(Form(...)) auto-sets wait=True and returns DisplayResponse."""
        from m4.vitrine._types import Dropdown, Form

        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "values": {"method": "logistic"},
        }
        result = display.show(Form([Dropdown("method", ["logistic", "cox"])]))
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"

    def test_form_explicit_wait_false_still_blocks(self, store, mock_server):
        """show(Form(...), wait=False) still blocks because forms force wait=True."""
        from m4.vitrine._types import Dropdown, Form

        mock_server._mock_response = {"action": "skip", "card_id": "test"}
        result = display.show(
            Form([Dropdown("method", ["logistic", "cox"])]), wait=False
        )
        assert isinstance(result, DisplayResponse)
        assert result.action == "skip"

    def test_form_renders_as_form_card(self, store, mock_server):
        """Form cards are stored as FORM with preview.fields."""
        from m4.vitrine._types import Dropdown, Form

        mock_server._mock_response = {"action": "confirm", "card_id": "test"}
        display.show(Form([Dropdown("method", ["logistic", "cox"])]))
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.FORM
        assert "fields" in cards[0].preview

    def test_form_sets_response_requested(self, store, mock_server):
        """Form cards always have response_requested=True."""
        from m4.vitrine._types import Dropdown, Form

        mock_server._mock_response = {"action": "confirm", "card_id": "test"}
        display.show(Form([Dropdown("method", ["logistic", "cox"])]))
        cards = store.list_cards()
        assert cards[0].response_requested is True

    def test_controls_auto_blocks(self, store, mock_server):
        """show(df, controls=[...]) auto-sets wait=True."""
        from m4.vitrine._types import Dropdown

        mock_server._mock_response = {"action": "confirm", "card_id": "test"}
        import pandas as pd

        df = pd.DataFrame({"x": [1, 2]})
        result = display.show(df, controls=[Dropdown("method", ["a", "b"])])
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"


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


class TestListStudies:
    def test_list_studies_empty(self, study_manager):
        assert display.list_studies() == []

    def test_list_studies_after_show(self, study_manager, mock_server):
        display.show("hello", study="test-study")
        studies = display.list_studies()
        assert len(studies) == 1
        assert studies[0]["label"] == "test-study"
        assert studies[0]["card_count"] == 1

    def test_list_studies_multiple(self, study_manager, mock_server):
        display.show("card-a", study="study-a")
        display.show("card-b", study="study-b")
        studies = display.list_studies()
        assert len(studies) == 2
        labels = {r["label"] for r in studies}
        assert labels == {"study-a", "study-b"}


class TestDeleteStudy:
    def test_delete_existing_study(self, study_manager, mock_server):
        display.show("hello", study="to-delete")
        assert len(display.list_studies()) == 1
        result = display.delete_study("to-delete")
        assert result is True
        assert display.list_studies() == []

    def test_delete_nonexistent_study(self, study_manager):
        assert display.delete_study("nope") is False


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


class TestStudyContext:
    def test_study_context_with_cards(self, study_manager, mock_server):
        display.show("hello", study="ctx-test", title="Card 1")
        ctx = display.study_context("ctx-test")
        assert ctx["study"] == "ctx-test"
        assert ctx["card_count"] == 1
        assert len(ctx["cards"]) == 1
        assert ctx["cards"][0]["title"] == "Card 1"
        assert "pending_responses" in ctx
        assert "decisions_made" in ctx
        assert "current_selections" in ctx

    def test_study_context_nonexistent(self, study_manager):
        ctx = display.study_context("nonexistent")
        assert ctx["card_count"] == 0
        assert ctx["cards"] == []


class TestCleanStudies:
    def test_clean_removes_all(self, study_manager, mock_server):
        display.show("card-a", study="old-a")
        display.show("card-b", study="old-b")
        removed = display.clean_studies("0d")
        assert removed == 2
        assert display.list_studies() == []

    def test_clean_keeps_recent(self, study_manager, mock_server):
        display.show("card", study="recent")
        removed = display.clean_studies("1d")
        assert removed == 0
        assert len(display.list_studies()) == 1


class TestAutoStudy:
    def test_show_without_study_creates_auto(self, study_manager, mock_server):
        display.show("hello")
        studies = display.list_studies()
        assert len(studies) == 1
        assert studies[0]["label"].startswith("auto-")

    def test_multiple_shows_without_study(self, study_manager, mock_server):
        """Multiple show() calls without study reuse the same auto-study."""
        display.show("card 1")
        display.show("card 2")
        studies = display.list_studies()
        # Both cards go into the same auto-study (same timestamp within test)
        assert len(studies) == 1
        assert studies[0]["card_count"] == 2


class TestMultiStudyShow:
    def test_different_studies_create_separate_studies(
        self, study_manager, mock_server
    ):
        display.show("card-a", study="study-a")
        display.show("card-b", study="study-b")
        display.show("card-a2", study="study-a")

        studies = display.list_studies()
        assert len(studies) == 2

        # study-a should have 2 cards
        study_a = next(r for r in studies if r["label"] == "study-a")
        assert study_a["card_count"] == 2

        # study-b should have 1 card
        study_b = next(r for r in studies if r["label"] == "study-b")
        assert study_b["card_count"] == 1


class TestStopServerPreservesData:
    def test_stop_preserves_study_data(self, study_manager, mock_server, tmp_path):
        """stop_server() should not delete study data."""
        display.show("persistent", study="keep-me")
        studies_before = display.list_studies()
        assert len(studies_before) == 1

        # Verify the study directory exists
        study_dir = study_manager._studies_dir / study_manager._label_to_dir["keep-me"]
        assert study_dir.exists()

        # Simulate stop (stop the mock server)
        display.stop()

        # Study directory should still exist on disk
        assert study_dir.exists()

        # Create a new StudyManager (simulates restart) — data should be discovered
        mgr2 = StudyManager(study_manager.display_dir)
        assert "keep-me" in mgr2._label_to_dir
        studies_after = mgr2.list_studies()
        assert len(studies_after) == 1
        assert studies_after[0]["label"] == "keep-me"


class TestErrorLogging:
    """Test that error/warning logs are emitted for failure scenarios."""

    def test_push_remote_logs_on_rediscovery_failure(
        self, store, mock_server, monkeypatch, caplog
    ):
        """_push_remote logs warning when re-discovery fails."""
        import logging

        # Set up remote mode
        display._remote_url = "http://127.0.0.1:9999"
        display._auth_token = "fake-token"

        # _remote_command always fails
        monkeypatch.setattr(display, "_remote_command", lambda *a: False)
        # _discover_server returns None (can't find server)
        monkeypatch.setattr(display, "_discover_server", lambda: None)

        with caplog.at_level(logging.WARNING, logger="m4.vitrine"):
            result = display._push_remote({"card_type": "markdown"})

        assert result is False
        assert "re-discovery failed" in caplog.text

    def test_push_remote_logs_on_retry_failure(
        self, store, mock_server, monkeypatch, caplog
    ):
        """_push_remote logs warning when retry after re-discovery fails."""
        import logging

        display._remote_url = "http://127.0.0.1:9999"
        display._auth_token = "fake-token"

        monkeypatch.setattr(display, "_remote_command", lambda *a: False)
        monkeypatch.setattr(
            display,
            "_discover_server",
            lambda: {"url": "http://127.0.0.1:9998", "token": "t"},
        )

        with caplog.at_level(logging.WARNING, logger="m4.vitrine"):
            result = display._push_remote({"card_type": "markdown"})

        assert result is False
        assert "failed after re-discovery" in caplog.text

    def test_poll_remote_response_http_error(self, monkeypatch, caplog):
        """_poll_remote_response returns error action on HTTPError."""
        import logging
        import urllib.error

        display._remote_url = "http://127.0.0.1:9999"
        display._auth_token = "fake-token"

        def mock_urlopen(*a, **kw):
            raise urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING, logger="m4.vitrine"):
            result = display._poll_remote_response("card-123", timeout=1.0)

        assert result["action"] == "error"
        assert result["card_id"] == "card-123"
        assert "HTTP error 403" in caplog.text

    def test_poll_remote_response_url_error(self, monkeypatch, caplog):
        """_poll_remote_response returns timeout action on URLError."""
        import logging
        import urllib.error

        display._remote_url = "http://127.0.0.1:9999"
        display._auth_token = "fake-token"

        def mock_urlopen(*a, **kw):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING, logger="m4.vitrine"):
            result = display._poll_remote_response("card-456", timeout=1.0)

        assert result["action"] == "timeout"
        assert result["card_id"] == "card-456"
        assert "connection error" in caplog.text

    def test_get_selection_remote_logs_on_failure(self, store, monkeypatch, caplog):
        """get_selection logs warning when remote fetch fails."""
        import logging

        # Bypass _ensure_started and force remote path
        monkeypatch.setattr(display, "_ensure_started", lambda **kw: None)
        display._server = None
        display._remote_url = "http://127.0.0.1:9999"

        def mock_urlopen(*a, **kw):
            raise ConnectionError("refused")

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING, logger="m4.vitrine"):
            result = display.get_selection("card-789")

        import pandas as pd

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert "Failed to fetch selection" in caplog.text


class TestFileLocking:
    """Test file lock and port scan helpers in the display module."""

    def test_lock_file_path(self, tmp_path, monkeypatch):
        """_lock_file_path returns correct path."""
        monkeypatch.setattr(display, "_get_vitrine_dir", lambda: tmp_path / "vitrine")
        path = display._lock_file_path()
        assert path == tmp_path / "vitrine" / ".server.lock"
