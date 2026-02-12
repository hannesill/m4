"""Tests for m4.vitrine._types.

Tests cover:
- CardType enum values and string serialization
- CardDescriptor creation and defaults
- CardProvenance creation
- DisplayEvent creation and repr
- DisplayResponse repr and artifact_path
"""

import pytest

from m4.vitrine._types import (
    CardDescriptor,
    CardProvenance,
    CardType,
    DisplayEvent,
    DisplayHandle,
    DisplayResponse,
    Form,
    Question,
)


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
        expected = {
            "table",
            "markdown",
            "keyvalue",
            "section",
            "plotly",
            "image",
            "decision",
            "agent",
        }
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
        assert card.study is None
        assert card.pinned is False
        assert card.dismissed is False
        assert card.artifact_id is None
        assert card.artifact_type is None
        assert card.preview == {}
        assert card.provenance is None
        assert card.actions is None

    def test_annotations_default_empty(self):
        card = CardDescriptor(card_id="ann0", card_type=CardType.MARKDOWN)
        assert card.annotations == []

    def test_annotations_populated(self):
        annotations = [
            {"id": "a1", "text": "Looks off", "timestamp": "2026-02-10T14:00:00Z"},
            {"id": "a2", "text": "Confirmed", "timestamp": "2026-02-10T15:00:00Z"},
        ]
        card = CardDescriptor(
            card_id="ann1",
            card_type=CardType.TABLE,
            annotations=annotations,
        )
        assert len(card.annotations) == 2
        assert card.annotations[0]["text"] == "Looks off"
        assert card.annotations[1]["id"] == "a2"

    def test_dismissed(self):
        card = CardDescriptor(
            card_id="dis1", card_type=CardType.MARKDOWN, dismissed=True
        )
        assert card.dismissed is True

    def test_with_actions(self):
        card = CardDescriptor(
            card_id="act1",
            card_type=CardType.MARKDOWN,
            actions=["Approve", "Reject", "Revise"],
        )
        assert card.actions == ["Approve", "Reject", "Revise"]

    def test_full(self):
        prov = CardProvenance(source="test_table")
        card = CardDescriptor(
            card_id="xyz789",
            card_type=CardType.TABLE,
            title="Test Table",
            description="A test",
            timestamp="2025-01-01T00:00:00Z",
            study="study-1",
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

    def test_repr_row_click(self):
        event = DisplayEvent(
            event_type="row_click",
            card_id="abcdef1234567890",
            payload={"row": {"id": 1, "name": "Alice", "age": 30}},
        )
        r = repr(event)
        assert "row_click" in r
        assert "abcdef12" in r
        assert "id=1" in r
        assert "name='Alice'" in r

    def test_repr_row_click_truncates_keys(self):
        event = DisplayEvent(
            event_type="row_click",
            card_id="card1234",
            payload={"row": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}},
        )
        r = repr(event)
        assert "\u2026" in r

    def test_repr_point_select(self):
        event = DisplayEvent(
            event_type="point_select",
            card_id="card1234",
            payload={"points": [{"x": 1}, {"x": 2}]},
        )
        r = repr(event)
        assert "2 points" in r

    def test_repr_generic_event(self):
        event = DisplayEvent(event_type="custom", card_id="card1234")
        r = repr(event)
        assert "custom" in r
        assert "card1234" in r


class TestDisplayResponse:
    def test_repr_basic(self):
        resp = DisplayResponse(action="confirm", card_id="c1", message="Looks good")
        r = repr(resp)
        assert "confirm" in r
        assert "Looks good" in r

    def test_repr_with_summary(self):
        resp = DisplayResponse(
            action="confirm",
            card_id="c1",
            summary="5 rows \u00d7 3 cols (a, b, c) from 'Cohort'",
        )
        r = repr(resp)
        assert "Selection:" in r
        assert "5 rows" in r

    def test_repr_no_message(self):
        resp = DisplayResponse(action="timeout", card_id="c1")
        r = repr(resp)
        assert "timeout" in r
        assert "message" not in r

    def test_repr_artifact_not_on_disk(self):
        resp = DisplayResponse(action="confirm", card_id="c1", artifact_id="resp-abc")
        r = repr(resp)
        assert "resp-abc" in r
        assert "not on disk" in r

    def test_artifact_path_with_store(self, tmp_path):
        from m4.vitrine.artifacts import ArtifactStore

        store = ArtifactStore(session_dir=tmp_path, session_id="s1")
        import pandas as pd

        df = pd.DataFrame({"x": [1, 2]})
        store.store_dataframe("resp-test", df)

        resp = DisplayResponse(
            action="confirm",
            card_id="c1",
            artifact_id="resp-test",
            _store=store,
        )
        assert resp.artifact_path is not None
        assert "resp-test.parquet" in resp.artifact_path
        r = repr(resp)
        assert "resp-test.parquet" in r
        assert "not on disk" not in r

    def test_artifact_path_none_without_store(self):
        resp = DisplayResponse(action="confirm", card_id="c1")
        assert resp.artifact_path is None


class TestDisplayHandle:
    def test_string_compat(self):
        handle = DisplayHandle("c1")
        assert isinstance(handle, str)
        assert str(handle) == "c1"
        assert handle.card_id == "c1"
        assert handle.url is None

    def test_url_attached(self):
        handle = DisplayHandle("c2", "http://127.0.0.1:7741/#study=r1")
        assert handle.card_id == "c2"
        assert handle.url.endswith("#study=r1")


class TestQuestion:
    def test_to_dict_tuple_options(self):
        q = Question(
            name="score",
            question="Which severity score?",
            options=[("SOFA", "6 organ systems"), ("APACHE", "More variables")],
            header="Score",
        )
        d = q.to_dict()
        assert d["type"] == "question"
        assert d["name"] == "score"
        assert d["question"] == "Which severity score?"
        assert d["header"] == "Score"
        assert d["multiple"] is False
        assert d["allow_other"] is True
        assert len(d["options"]) == 2
        assert d["options"][0] == {"label": "SOFA", "description": "6 organ systems"}
        assert d["options"][1] == {"label": "APACHE", "description": "More variables"}
        assert "default" not in d

    def test_plain_string_options(self):
        q = Question(
            name="method",
            question="Which method?",
            options=["Logistic", "Cox", "Random Forest"],
        )
        d = q.to_dict()
        assert d["options"][0] == {"label": "Logistic", "description": ""}
        assert d["options"][2] == {"label": "Random Forest", "description": ""}

    def test_mixed_options(self):
        q = Question(
            name="x",
            question="Pick one",
            options=[("A", "desc A"), "B"],
        )
        d = q.to_dict()
        assert d["options"][0] == {"label": "A", "description": "desc A"}
        assert d["options"][1] == {"label": "B", "description": ""}

    def test_default_validation_invalid(self):
        with pytest.raises(ValueError, match="not in option labels"):
            Question(
                name="x",
                question="Pick",
                options=[("A", "a"), ("B", "b")],
                default="C",
            )

    def test_empty_options_validation(self):
        with pytest.raises(ValueError, match="non-empty"):
            Question(name="x", question="Pick", options=[])

    def test_multiple_default_list(self):
        q = Question(
            name="x",
            question="Pick some",
            options=["A", "B", "C"],
            multiple=True,
            default=["A", "C"],
        )
        d = q.to_dict()
        assert d["multiple"] is True
        assert d["default"] == ["A", "C"]

    def test_multiple_invalid_default(self):
        with pytest.raises(ValueError, match="not in option labels"):
            Question(
                name="x",
                question="Pick",
                options=["A", "B"],
                multiple=True,
                default=["A", "Z"],
            )

    def test_allow_other_false(self):
        q = Question(
            name="x",
            question="Pick",
            options=["A"],
            allow_other=False,
        )
        d = q.to_dict()
        assert d["allow_other"] is False

    def test_question_in_form(self):
        form = Form(
            fields=[
                Question(name="score", question="Which?", options=["SOFA", "APACHE"]),
                Question(name="method", question="How?", options=["logistic", "cox"]),
            ]
        )
        assert len(form.fields) == 2
        d = form.to_dict()
        assert d["fields"][0]["type"] == "question"
        assert d["fields"][1]["type"] == "question"

    def test_question_duplicate_name_in_form(self):
        with pytest.raises(ValueError, match="Duplicate"):
            Form(
                fields=[
                    Question(name="x", question="A?", options=["1"]),
                    Question(name="x", question="B?", options=["2"]),
                ]
            )
