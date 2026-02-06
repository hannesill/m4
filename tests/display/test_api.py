"""Tests for m4.display public API (show, start, stop, clear, section).

Tests cover:
- show() returns a card_id
- show() stores cards in artifact store
- show() with different object types
- clear() removes cards
- section() creates section cards
- Module state management
"""

import pandas as pd
import pytest

import m4.display as display
from m4.display._types import CardType
from m4.display.artifacts import ArtifactStore


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    display._server = None
    display._store = None
    display._session_id = None
    yield
    # Clean up
    if display._server is not None:
        try:
            display._server.stop()
        except Exception:
            pass
    display._server = None
    display._store = None
    display._session_id = None


@pytest.fixture
def store(tmp_path):
    """Create a store and inject it into the module state."""
    session_dir = tmp_path / "api_session"
    store = ArtifactStore(session_dir=session_dir, session_id="api-test")
    display._store = store
    display._session_id = "api-test"
    return store


@pytest.fixture
def mock_server(store, monkeypatch):
    """Mock the server to avoid actually starting it."""

    class MockServer:
        is_running = True

        def __init__(self):
            self.pushed_cards = []
            self.pushed_sections = []
            self.pushed_clears = []

        def start(self, open_browser=True):
            pass

        def stop(self):
            self.is_running = False

        def push_card(self, card):
            self.pushed_cards.append(card)

        def push_section(self, title, run_id=None):
            self.pushed_sections.append((title, run_id))

        def push_clear(self, keep_pinned=True):
            self.pushed_clears.append(keep_pinned)

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
        display.show("text", run_id="my-run")
        cards = store.list_cards()
        assert cards[0].run_id == "my-run"

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


class TestClear:
    def test_clears_store(self, store, mock_server):
        display.show("card 1")
        display.show("card 2")
        assert len(store.list_cards()) == 2
        display.clear()
        assert len(store.list_cards()) == 0

    def test_pushes_clear_to_server(self, store, mock_server):
        display.clear()
        assert len(mock_server.pushed_clears) == 1

    def test_clear_keeps_pinned(self, store, mock_server):
        display.show("card 1")
        card_id = display.show("card 2")
        store.update_card(card_id, pinned=True)
        display.clear(keep_pinned=True)
        remaining = store.list_cards()
        assert len(remaining) == 1
        assert remaining[0].pinned is True


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

    def test_stop_when_not_started(self):
        # Should not raise
        display.stop()

    def test_clear_when_no_store(self):
        # Should not raise
        display.clear()
