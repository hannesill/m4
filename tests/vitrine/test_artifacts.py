"""Tests for m4.vitrine.artifacts.

Tests cover:
- ArtifactStore creation and directory layout
- store_dataframe -> Parquet on disk
- store_json -> JSON on disk
- store_image -> binary on disk
- read_table_page with offset, limit, sort
- list_cards in insertion order, with study filter
- update_card
- clear with and without keep_pinned
- Serialization/deserialization of CardDescriptor
"""

import json

import pandas as pd
import pytest

from m4.vitrine._types import CardDescriptor, CardProvenance, CardType
from m4.vitrine.artifacts import ArtifactStore


@pytest.fixture
def store(tmp_path):
    """Create a fresh ArtifactStore in a temp directory."""
    session_dir = tmp_path / "test_session"
    return ArtifactStore(session_dir=session_dir, session_id="test-session-123")


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
            "age": [30, 25, 35, 28, 32],
            "score": [88.5, 92.0, 76.3, 95.1, 81.7],
        }
    )


@pytest.fixture
def sample_card():
    return CardDescriptor(
        card_id="card-001",
        card_type=CardType.TABLE,
        title="Test",
        timestamp="2025-01-01T00:00:00Z",
        artifact_id="card-001",
        artifact_type="parquet",
        preview={"columns": ["a"], "shape": [5, 1]},
        provenance=CardProvenance(source="test_table"),
    )


class TestArtifactStoreCreation:
    def test_creates_directories(self, store):
        assert store.session_dir.exists()
        assert (store.session_dir / "artifacts").exists()

    def test_creates_index(self, store):
        assert (store.session_dir / "index.json").exists()
        index = json.loads((store.session_dir / "index.json").read_text())
        assert index == []

    def test_creates_metadata(self, store):
        meta_path = store.session_dir / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["session_id"] == "test-session-123"
        assert "start_time" in meta
        assert meta["study_names"] == []


class TestStoreDataFrame:
    def test_stores_parquet(self, store, sample_df):
        path = store.store_dataframe("df-001", sample_df)
        assert path.exists()
        assert path.suffix == ".parquet"

    def test_parquet_readable(self, store, sample_df):
        store.store_dataframe("df-002", sample_df)
        result = pd.read_parquet(store._artifacts_dir / "df-002.parquet")
        assert len(result) == 5
        assert list(result.columns) == ["name", "age", "score"]


class TestStoreJson:
    def test_stores_json(self, store):
        data = {"key": "value", "nested": {"a": 1}}
        path = store.store_json("json-001", data)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["key"] == "value"
        assert loaded["nested"]["a"] == 1


class TestStoreImage:
    def test_stores_svg(self, store):
        svg_data = b"<svg><circle r='10'/></svg>"
        path = store.store_image("img-001", svg_data, "svg")
        assert path.exists()
        assert path.read_bytes() == svg_data

    def test_stores_png(self, store):
        png_data = b"\x89PNG\r\n\x1a\nfakedata"
        path = store.store_image("img-002", png_data, "png")
        assert path.exists()
        assert path.read_bytes() == png_data


class TestReadTablePage:
    def test_basic_read(self, store, sample_df):
        store.store_dataframe("page-001", sample_df)
        result = store.read_table_page("page-001", offset=0, limit=3)
        assert result["total_rows"] == 5
        assert len(result["rows"]) == 3
        assert result["columns"] == ["name", "age", "score"]
        assert result["offset"] == 0
        assert result["limit"] == 3

    def test_offset(self, store, sample_df):
        store.store_dataframe("page-002", sample_df)
        result = store.read_table_page("page-002", offset=3, limit=10)
        assert len(result["rows"]) == 2  # Only 2 rows left after offset 3
        assert result["total_rows"] == 5

    def test_sort_ascending(self, store, sample_df):
        store.store_dataframe("page-003", sample_df)
        result = store.read_table_page(
            "page-003", offset=0, limit=5, sort_col="age", sort_asc=True
        )
        ages = [row[1] for row in result["rows"]]
        assert ages == sorted(ages)

    def test_sort_descending(self, store, sample_df):
        store.store_dataframe("page-004", sample_df)
        result = store.read_table_page(
            "page-004", offset=0, limit=5, sort_col="age", sort_asc=False
        )
        ages = [row[1] for row in result["rows"]]
        assert ages == sorted(ages, reverse=True)

    def test_invalid_sort_col_ignored(self, store, sample_df):
        store.store_dataframe("page-005", sample_df)
        # Should not crash — invalid column is silently ignored
        result = store.read_table_page(
            "page-005", offset=0, limit=5, sort_col="nonexistent"
        )
        assert len(result["rows"]) == 5

    def test_missing_artifact_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.read_table_page("nonexistent", offset=0, limit=10)


class TestListCards:
    def test_empty_store(self, store):
        assert store.list_cards() == []

    def test_insertion_order(self, store):
        for i in range(3):
            card = CardDescriptor(
                card_id=f"card-{i}",
                card_type=CardType.MARKDOWN,
                title=f"Card {i}",
                timestamp=f"2025-01-0{i + 1}T00:00:00Z",
                preview={"text": f"Content {i}"},
            )
            store.store_card(card)

        cards = store.list_cards()
        assert len(cards) == 3
        assert [c.card_id for c in cards] == ["card-0", "card-1", "card-2"]

    def test_filter_by_study(self, store):
        store.store_card(
            CardDescriptor(
                card_id="a",
                card_type=CardType.MARKDOWN,
                study="study-1",
                preview={"text": "a"},
            )
        )
        store.store_card(
            CardDescriptor(
                card_id="b",
                card_type=CardType.MARKDOWN,
                study="study-2",
                preview={"text": "b"},
            )
        )
        store.store_card(
            CardDescriptor(
                card_id="c",
                card_type=CardType.MARKDOWN,
                study="study-1",
                preview={"text": "c"},
            )
        )

        study1 = store.list_cards(study="study-1")
        assert [c.card_id for c in study1] == ["a", "c"]

        study2 = store.list_cards(study="study-2")
        assert [c.card_id for c in study2] == ["b"]

    def test_tracks_study_names_in_meta(self, store):
        store.store_card(
            CardDescriptor(
                card_id="x",
                card_type=CardType.MARKDOWN,
                study="my-study",
                preview={},
            )
        )
        meta = json.loads(store._meta_path.read_text())
        assert "my-study" in meta["study_names"]


class TestUpdateCard:
    def test_update_title(self, store, sample_card):
        store.store_card(sample_card)
        updated = store.update_card("card-001", title="New Title")
        assert updated is not None
        assert updated.title == "New Title"

        # Persisted
        cards = store.list_cards()
        assert cards[0].title == "New Title"

    def test_update_pinned(self, store, sample_card):
        store.store_card(sample_card)
        updated = store.update_card("card-001", pinned=True)
        assert updated.pinned is True

    def test_update_nonexistent(self, store):
        result = store.update_card("nonexistent", title="X")
        assert result is None


class TestClear:
    def test_clear_all(self, store, sample_df):
        store.store_dataframe("c1", sample_df)
        store.store_card(
            CardDescriptor(
                card_id="c1",
                card_type=CardType.TABLE,
                artifact_id="c1",
                artifact_type="parquet",
                preview={},
            )
        )
        store.store_card(
            CardDescriptor(
                card_id="c2",
                card_type=CardType.MARKDOWN,
                preview={"text": "hi"},
            )
        )

        store.clear(keep_pinned=False)
        assert store.list_cards() == []
        assert not (store._artifacts_dir / "c1.parquet").exists()

    def test_clear_keeps_pinned(self, store, sample_df):
        store.store_dataframe("p1", sample_df)
        store.store_card(
            CardDescriptor(
                card_id="p1",
                card_type=CardType.TABLE,
                pinned=True,
                artifact_id="p1",
                artifact_type="parquet",
                preview={},
            )
        )
        store.store_card(
            CardDescriptor(
                card_id="u1",
                card_type=CardType.MARKDOWN,
                pinned=False,
                preview={"text": "gone"},
            )
        )

        store.clear(keep_pinned=True)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_id == "p1"
        # Pinned artifact preserved
        assert (store._artifacts_dir / "p1.parquet").exists()

    def test_clear_empty_store(self, store):
        store.clear()  # Should not raise
        assert store.list_cards() == []


class TestGetArtifact:
    def test_get_json_artifact(self, store):
        store.store_json("j1", {"key": "val"})
        result = store.get_artifact("j1")
        assert isinstance(result, dict)
        assert result["key"] == "val"

    def test_get_parquet_artifact(self, store, sample_df):
        store.store_dataframe("d1", sample_df)
        result = store.get_artifact("d1")
        assert isinstance(result, bytes)

    def test_get_image_artifact(self, store):
        store.store_image("i1", b"<svg/>", "svg")
        result = store.get_artifact("i1")
        assert result == b"<svg/>"

    def test_missing_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.get_artifact("nonexistent")


class TestDeleteSession:
    def test_removes_directory(self, store, sample_df):
        store.store_dataframe("x", sample_df)
        store.store_card(
            CardDescriptor(card_id="x", card_type=CardType.TABLE, preview={})
        )
        assert store.session_dir.exists()

        store.delete_session()
        assert not store.session_dir.exists()


class TestSerialization:
    def test_roundtrip_with_provenance(self, store):
        card = CardDescriptor(
            card_id="rt-001",
            card_type=CardType.TABLE,
            title="Roundtrip",
            description="Test roundtrip",
            timestamp="2025-06-01T00:00:00Z",
            study="study-rt",
            pinned=True,
            artifact_id="rt-001",
            artifact_type="parquet",
            preview={"columns": ["x"], "shape": [1, 1]},
            provenance=CardProvenance(
                source="test_source",
                query="SELECT 1",
                dataset="mimic-iv",
                timestamp="2025-06-01T00:00:00Z",
            ),
        )
        store.store_card(card)
        cards = store.list_cards()
        assert len(cards) == 1

        restored = cards[0]
        assert restored.card_id == "rt-001"
        assert restored.card_type == CardType.TABLE
        assert restored.title == "Roundtrip"
        assert restored.pinned is True
        assert restored.provenance is not None
        assert restored.provenance.source == "test_source"
        assert restored.provenance.query == "SELECT 1"
        assert restored.provenance.dataset == "mimic-iv"

    def test_roundtrip_with_annotations(self, store):
        annotations = [
            {
                "id": "a1",
                "text": "Mortality seems high",
                "timestamp": "2026-02-10T14:32:00Z",
            },
            {
                "id": "a2",
                "text": "Double-check exclusions",
                "timestamp": "2026-02-10T15:00:00Z",
            },
        ]
        card = CardDescriptor(
            card_id="rt-ann",
            card_type=CardType.MARKDOWN,
            preview={"text": "analysis"},
            annotations=annotations,
        )
        store.store_card(card)
        restored = store.list_cards()[0]
        assert len(restored.annotations) == 2
        assert restored.annotations[0]["id"] == "a1"
        assert restored.annotations[0]["text"] == "Mortality seems high"
        assert restored.annotations[1]["id"] == "a2"

    def test_roundtrip_empty_annotations(self, store):
        card = CardDescriptor(
            card_id="rt-ann-empty",
            card_type=CardType.MARKDOWN,
            preview={"text": "no notes"},
        )
        store.store_card(card)
        restored = store.list_cards()[0]
        assert restored.annotations == []

    def test_roundtrip_with_dismissed(self, store):
        card = CardDescriptor(
            card_id="rt-dis",
            card_type=CardType.MARKDOWN,
            preview={"text": "dismissed card"},
            dismissed=True,
        )
        store.store_card(card)
        restored = store.list_cards()[0]
        assert restored.dismissed is True

    def test_dismissed_backward_compat(self, store):
        """Cards serialized before the dismissed field should default to False."""
        raw = [
            {
                "card_id": "old-card",
                "card_type": "markdown",
                "preview": {"text": "old"},
                "provenance": None,
            }
        ]
        store._write_index(raw)
        restored = store.list_cards()[0]
        assert restored.dismissed is False

    def test_roundtrip_without_provenance(self, store):
        card = CardDescriptor(
            card_id="rt-002",
            card_type=CardType.MARKDOWN,
            preview={"text": "hello"},
        )
        store.store_card(card)
        restored = store.list_cards()[0]
        assert restored.provenance is None
        assert restored.preview["text"] == "hello"
