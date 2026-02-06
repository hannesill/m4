"""Tests for m4.display._types.

Tests cover:
- CardType enum values and string serialization
- CardDescriptor creation and defaults
- CardProvenance creation
- DisplayEvent creation
"""

from m4.display._types import CardDescriptor, CardProvenance, CardType, DisplayEvent


class TestCardType:
    def test_enum_values(self):
        assert CardType.TABLE.value == "table"
        assert CardType.MARKDOWN.value == "markdown"
        assert CardType.KEYVALUE.value == "keyvalue"
        assert CardType.SECTION.value == "section"
        assert CardType.PLOTLY.value == "plotly"
        assert CardType.IMAGE.value == "image"

    def test_string_enum(self):
        assert CardType.TABLE == "table"
        assert CardType("table") is CardType.TABLE

    def test_all_types_present(self):
        expected = {"table", "markdown", "keyvalue", "section", "plotly", "image"}
        actual = {ct.value for ct in CardType}
        assert actual == expected


class TestCardProvenance:
    def test_defaults(self):
        prov = CardProvenance()
        assert prov.source is None
        assert prov.query is None
        assert prov.code_hash is None
        assert prov.dataset is None
        assert prov.timestamp is None

    def test_with_values(self):
        prov = CardProvenance(
            source="mimiciv_hosp.patients",
            query="SELECT * FROM ...",
            dataset="mimic-iv",
            timestamp="2025-01-15T10:00:00Z",
        )
        assert prov.source == "mimiciv_hosp.patients"
        assert prov.query == "SELECT * FROM ..."
        assert prov.dataset == "mimic-iv"


class TestCardDescriptor:
    def test_minimal(self):
        card = CardDescriptor(card_id="abc123", card_type=CardType.MARKDOWN)
        assert card.card_id == "abc123"
        assert card.card_type == CardType.MARKDOWN
        assert card.title is None
        assert card.description is None
        assert card.run_id is None
        assert card.pinned is False
        assert card.artifact_id is None
        assert card.artifact_type is None
        assert card.preview == {}
        assert card.provenance is None

    def test_full(self):
        prov = CardProvenance(source="test_table")
        card = CardDescriptor(
            card_id="xyz789",
            card_type=CardType.TABLE,
            title="Test Table",
            description="A test",
            timestamp="2025-01-01T00:00:00Z",
            run_id="run-1",
            pinned=True,
            artifact_id="xyz789",
            artifact_type="parquet",
            preview={"columns": ["a", "b"], "shape": [10, 2]},
            provenance=prov,
        )
        assert card.title == "Test Table"
        assert card.pinned is True
        assert card.artifact_type == "parquet"
        assert card.preview["columns"] == ["a", "b"]
        assert card.provenance.source == "test_table"


class TestDisplayEvent:
    def test_creation(self):
        event = DisplayEvent(
            event_type="row_click",
            card_id="card1",
            payload={"row_index": 42},
        )
        assert event.event_type == "row_click"
        assert event.card_id == "card1"
        assert event.payload["row_index"] == 42

    def test_defaults(self):
        event = DisplayEvent(event_type="test", card_id="c1")
        assert event.payload == {}
