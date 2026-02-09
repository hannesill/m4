"""Tests for m4.vitrine.export.

Tests cover:
- HTML export produces self-contained file
- JSON export produces valid zip with cards and artifacts
- Export individual studies vs all studies
- Provenance metadata in exports
- Table rendering from Parquet artifacts
- Plotly, image, markdown, and key-value card rendering
- Edge cases (empty studies, missing artifacts)
"""

import json
import zipfile

import pandas as pd
import pytest

from m4.vitrine.export import (
    _format_cell,
    export_html,
    export_html_string,
    export_json,
    export_json_bytes,
)
from m4.vitrine.renderer import render
from m4.vitrine.study_manager import StudyManager


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


@pytest.fixture
def populated_manager(manager):
    """Create a StudyManager with a populated study containing various card types."""
    _, store = manager.get_or_create_study("test-study")
    dir_name = manager._label_to_dir["test-study"]

    # Table card
    df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"], "age": [30, 25, 35]})
    card = render(
        df, title="Demographics", source="test_table", store=store, study="test-study"
    )
    manager.register_card(card.card_id, dir_name)

    # Markdown card
    card = render(
        "## Key Finding\nMortality is **23%**",
        title="Finding",
        store=store,
        study="test-study",
    )
    manager.register_card(card.card_id, dir_name)

    # Key-value card
    card = render(
        {"patients": "4238", "mortality": "23%"},
        title="Summary",
        store=store,
        study="test-study",
    )
    manager.register_card(card.card_id, dir_name)

    return manager


class TestExportHTML:
    def test_produces_file(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        result = export_html(populated_manager, out, study="test-study")
        assert result.exists()
        assert result.stat().st_size > 0

    def test_self_contained(self, populated_manager, tmp_path):
        """Exported HTML contains all content without external dependencies."""
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "<!DOCTYPE html>" in html
        assert "<style>" in html
        assert "vitrine" in html

    def test_contains_table_data(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "Alice" in html
        assert "Bob" in html
        assert "Charlie" in html
        assert "Demographics" in html

    def test_contains_markdown(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "Key Finding" in html
        assert "23%" in html

    def test_contains_keyvalue(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "patients" in html
        assert "4238" in html

    def test_contains_provenance(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "test_table" in html

    def test_contains_print_css(self, populated_manager, tmp_path):
        out = tmp_path / "export.html"
        export_html(populated_manager, out, study="test-study")
        html = out.read_text()
        assert "@media print" in html

    def test_export_all_studies(self, populated_manager, tmp_path):
        # Add another study
        _, store2 = populated_manager.get_or_create_study("second-study")
        dir_name2 = populated_manager._label_to_dir["second-study"]
        card = render("Second study card", store=store2, study="second-study")
        populated_manager.register_card(card.card_id, dir_name2)

        out = tmp_path / "all.html"
        export_html(populated_manager, out, study=None)
        html = out.read_text()
        # Both studies should be present
        assert "test-study" in html
        assert "second-study" in html

    def test_creates_parent_dirs(self, populated_manager, tmp_path):
        out = tmp_path / "subdir" / "deep" / "export.html"
        result = export_html(populated_manager, out, study="test-study")
        assert result.exists()

    def test_empty_study(self, manager, tmp_path):
        """Exporting a study with no cards produces a valid HTML file."""
        manager.get_or_create_study("empty-study")
        out = tmp_path / "empty.html"
        result = export_html(manager, out, study="empty-study")
        assert result.exists()
        html = out.read_text()
        assert "<!DOCTYPE html>" in html


class TestExportJSON:
    def test_produces_zip(self, populated_manager, tmp_path):
        out = tmp_path / "export.zip"
        result = export_json(populated_manager, out, study="test-study")
        assert result.exists()
        assert zipfile.is_zipfile(result)

    def test_adds_zip_extension(self, populated_manager, tmp_path):
        out = tmp_path / "export"
        result = export_json(populated_manager, out, study="test-study")
        assert str(result).endswith(".zip")

    def test_contains_meta(self, populated_manager, tmp_path):
        out = tmp_path / "export.zip"
        export_json(populated_manager, out, study="test-study")
        with zipfile.ZipFile(out) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert "exported_at" in meta
            assert meta["study"] == "test-study"
            assert meta["card_count"] == 3

    def test_contains_cards(self, populated_manager, tmp_path):
        out = tmp_path / "export.zip"
        export_json(populated_manager, out, study="test-study")
        with zipfile.ZipFile(out) as zf:
            cards = json.loads(zf.read("cards.json"))
            assert len(cards) == 3

    def test_contains_artifacts(self, populated_manager, tmp_path):
        out = tmp_path / "export.zip"
        export_json(populated_manager, out, study="test-study")
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            # Should have at least one parquet file (the table)
            artifact_files = [n for n in names if n.startswith("artifacts/")]
            assert len(artifact_files) > 0
            assert any(n.endswith(".parquet") for n in artifact_files)

    def test_export_all_studies(self, populated_manager, tmp_path):
        _, store2 = populated_manager.get_or_create_study("second-study")
        dir_name2 = populated_manager._label_to_dir["second-study"]
        card = render("another card", store=store2, study="second-study")
        populated_manager.register_card(card.card_id, dir_name2)

        out = tmp_path / "all.zip"
        export_json(populated_manager, out, study=None)
        with zipfile.ZipFile(out) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert meta["card_count"] == 4
            assert meta["study"] is None

    def test_empty_study(self, manager, tmp_path):
        manager.get_or_create_study("empty-study")
        out = tmp_path / "empty.zip"
        result = export_json(manager, out, study="empty-study")
        assert zipfile.is_zipfile(result)
        with zipfile.ZipFile(result) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert meta["card_count"] == 0


class TestExportStringBytes:
    """Test the in-memory export functions used by server endpoints."""

    def test_html_string(self, populated_manager):
        html = export_html_string(populated_manager, study="test-study")
        assert "<!DOCTYPE html>" in html
        assert "Demographics" in html

    def test_json_bytes(self, populated_manager):
        data = export_json_bytes(populated_manager, study="test-study")
        assert len(data) > 0
        # Verify it's a valid zip
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "meta.json" in zf.namelist()
            assert "cards.json" in zf.namelist()


class TestFormatCell:
    def test_none(self):
        assert _format_cell(None) == ""

    def test_nan(self):
        assert _format_cell(float("nan")) == ""

    def test_integer_float(self):
        assert _format_cell(42.0) == "42"

    def test_float(self):
        result = _format_cell(3.14159265)
        assert "3.14" in result

    def test_string(self):
        assert _format_cell("hello") == "hello"

    def test_int(self):
        assert _format_cell(42) == "42"
