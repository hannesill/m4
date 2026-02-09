"""Tests for m4.vitrine.study_manager.

Tests cover:
- Directory creation and study naming format
- get_or_create_study() creates new / returns existing
- Label reuse across calls
- get_store_for_card() lookups
- list_studies() metadata and sort order
- delete_study() removes dir and updates registry
- clean_studies() age-based removal
- Startup discovery from existing study directories
"""

import json
import time

import pytest

from m4.vitrine.study_manager import (
    StudyManager,
    _make_study_dir_name,
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
    """Create a StudyManager instance."""
    return StudyManager(display_dir)


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


class TestMakeStudyDirName:
    def test_format(self):
        name = _make_study_dir_name("test-study")
        # Should match YYYY-MM-DD_HHMMSS_label pattern
        parts = name.split("_", 2)
        assert len(parts) == 3
        assert len(parts[0]) == 10  # YYYY-MM-DD
        assert len(parts[1]) == 6  # HHMMSS
        assert parts[2] == "test-study"


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


class TestGetOrCreateStudy:
    def test_creates_new_study(self, manager):
        label, store = manager.get_or_create_study("test-study")
        assert label == "test-study"
        assert store is not None
        assert (manager._studies_dir / manager._label_to_dir["test-study"]).exists()

    def test_returns_existing_study(self, manager):
        label1, store1 = manager.get_or_create_study("my-study")
        label2, store2 = manager.get_or_create_study("my-study")
        assert label1 == label2
        assert store1 is store2

    def test_auto_label(self, manager):
        label, store = manager.get_or_create_study(None)
        assert label.startswith("auto-")
        assert store is not None

    def test_different_labels_different_studies(self, manager):
        _, store1 = manager.get_or_create_study("study-a")
        _, store2 = manager.get_or_create_study("study-b")
        assert store1 is not store2

    def test_creates_meta_json(self, manager):
        label, _ = manager.get_or_create_study("meta-test")
        dir_name = manager._label_to_dir[label]
        meta_path = manager._studies_dir / dir_name / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["label"] == "meta-test"
        assert "start_time" in meta

    def test_updates_registry(self, manager):
        manager.get_or_create_study("reg-test")
        registry = manager._read_registry()
        assert len(registry) == 1
        assert registry[0]["label"] == "reg-test"


class TestStoreForCard:
    def test_lookup_registered_card(self, manager):
        _, store = manager.get_or_create_study("lookup-test")
        dir_name = manager._label_to_dir["lookup-test"]
        manager.register_card("card-123", dir_name)
        assert manager.get_store_for_card("card-123") is store

    def test_lookup_missing_card(self, manager):
        assert manager.get_store_for_card("nonexistent") is None


class TestListStudies:
    def test_empty(self, manager):
        assert manager.list_studies() == []

    def test_lists_created_studies(self, manager):
        manager.get_or_create_study("study-a")
        manager.get_or_create_study("study-b")
        studies = manager.list_studies()
        assert len(studies) == 2
        labels = {r["label"] for r in studies}
        assert labels == {"study-a", "study-b"}

    def test_sorted_newest_first(self, manager):
        manager.get_or_create_study("first")
        time.sleep(0.01)
        manager.get_or_create_study("second")
        studies = manager.list_studies()
        assert studies[0]["label"] == "second"
        assert studies[1]["label"] == "first"

    def test_includes_card_count(self, manager):
        _, store = manager.get_or_create_study("count-test")
        from m4.vitrine.renderer import render

        render("hello", store=store)
        render("world", store=store)
        studies = manager.list_studies()
        assert studies[0]["card_count"] == 2


class TestDeleteStudy:
    def test_deletes_existing(self, manager):
        manager.get_or_create_study("to-delete")
        dir_name = manager._label_to_dir["to-delete"]
        study_dir = manager._studies_dir / dir_name
        assert study_dir.exists()

        result = manager.delete_study("to-delete")
        assert result is True
        assert not study_dir.exists()
        assert "to-delete" not in manager._label_to_dir
        assert manager._read_registry() == []

    def test_delete_nonexistent(self, manager):
        assert manager.delete_study("nonexistent") is False

    def test_removes_card_index_entries(self, manager):
        _, _store = manager.get_or_create_study("idx-test")
        dir_name = manager._label_to_dir["idx-test"]
        manager.register_card("c1", dir_name)
        manager.register_card("c2", dir_name)
        assert manager.get_store_for_card("c1") is not None

        manager.delete_study("idx-test")
        assert manager.get_store_for_card("c1") is None
        assert manager.get_store_for_card("c2") is None


class TestCleanStudies:
    def test_removes_all_with_zero(self, manager):
        manager.get_or_create_study("old-a")
        manager.get_or_create_study("old-b")
        removed = manager.clean_studies("0d")
        assert removed == 2
        assert manager.list_studies() == []

    def test_keeps_recent_studies(self, manager):
        manager.get_or_create_study("recent")
        removed = manager.clean_studies("1d")
        assert removed == 0
        assert len(manager.list_studies()) == 1


class TestListAllCards:
    def test_all_cards_across_studies(self, manager):
        _, store_a = manager.get_or_create_study("study-a")
        _, store_b = manager.get_or_create_study("study-b")

        from m4.vitrine.renderer import render

        render("card-a", study="study-a", store=store_a)
        render("card-b", study="study-b", store=store_b)

        all_cards = manager.list_all_cards()
        assert len(all_cards) == 2

    def test_filter_by_study(self, manager):
        _, store_a = manager.get_or_create_study("study-a")
        _, store_b = manager.get_or_create_study("study-b")

        from m4.vitrine.renderer import render

        render("card-a", study="study-a", store=store_a)
        render("card-b", study="study-b", store=store_b)

        cards_a = manager.list_all_cards(study="study-a")
        assert len(cards_a) == 1

    def test_filter_nonexistent_study(self, manager):
        assert manager.list_all_cards(study="nonexistent") == []


class TestBuildContext:
    def test_empty_study(self, manager):
        manager.get_or_create_study("empty")
        ctx = manager.build_context("empty")
        assert ctx["study"] == "empty"
        assert ctx["card_count"] == 0
        assert ctx["cards"] == []
        assert ctx["decisions"] == []
        assert ctx["pending_responses"] == []
        assert ctx["decisions_made"] == []
        assert ctx["current_selections"] == {}

    def test_with_cards(self, manager):
        from m4.vitrine.renderer import render

        _, store = manager.get_or_create_study("ctx-test")
        render("hello", title="Card 1", study="ctx-test", store=store)
        render("world", title="Card 2", study="ctx-test", store=store)

        ctx = manager.build_context("ctx-test")
        assert ctx["card_count"] == 2
        assert len(ctx["cards"]) == 2
        assert ctx["cards"][0]["title"] == "Card 1"
        assert ctx["cards"][1]["title"] == "Card 2"
        assert ctx["cards"][0]["card_type"] == "markdown"

    def test_with_decision_cards(self, manager):
        from m4.vitrine.renderer import render

        _, store = manager.get_or_create_study("decision-test")
        card = render("check this", title="Review", study="decision-test", store=store)
        store.update_card(card.card_id, response_requested=True, prompt="Approve?")

        ctx = manager.build_context("decision-test")
        assert len(ctx["decisions"]) == 1
        assert ctx["decisions"][0]["title"] == "Review"
        assert ctx["decisions"][0]["prompt"] == "Approve?"
        assert len(ctx["pending_responses"]) == 1

    def test_with_resolved_response(self, manager):
        from m4.vitrine.renderer import render

        _, store = manager.get_or_create_study("resolved-test")
        card = render("check this", title="Review", study="resolved-test", store=store)
        store.update_card(
            card.card_id,
            response_action="Approve",
            response_message="Looks good",
            response_values={"threshold": 0.2},
            response_summary="3 rows from 'Review'",
            response_artifact_id="resp-1",
            response_timestamp="2026-02-09T10:00:00+00:00",
        )

        ctx = manager.build_context("resolved-test")
        assert len(ctx["decisions_made"]) == 1
        assert ctx["decisions_made"][0]["action"] == "Approve"
        assert ctx["decisions_made"][0]["message"] == "Looks good"
        assert ctx["decisions_made"][0]["values"] == {"threshold": 0.2}

    def test_nonexistent_study(self, manager):
        ctx = manager.build_context("nonexistent")
        assert ctx["study"] == "nonexistent"
        assert ctx["card_count"] == 0


class TestDiscovery:
    def test_discovers_existing_studies(self, display_dir):
        """StudyManager discovers studies created by a previous instance."""
        # Create a study with the first manager
        mgr1 = StudyManager(display_dir)
        _label, store = mgr1.get_or_create_study("persistent-study")
        dir_name = mgr1._label_to_dir["persistent-study"]

        # Store a card
        from m4.vitrine.renderer import render

        card = render("hello world", study="persistent-study", store=store)

        # Create a new manager (simulates server restart)
        mgr2 = StudyManager(display_dir)

        # Should discover the existing study
        assert "persistent-study" in mgr2._label_to_dir
        assert mgr2._label_to_dir["persistent-study"] == dir_name

        # Should be able to list cards from the discovered study
        cards = mgr2.list_all_cards(study="persistent-study")
        assert len(cards) == 1
        assert cards[0].card_id == card.card_id

        # Card index should be rebuilt
        assert mgr2.get_store_for_card(card.card_id) is not None


class TestEnsureStudyLoaded:
    def test_loads_existing_dir(self, manager):
        _, _store = manager.get_or_create_study("load-test")
        dir_name = manager._label_to_dir["load-test"]

        # Remove from in-memory stores to simulate lazy loading
        del manager._stores[dir_name]

        loaded = manager.ensure_study_loaded(dir_name)
        assert loaded is not None

    def test_returns_none_for_missing(self, manager):
        assert manager.ensure_study_loaded("nonexistent-dir") is None


class TestRefresh:
    def test_picks_up_new_studies(self, display_dir):
        """refresh() discovers studies created by another StudyManager instance."""
        mgr1 = StudyManager(display_dir)
        mgr2 = StudyManager(display_dir)

        # mgr1 creates a study — mgr2 doesn't know about it yet
        mgr1.get_or_create_study("new-study")
        assert "new-study" not in mgr2._label_to_dir

        # After refresh, mgr2 should discover it
        mgr2.refresh()
        assert "new-study" in mgr2._label_to_dir
        assert mgr2.get_store_for_card is not None

    def test_skips_already_known(self, manager):
        """refresh() doesn't reload studies already in memory."""
        _, store = manager.get_or_create_study("existing")
        manager.refresh()
        # Same store object — not reloaded
        assert manager._stores[manager._label_to_dir["existing"]] is store

    def test_discovers_cards_in_new_studies(self, display_dir):
        """refresh() indexes cards from newly discovered studies."""
        from m4.vitrine.renderer import render

        mgr1 = StudyManager(display_dir)
        _, store = mgr1.get_or_create_study("card-study")
        card = render("hello", study="card-study", store=store)

        mgr2 = StudyManager(display_dir)
        # Card was indexed at construction via _discover_runs
        assert mgr2.get_store_for_card(card.card_id) is not None

        # Now test refresh path: create another study after mgr2 init
        _, store2 = mgr1.get_or_create_study("card-study-2")
        card2 = render("world", study="card-study-2", store=store2)

        assert mgr2.get_store_for_card(card2.card_id) is None
        mgr2.refresh()
        assert mgr2.get_store_for_card(card2.card_id) is not None
