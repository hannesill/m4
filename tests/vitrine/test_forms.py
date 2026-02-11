"""Tests for Question field, form rendering, blocking flow, and validation.

Tests cover:
- Question field: construct -> to_dict() -> assert keys/values
- Form rendering -> CardType.DECISION with preview.fields
- Form blocking flow (auto wait=True + form_values)
- Controls parameter on show() -> hybrid data+controls cards (auto wait=True)
- Form export in HTML and JSON
- Form field validation (__post_init__ checks)
- Form field name uniqueness
"""

import json

import pandas as pd
import pytest

import m4.vitrine as display
from m4.vitrine._types import (
    CardType,
    DisplayResponse,
    Form,
    Question,
)
from m4.vitrine.artifacts import ArtifactStore
from m4.vitrine.renderer import render
from m4.vitrine.study_manager import StudyManager

# ================================================================
# Fixtures
# ================================================================


@pytest.fixture
def store(tmp_path):
    session_dir = tmp_path / "form_session"
    return ArtifactStore(session_dir=session_dir, session_id="form-test")


@pytest.fixture
def study_manager(tmp_path):
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    return StudyManager(display_dir)


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
def mock_server(store):
    class MockServer:
        is_running = True

        def __init__(self):
            self.pushed_cards = []
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
            pass

        def wait_for_response_sync(self, card_id, timeout):
            return self._mock_response

        def register_event_callback(self, callback):
            pass

    mock = MockServer()
    display._server = mock
    display._store = store
    display._session_id = "form-test"
    return mock


# ================================================================
# TestFormRendering
# ================================================================


class TestFormRendering:
    def test_renders_form_card(self, store):
        form = Form(
            fields=[
                Question(
                    name="score",
                    question="Which score?",
                    options=["SOFA", "APACHE"],
                ),
                Question(
                    name="method",
                    question="Which method?",
                    options=["Logistic", "Cox"],
                ),
            ]
        )
        card = render(form, title="Cohort Filter", store=store)
        assert card.card_type == CardType.DECISION
        assert card.title == "Cohort Filter"

    def test_preview_has_fields(self, store):
        form = Form(
            fields=[
                Question(
                    name="q1",
                    question="Pick one",
                    options=["A", "B"],
                ),
                Question(
                    name="q2",
                    question="Pick another",
                    options=["X", "Y"],
                ),
            ]
        )
        card = render(form, store=store)
        assert "fields" in card.preview
        assert len(card.preview["fields"]) == 2
        assert card.preview["fields"][0]["type"] == "question"

    def test_no_artifact(self, store):
        form = Form(
            fields=[
                Question(name="q", question="Yes?", options=["Yes", "No"]),
            ]
        )
        card = render(form, store=store)
        assert card.artifact_id is None
        assert card.artifact_type is None

    def test_stored_in_index(self, store):
        form = Form(
            fields=[
                Question(name="q", question="Yes?", options=["Yes", "No"]),
            ]
        )
        render(form, store=store)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.DECISION


# ================================================================
# TestFormBlockingFlow
# ================================================================


class TestFormBlockingFlow:
    def test_form_wait_returns_values(self, store, mock_server):
        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "values": {"score": "SOFA", "method": "Logistic"},
        }
        form = Form(
            fields=[
                Question(
                    name="score",
                    question="Which score?",
                    options=[("SOFA", "6 organ systems"), ("APACHE", "More variables")],
                ),
                Question(
                    name="method",
                    question="Which method?",
                    options=["Logistic", "Cox"],
                ),
            ]
        )
        result = display.show(form, wait=True, title="Filter")
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"
        assert result.values == {"score": "SOFA", "method": "Logistic"}

    def test_form_response_requested_set(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        form = Form(
            fields=[
                Question(name="q", question="Active?", options=["Yes", "No"]),
            ]
        )
        display.show(form, wait=True)
        cards = store.list_cards()
        assert cards[0].response_requested is True


# ================================================================
# TestControlsParameter
# ================================================================


class TestControlsParameter:
    def test_controls_attached_to_table(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        df = pd.DataFrame({"x": [1, 2, 3]})
        controls = [
            Question(
                name="threshold",
                question="Which threshold?",
                options=["Low", "Medium", "High"],
            ),
        ]
        result = display.show(df, title="Table", controls=controls)
        assert isinstance(result, DisplayResponse)
        cards = store.list_cards()
        assert "controls" in cards[0].preview
        assert len(cards[0].preview["controls"]) == 1
        assert cards[0].preview["controls"][0]["type"] == "question"

    def test_controls_multiple_fields(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        df = pd.DataFrame({"val": [1]})
        controls = [
            Question(
                name="age_group",
                question="Age group?",
                options=["Young", "Middle", "Old"],
            ),
            Question(
                name="unit",
                question="Which unit?",
                options=["ICU", "Ward"],
            ),
        ]
        result = display.show(df, controls=controls)
        assert isinstance(result, DisplayResponse)
        cards = store.list_cards()
        assert len(cards[0].preview["controls"]) == 2


# ================================================================
# TestFormExport
# ================================================================


class TestFormExport:
    def test_html_export_contains_form(self, tmp_path):
        from m4.vitrine.export import export_html

        mgr = StudyManager(tmp_path / "display")
        _, store = mgr.get_or_create_study("form-export")
        dir_name = mgr._label_to_dir["form-export"]

        form = Form(
            fields=[
                Question(
                    name="score",
                    question="Which severity score?",
                    options=[("SOFA", "Standard"), ("APACHE", "Advanced")],
                ),
            ]
        )
        card = render(form, title="Form Card", store=store, study="form-export")
        mgr.register_card(card.card_id, dir_name)

        out = tmp_path / "export.html"
        export_html(mgr, out, study="form-export")
        html = out.read_text()
        assert "Form Card" in html
        assert "score" in html

    def test_json_export_contains_form(self, tmp_path):
        import zipfile

        from m4.vitrine.export import export_json

        mgr = StudyManager(tmp_path / "display2")
        _, store = mgr.get_or_create_study("form-json")
        dir_name = mgr._label_to_dir["form-json"]

        form = Form(
            fields=[
                Question(
                    name="active",
                    question="Include active only?",
                    options=["Yes", "No"],
                ),
            ]
        )
        card = render(form, title="Check", store=store, study="form-json")
        mgr.register_card(card.card_id, dir_name)

        out = tmp_path / "export.zip"
        export_json(mgr, out, study="form-json")
        with zipfile.ZipFile(out) as zf:
            cards = json.loads(zf.read("cards.json"))
            assert len(cards) == 1
            assert cards[0]["card_type"] == "decision"


# ================================================================
# TestFormWebSocket
# ================================================================


class TestFormWebSocket:
    def test_ws_response_with_form_values(self, tmp_path):
        """WS vitrine.event with form_values payload stores values."""
        from starlette.testclient import TestClient

        from m4.vitrine.server import DisplayServer

        store = ArtifactStore(
            session_dir=tmp_path / "ws_session",
            session_id="ws-form-test",
        )
        srv = DisplayServer(
            store=store,
            port=7797,
            host="127.0.0.1",
            session_id="ws-form-test",
        )
        app = srv._app

        # Store a card for the response to reference
        render("text", title="Card", store=store)
        card = store.list_cards()[0]

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            # Drain replay
            ws.receive_json()
            ws.send_json(
                {
                    "type": "vitrine.event",
                    "event_type": "response",
                    "card_id": card.card_id,
                    "payload": {
                        "action": "confirm",
                        "form_values": {"age": 65, "sex": "M"},
                    },
                }
            )
            import time

            time.sleep(0.2)

        # Verify the response was stored with form_values
        updated = store.list_cards()[0]
        assert updated.response_values == {"age": 65, "sex": "M"}
        assert updated.response_action == "confirm"


# ================================================================
# TestFormFieldValidation
# ================================================================


class TestFormFieldValidation:
    # Question
    def test_question_empty_options(self):
        with pytest.raises(ValueError, match="non-empty"):
            Question(name="q", question="Pick one", options=[])

    def test_question_invalid_default(self):
        with pytest.raises(ValueError, match="not in option labels"):
            Question(name="q", question="Pick one", options=["A", "B"], default="C")

    def test_question_valid_default(self):
        q = Question(name="q", question="Pick one", options=["A", "B"], default="A")
        assert q.default == "A"

    def test_question_multiple_invalid_default(self):
        with pytest.raises(ValueError, match="not in option labels"):
            Question(
                name="q",
                question="Pick",
                options=["A", "B"],
                multiple=True,
                default=["C"],
            )

    # Form name uniqueness
    def test_form_duplicate_names(self):
        with pytest.raises(ValueError, match="Duplicate"):
            Form(
                fields=[
                    Question(name="q", question="First?", options=["A", "B"]),
                    Question(name="q", question="Second?", options=["X", "Y"]),
                ]
            )

    def test_form_unique_names(self):
        f = Form(
            fields=[
                Question(name="q1", question="First?", options=["A", "B"]),
                Question(name="q2", question="Second?", options=["X", "Y"]),
            ]
        )
        assert len(f.fields) == 2


# ================================================================
# TestDisplayResponseConstants
# ================================================================


class TestDisplayResponseConstants:
    def test_confirm_constant(self):
        assert DisplayResponse.CONFIRM == "confirm"

    def test_skip_constant(self):
        assert DisplayResponse.SKIP == "skip"

    def test_timeout_constant(self):
        assert DisplayResponse.TIMEOUT == "timeout"

    def test_error_constant(self):
        assert DisplayResponse.ERROR == "error"


# ================================================================
# TestDisplayHandleStudy
# ================================================================


class TestDisplayHandleStudy:
    def test_study_attached(self, store, mock_server):
        handle = display.show("hello", study="my-study")
        assert handle.study == "my-study"

    def test_study_none_when_no_study(self, store, mock_server):
        handle = display.show("hello")
        # Without study_manager, study is None
        assert handle.study is None


# ================================================================
# TestQuestionIntegration
# ================================================================


class TestQuestionIntegration:
    def test_question_form_returns_values(self, store, mock_server):
        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "values": {"score": "SOFA", "method": "Logistic"},
        }
        form = Form(
            fields=[
                Question(
                    name="score",
                    question="Which severity score?",
                    options=[
                        ("SOFA", "6 organ systems"),
                        ("APACHE", "More variables"),
                    ],
                    header="Score",
                ),
                Question(
                    name="method",
                    question="Which method?",
                    options=["Logistic", "Cox"],
                    allow_other=False,
                ),
            ]
        )
        result = display.show(form, title="Study Decisions", wait=True)
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"
        assert result.values == {"score": "SOFA", "method": "Logistic"}

    def test_question_renders_as_markdown_card(self, store):
        form = Form(
            fields=[
                Question(
                    name="q1",
                    question="Pick one",
                    options=[("A", "Desc A"), ("B", "Desc B")],
                ),
            ]
        )
        card = render(form, title="Interview", store=store)
        assert card.card_type == CardType.DECISION
        assert "fields" in card.preview
        assert card.preview["fields"][0]["type"] == "question"
        assert len(card.preview["fields"][0]["options"]) == 2

    def test_question_preview_fields(self, store):
        form = Form(
            fields=[
                Question(
                    name="score",
                    question="Which score?",
                    options=[("SOFA", "Standard"), ("APACHE", "Advanced")],
                    header="Score",
                    multiple=False,
                    allow_other=True,
                ),
            ]
        )
        card = render(form, store=store)
        field = card.preview["fields"][0]
        assert field["question"] == "Which score?"
        assert field["header"] == "Score"
        assert field["multiple"] is False
        assert field["allow_other"] is True
        assert field["options"][0]["label"] == "SOFA"
        assert field["options"][0]["description"] == "Standard"
