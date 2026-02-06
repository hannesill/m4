"""Tests for m4.display.run_manager.

Tests cover:
- Directory creation and run naming format
- get_or_create_run() creates new / returns existing
- Label reuse across calls
- get_store_for_card() lookups
- list_runs() metadata and sort order
- delete_run() removes dir and updates registry
- clean_runs() age-based removal
- Request queue methods
- Startup discovery from existing run directories
"""

import json
import time

import pytest

from m4.display.run_manager import (
    RunManager,
    _make_run_dir_name,
    _parse_age,
    _sanitize_label,
)


@pytest.fixture
def display_dir(tmp_path):
    """Create a temporary display directory."""
    d = tmp_path / "display"
    d.mkdir()
    return d


@pytest.fixture
def manager(display_dir):
    """Create a RunManager instance."""
    return RunManager(display_dir)


class TestSanitizeLabel:
    def test_basic(self):
        assert _sanitize_label("sepsis-mortality") == "sepsis-mortality"

    def test_spaces_and_special_chars(self):
        assert _sanitize_label("My Run #1") == "my-run-1"

    def test_truncation(self):
        result = _sanitize_label("a" * 100)
        assert len(result) <= 64

    def test_empty_string(self):
        assert _sanitize_label("") == "unnamed"

    def test_only_special_chars(self):
        assert _sanitize_label("!!!") == "unnamed"


class TestMakeRunDirName:
    def test_format(self):
        name = _make_run_dir_name("test-run")
        # Should match YYYY-MM-DD_HHMMSS_label pattern
        parts = name.split("_", 2)
        assert len(parts) == 3
        assert len(parts[0]) == 10  # YYYY-MM-DD
        assert len(parts[1]) == 6  # HHMMSS
        assert parts[2] == "test-run"


class TestParseAge:
    def test_days(self):
        assert _parse_age("7d") == 7 * 86400

    def test_hours(self):
        assert _parse_age("24h") == 24 * 3600

    def test_minutes(self):
        assert _parse_age("30m") == 30 * 60

    def test_seconds(self):
        assert _parse_age("60s") == 60

    def test_zero(self):
        assert _parse_age("0d") == 0

    def test_plain_number(self):
        assert _parse_age("300") == 300

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_age("abc")


class TestGetOrCreateRun:
    def test_creates_new_run(self, manager):
        label, store = manager.get_or_create_run("test-run")
        assert label == "test-run"
        assert store is not None
        assert (manager._runs_dir / manager._label_to_dir["test-run"]).exists()

    def test_returns_existing_run(self, manager):
        label1, store1 = manager.get_or_create_run("my-run")
        label2, store2 = manager.get_or_create_run("my-run")
        assert label1 == label2
        assert store1 is store2

    def test_auto_label(self, manager):
        label, store = manager.get_or_create_run(None)
        assert label.startswith("auto-")
        assert store is not None

    def test_different_labels_different_runs(self, manager):
        _, store1 = manager.get_or_create_run("run-a")
        _, store2 = manager.get_or_create_run("run-b")
        assert store1 is not store2

    def test_creates_meta_json(self, manager):
        label, _ = manager.get_or_create_run("meta-test")
        dir_name = manager._label_to_dir[label]
        meta_path = manager._runs_dir / dir_name / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["label"] == "meta-test"
        assert "start_time" in meta

    def test_updates_registry(self, manager):
        manager.get_or_create_run("reg-test")
        registry = manager._read_registry()
        assert len(registry) == 1
        assert registry[0]["label"] == "reg-test"


class TestStoreForCard:
    def test_lookup_registered_card(self, manager):
        _, store = manager.get_or_create_run("lookup-test")
        dir_name = manager._label_to_dir["lookup-test"]
        manager.register_card("card-123", dir_name)
        assert manager.get_store_for_card("card-123") is store

    def test_lookup_missing_card(self, manager):
        assert manager.get_store_for_card("nonexistent") is None


class TestListRuns:
    def test_empty(self, manager):
        assert manager.list_runs() == []

    def test_lists_created_runs(self, manager):
        manager.get_or_create_run("run-a")
        manager.get_or_create_run("run-b")
        runs = manager.list_runs()
        assert len(runs) == 2
        labels = {r["label"] for r in runs}
        assert labels == {"run-a", "run-b"}

    def test_sorted_newest_first(self, manager):
        manager.get_or_create_run("first")
        time.sleep(0.01)
        manager.get_or_create_run("second")
        runs = manager.list_runs()
        assert runs[0]["label"] == "second"
        assert runs[1]["label"] == "first"

    def test_includes_card_count(self, manager):
        _, store = manager.get_or_create_run("count-test")
        from m4.display.renderer import render

        render("hello", store=store)
        render("world", store=store)
        runs = manager.list_runs()
        assert runs[0]["card_count"] == 2


class TestDeleteRun:
    def test_deletes_existing(self, manager):
        manager.get_or_create_run("to-delete")
        dir_name = manager._label_to_dir["to-delete"]
        run_dir = manager._runs_dir / dir_name
        assert run_dir.exists()

        result = manager.delete_run("to-delete")
        assert result is True
        assert not run_dir.exists()
        assert "to-delete" not in manager._label_to_dir
        assert manager._read_registry() == []

    def test_delete_nonexistent(self, manager):
        assert manager.delete_run("nonexistent") is False

    def test_removes_card_index_entries(self, manager):
        _, _store = manager.get_or_create_run("idx-test")
        dir_name = manager._label_to_dir["idx-test"]
        manager.register_card("c1", dir_name)
        manager.register_card("c2", dir_name)
        assert manager.get_store_for_card("c1") is not None

        manager.delete_run("idx-test")
        assert manager.get_store_for_card("c1") is None
        assert manager.get_store_for_card("c2") is None


class TestCleanRuns:
    def test_removes_all_with_zero(self, manager):
        manager.get_or_create_run("old-a")
        manager.get_or_create_run("old-b")
        removed = manager.clean_runs("0d")
        assert removed == 2
        assert manager.list_runs() == []

    def test_keeps_recent_runs(self, manager):
        manager.get_or_create_run("recent")
        removed = manager.clean_runs("1d")
        assert removed == 0
        assert len(manager.list_runs()) == 1


class TestListAllCards:
    def test_all_cards_across_runs(self, manager):
        _, store_a = manager.get_or_create_run("run-a")
        _, store_b = manager.get_or_create_run("run-b")

        from m4.display.renderer import render

        render("card-a", run_id="run-a", store=store_a)
        render("card-b", run_id="run-b", store=store_b)

        all_cards = manager.list_all_cards()
        assert len(all_cards) == 2

    def test_filter_by_run_id(self, manager):
        _, store_a = manager.get_or_create_run("run-a")
        _, store_b = manager.get_or_create_run("run-b")

        from m4.display.renderer import render

        render("card-a", run_id="run-a", store=store_a)
        render("card-b", run_id="run-b", store=store_b)

        cards_a = manager.list_all_cards(run_id="run-a")
        assert len(cards_a) == 1

    def test_filter_nonexistent_run(self, manager):
        assert manager.list_all_cards(run_id="nonexistent") == []


class TestRequestQueue:
    def test_store_and_list(self, manager):
        manager.store_request({"request_id": "r1", "card_id": "c1", "prompt": "test"})
        requests = manager.list_requests(pending_only=True)
        assert len(requests) == 1
        assert requests[0]["request_id"] == "r1"

    def test_acknowledge(self, manager):
        manager.store_request({"request_id": "r1", "card_id": "c1", "prompt": "test"})
        manager.acknowledge_request("r1")
        assert manager.list_requests(pending_only=True) == []

    def test_multiple_requests(self, manager):
        manager.store_request({"request_id": "r1", "card_id": "c1", "prompt": "first"})
        manager.store_request({"request_id": "r2", "card_id": "c2", "prompt": "second"})
        assert len(manager.list_requests(pending_only=True)) == 2
        manager.acknowledge_request("r1")
        pending = manager.list_requests(pending_only=True)
        assert len(pending) == 1
        assert pending[0]["request_id"] == "r2"


class TestDiscovery:
    def test_discovers_existing_runs(self, display_dir):
        """RunManager discovers runs created by a previous instance."""
        # Create a run with the first manager
        mgr1 = RunManager(display_dir)
        _label, store = mgr1.get_or_create_run("persistent-run")
        dir_name = mgr1._label_to_dir["persistent-run"]

        # Store a card
        from m4.display.renderer import render

        card = render("hello world", run_id="persistent-run", store=store)

        # Create a new manager (simulates server restart)
        mgr2 = RunManager(display_dir)

        # Should discover the existing run
        assert "persistent-run" in mgr2._label_to_dir
        assert mgr2._label_to_dir["persistent-run"] == dir_name

        # Should be able to list cards from the discovered run
        cards = mgr2.list_all_cards(run_id="persistent-run")
        assert len(cards) == 1
        assert cards[0].card_id == card.card_id

        # Card index should be rebuilt
        assert mgr2.get_store_for_card(card.card_id) is not None


class TestEnsureRunLoaded:
    def test_loads_existing_dir(self, manager):
        _, _store = manager.get_or_create_run("load-test")
        dir_name = manager._label_to_dir["load-test"]

        # Remove from in-memory stores to simulate lazy loading
        del manager._stores[dir_name]

        loaded = manager.ensure_run_loaded(dir_name)
        assert loaded is not None

    def test_returns_none_for_missing(self, manager):
        assert manager.ensure_run_loaded("nonexistent-dir") is None


class TestRefresh:
    def test_picks_up_new_runs(self, display_dir):
        """refresh() discovers runs created by another RunManager instance."""
        mgr1 = RunManager(display_dir)
        mgr2 = RunManager(display_dir)

        # mgr1 creates a run — mgr2 doesn't know about it yet
        mgr1.get_or_create_run("new-run")
        assert "new-run" not in mgr2._label_to_dir

        # After refresh, mgr2 should discover it
        mgr2.refresh()
        assert "new-run" in mgr2._label_to_dir
        assert mgr2.get_store_for_card is not None

    def test_skips_already_known(self, manager):
        """refresh() doesn't reload runs already in memory."""
        _, store = manager.get_or_create_run("existing")
        manager.refresh()
        # Same store object — not reloaded
        assert manager._stores[manager._label_to_dir["existing"]] is store

    def test_discovers_cards_in_new_runs(self, display_dir):
        """refresh() indexes cards from newly discovered runs."""
        from m4.display.renderer import render

        mgr1 = RunManager(display_dir)
        _, store = mgr1.get_or_create_run("card-run")
        card = render("hello", run_id="card-run", store=store)

        mgr2 = RunManager(display_dir)
        # Card was indexed at construction via _discover_runs
        assert mgr2.get_store_for_card(card.card_id) is not None

        # Now test refresh path: create another run after mgr2 init
        _, store2 = mgr1.get_or_create_run("card-run-2")
        card2 = render("world", run_id="card-run-2", store=store2)

        assert mgr2.get_store_for_card(card2.card_id) is None
        mgr2.refresh()
        assert mgr2.get_store_for_card(card2.card_id) is not None
