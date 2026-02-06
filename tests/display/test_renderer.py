"""Tests for m4.display.renderer.

Tests cover:
- DataFrame → table CardDescriptor with Parquet artifact on disk
- str → inline markdown CardDescriptor
- dict → inline key-value CardDescriptor
- Unknown type → repr() fallback as markdown
- Renderer calls Redactor (pass-through for now)
- Error when no store provided
"""

import pandas as pd
import pytest

from m4.display._types import CardType
from m4.display.artifacts import ArtifactStore
from m4.display.redaction import Redactor
from m4.display.renderer import render


@pytest.fixture
def store(tmp_path):
    session_dir = tmp_path / "render_session"
    return ArtifactStore(session_dir=session_dir, session_id="render-test")


@pytest.fixture
def redactor():
    return Redactor(enabled=False)


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "patient_id": [1, 2, 3],
            "age": [65, 72, 58],
            "diagnosis": ["sepsis", "pneumonia", "AKI"],
        }
    )


class TestRenderDataFrame:
    def test_creates_table_card(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert card.card_type == CardType.TABLE
        assert card.artifact_id is not None
        assert card.artifact_type == "parquet"

    def test_default_title(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert card.title == "Table"

    def test_custom_title(self, store, redactor, sample_df):
        card = render(sample_df, title="Demographics", store=store, redactor=redactor)
        assert card.title == "Demographics"

    def test_preview_contains_columns(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert card.preview["columns"] == ["patient_id", "age", "diagnosis"]

    def test_preview_contains_shape(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert card.preview["shape"] == [3, 3]

    def test_preview_contains_dtypes(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert "patient_id" in card.preview["dtypes"]
        assert "age" in card.preview["dtypes"]

    def test_preview_contains_rows(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        assert len(card.preview["preview_rows"]) == 3  # Small df, all rows in preview

    def test_preview_capped_at_20_rows(self, store, redactor):
        big_df = pd.DataFrame({"x": range(100)})
        card = render(big_df, store=store, redactor=redactor)
        assert len(card.preview["preview_rows"]) == 20

    def test_parquet_artifact_on_disk(self, store, redactor, sample_df):
        card = render(sample_df, store=store, redactor=redactor)
        parquet_path = store._artifacts_dir / f"{card.artifact_id}.parquet"
        assert parquet_path.exists()

    def test_stored_in_index(self, store, redactor, sample_df):
        render(sample_df, store=store, redactor=redactor)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.TABLE

    def test_provenance_with_source(self, store, redactor, sample_df):
        card = render(
            sample_df,
            source="mimiciv_hosp.patients",
            store=store,
            redactor=redactor,
        )
        assert card.provenance is not None
        assert card.provenance.source == "mimiciv_hosp.patients"

    def test_run_id_propagated(self, store, redactor, sample_df):
        card = render(sample_df, run_id="my-run", store=store, redactor=redactor)
        assert card.run_id == "my-run"

    def test_paging_works_on_stored_artifact(self, store, redactor):
        df = pd.DataFrame({"val": range(100)})
        card = render(df, store=store, redactor=redactor)
        page = store.read_table_page(card.artifact_id, offset=10, limit=5)
        assert len(page["rows"]) == 5
        assert page["total_rows"] == 100
        assert page["rows"][0][0] == 10  # val starts at offset


class TestRenderMarkdown:
    def test_creates_markdown_card(self, store):
        card = render("## Hello World", store=store)
        assert card.card_type == CardType.MARKDOWN

    def test_text_in_preview(self, store):
        card = render("Some **bold** text", store=store)
        assert card.preview["text"] == "Some **bold** text"

    def test_no_artifact(self, store):
        card = render("text", store=store)
        assert card.artifact_id is None
        assert card.artifact_type is None

    def test_custom_title(self, store):
        card = render("text", title="Finding", store=store)
        assert card.title == "Finding"

    def test_no_default_title(self, store):
        card = render("text", store=store)
        assert card.title is None

    def test_stored_in_index(self, store):
        render("text", store=store)
        assert len(store.list_cards()) == 1


class TestRenderDict:
    def test_creates_keyvalue_card(self, store):
        card = render({"key": "value"}, store=store)
        assert card.card_type == CardType.KEYVALUE

    def test_items_in_preview(self, store):
        card = render({"name": "Alice", "age": 30}, store=store)
        assert card.preview["items"]["name"] == "Alice"
        assert card.preview["items"]["age"] == "30"  # Converted to string

    def test_default_title(self, store):
        card = render({"k": "v"}, store=store)
        assert card.title == "Key-Value"

    def test_custom_title(self, store):
        card = render({"k": "v"}, title="Stats", store=store)
        assert card.title == "Stats"

    def test_no_artifact(self, store):
        card = render({"k": "v"}, store=store)
        assert card.artifact_id is None

    def test_stored_in_index(self, store):
        render({"k": "v"}, store=store)
        assert len(store.list_cards()) == 1


class TestRenderFallback:
    def test_unknown_type_renders_as_markdown(self, store):
        card = render(42, store=store)
        assert card.card_type == CardType.MARKDOWN

    def test_repr_in_code_block(self, store):
        card = render([1, 2, 3], store=store)
        assert "```" in card.preview["text"]
        assert "[1, 2, 3]" in card.preview["text"]

    def test_custom_object(self, store):
        class Foo:
            def __repr__(self):
                return "Foo(bar=42)"

        card = render(Foo(), store=store)
        assert "Foo(bar=42)" in card.preview["text"]


class TestRenderErrors:
    def test_no_store_raises(self):
        with pytest.raises(ValueError, match="ArtifactStore is required"):
            render("text")


class TestRedactorIntegration:
    def test_redactor_called_on_dataframe(self, store):
        """Verify the renderer passes through the redactor (currently a no-op)."""
        df = pd.DataFrame({"name": ["Alice"], "age": [30]})
        redactor = Redactor(enabled=True)
        card = render(df, store=store, redactor=redactor)
        # Currently pass-through, but the card should still be valid
        assert card.card_type == CardType.TABLE
        assert card.preview["columns"] == ["name", "age"]

    def test_default_redactor_created(self, store):
        """When no redactor is passed, a default one is created."""
        df = pd.DataFrame({"x": [1]})
        card = render(df, store=store)
        assert card.card_type == CardType.TABLE
