"""Tests for m4.vitrine.renderer.

Tests cover:
- DataFrame -> table CardDescriptor with Parquet artifact on disk
- Plotly Figure -> chart CardDescriptor with JSON artifact
- matplotlib Figure -> image CardDescriptor with SVG artifact
- str -> inline markdown CardDescriptor
- dict -> inline key-value CardDescriptor
- Unknown type -> repr() fallback as markdown
- Renderer calls Redactor (pass-through for now)
- Error when no store provided
- SVG sanitization (script stripping, size limits)
"""

import json

import pandas as pd
import pytest

from m4.vitrine._types import CardType
from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.redaction import Redactor
from m4.vitrine.renderer import (
    _is_matplotlib_figure,
    _is_plotly_figure,
    _sanitize_svg,
    render,
)


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

    def test_study_propagated(self, store, redactor, sample_df):
        card = render(sample_df, study="my-study", store=store, redactor=redactor)
        assert card.study == "my-study"

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


class TestSanitizeSvg:
    def test_strips_script_tags(self):
        svg = b'<svg><script>alert("xss")</script><circle r="10"/></svg>'
        result = _sanitize_svg(svg)
        assert b"<script" not in result
        assert b"alert" not in result
        assert b"<circle" in result

    def test_strips_event_attributes(self):
        svg = b'<svg><rect onload="alert(1)" onclick="evil()" width="10"/></svg>'
        result = _sanitize_svg(svg)
        assert b"onload" not in result
        assert b"onclick" not in result
        assert b"width" in result

    def test_preserves_valid_svg(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40"/></svg>'
        result = _sanitize_svg(svg)
        assert b"<circle" in result
        assert b'cx="50"' in result

    def test_rejects_oversized_svg(self):
        svg = b"<svg>" + b"x" * (2 * 1024 * 1024 + 1) + b"</svg>"
        with pytest.raises(ValueError, match="SVG exceeds size limit"):
            _sanitize_svg(svg)

    def test_size_limit_after_stripping(self):
        # Just under limit after stripping scripts
        inner = b"x" * (2 * 1024 * 1024 - 100)
        svg = b"<svg>" + inner + b"</svg>"
        result = _sanitize_svg(svg)
        assert b"<svg>" in result


class TestRenderPlotly:
    @pytest.fixture
    def plotly_fig(self):
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        fig = go.Figure(data=[go.Bar(x=["A", "B", "C"], y=[1, 2, 3])])
        fig.update_layout(title="Test Chart")
        return fig

    def test_creates_plotly_card(self, store, plotly_fig):
        card = render(plotly_fig, store=store)
        assert card.card_type == CardType.PLOTLY

    def test_has_json_artifact(self, store, plotly_fig):
        card = render(plotly_fig, store=store)
        assert card.artifact_id is not None
        assert card.artifact_type == "json"

    def test_json_artifact_on_disk(self, store, plotly_fig):
        card = render(plotly_fig, store=store)
        json_path = store._artifacts_dir / f"{card.artifact_id}.json"
        assert json_path.exists()
        spec = json.loads(json_path.read_text())
        assert "data" in spec
        assert "layout" in spec

    def test_preview_contains_spec(self, store, plotly_fig):
        card = render(plotly_fig, store=store)
        assert "spec" in card.preview
        assert "data" in card.preview["spec"]

    def test_infers_title_from_layout(self, store, plotly_fig):
        card = render(plotly_fig, store=store)
        assert card.title == "Test Chart"

    def test_custom_title_overrides(self, store, plotly_fig):
        card = render(plotly_fig, title="My Chart", store=store)
        assert card.title == "My Chart"

    def test_default_title_when_no_layout_title(self, store):
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        fig = go.Figure(data=[go.Scatter(x=[1], y=[1])])
        card = render(fig, store=store)
        assert card.title == "Chart"

    def test_stored_in_index(self, store, plotly_fig):
        render(plotly_fig, store=store)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.PLOTLY

    def test_study_propagated(self, store, plotly_fig):
        card = render(plotly_fig, study="analysis-1", store=store)
        assert card.study == "analysis-1"

    def test_provenance_with_source(self, store, plotly_fig):
        card = render(plotly_fig, source="cohort_analysis", store=store)
        assert card.provenance is not None
        assert card.provenance.source == "cohort_analysis"

    def test_plotly_express_customdata_ndarray_serialized(self, store):
        pytest.importorskip("plotly")
        import plotly.express as px

        df = pd.DataFrame(
            {
                "age": [21, 34, 55, 63],
                "sofa": [2.1, 4.2, 7.4, 8.0],
                "cohort": ["control", "sepsis", "sepsis", "control"],
                "mortality_30d": [False, True, False, True],
                "patient_id": [1001, 1002, 1003, 1004],
            }
        )
        fig = px.scatter(
            df,
            x="age",
            y="sofa",
            color="cohort",
            hover_data=["patient_id", "mortality_30d"],
        )

        card = render(fig, store=store)
        assert card.card_type == CardType.PLOTLY
        assert isinstance(card.preview["spec"]["data"][0].get("customdata"), list)


class TestIsPlotlyFigure:
    def test_detects_plotly_figure(self):
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        assert _is_plotly_figure(go.Figure()) is True

    def test_rejects_non_plotly(self):
        assert _is_plotly_figure("not a figure") is False
        assert _is_plotly_figure(42) is False
        assert _is_plotly_figure({"data": []}) is False


class TestRenderMatplotlib:
    @pytest.fixture
    def mpl_fig(self):
        mpl = pytest.importorskip("matplotlib")
        mpl.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        return fig

    def test_creates_image_card(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        assert card.card_type == CardType.IMAGE

    def test_has_svg_artifact(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        assert card.artifact_id is not None
        assert card.artifact_type == "svg"

    def test_svg_artifact_on_disk(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        svg_path = store._artifacts_dir / f"{card.artifact_id}.svg"
        assert svg_path.exists()
        content = svg_path.read_text()
        assert "<svg" in content

    def test_preview_contains_base64(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        assert "data" in card.preview
        assert card.preview["format"] == "svg"
        assert card.preview["size_bytes"] > 0
        # Verify base64 is valid
        import base64

        decoded = base64.b64decode(card.preview["data"])
        assert b"<svg" in decoded

    def test_svg_is_sanitized(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        svg_path = store._artifacts_dir / f"{card.artifact_id}.svg"
        content = svg_path.read_text()
        assert "<script" not in content

    def test_custom_title(self, store, mpl_fig):
        card = render(mpl_fig, title="My Plot", store=store)
        assert card.title == "My Plot"

    def test_default_title(self, store, mpl_fig):
        card = render(mpl_fig, store=store)
        assert card.title == "Figure"

    def test_title_from_suptitle(self, store):
        mpl = pytest.importorskip("matplotlib")
        mpl.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        fig.suptitle("Super Title")
        ax.plot([1, 2], [1, 2])
        card = render(fig, store=store)
        assert card.title == "Super Title"

    def test_stored_in_index(self, store, mpl_fig):
        render(mpl_fig, store=store)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.IMAGE

    def test_study_propagated(self, store, mpl_fig):
        card = render(mpl_fig, study="plot-study", store=store)
        assert card.study == "plot-study"


class TestIsMatplotlibFigure:
    def test_detects_matplotlib_figure(self):
        mpl = pytest.importorskip("matplotlib")
        mpl.use("Agg")
        import matplotlib.pyplot as plt

        fig, _ = plt.subplots()
        assert _is_matplotlib_figure(fig) is True
        plt.close(fig)

    def test_rejects_non_matplotlib(self):
        assert _is_matplotlib_figure("not a figure") is False
        assert _is_matplotlib_figure(42) is False


class TestRenderForm:
    def test_form_renders_as_form_card(self, store):
        from m4.vitrine._types import Dropdown, Form

        form = Form([Dropdown("method", ["logistic", "cox"])])
        card = render(form, store=store)
        assert card.card_type == CardType.FORM

    def test_form_preview_has_fields(self, store):
        from m4.vitrine._types import Dropdown, Form

        form = Form([Dropdown("method", ["logistic", "cox"])])
        card = render(form, store=store)
        assert "fields" in card.preview
        assert len(card.preview["fields"]) == 1
        assert card.preview["fields"][0]["name"] == "method"

    def test_form_default_title(self, store):
        from m4.vitrine._types import Dropdown, Form

        form = Form([Dropdown("method", ["logistic", "cox"])])
        card = render(form, store=store)
        assert card.title == "Form"

    def test_form_custom_title(self, store):
        from m4.vitrine._types import Dropdown, Form

        form = Form([Dropdown("method", ["logistic", "cox"])])
        card = render(form, title="Choose Method", store=store)
        assert card.title == "Choose Method"
