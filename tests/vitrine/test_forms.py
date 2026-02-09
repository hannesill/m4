"""Tests for form field primitives, form rendering, blocking flow, and validation.

Tests cover:
- All 10 field types: construct -> to_dict() -> assert keys/values
- Form rendering -> CardType.FORM, preview structure
- Form blocking flow (response_requested + form_values)
- Controls parameter on show() -> hybrid data+controls cards
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
    Checkbox,
    DateRange,
    DisplayResponse,
    Dropdown,
    Form,
    MultiSelect,
    NumberInput,
    RadioGroup,
    RangeSlider,
    Slider,
    TextInput,
    Toggle,
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
# TestFormFieldSerialization -- all 10 field types
# ================================================================


class TestFormFieldSerialization:
    def test_dropdown(self):
        f = Dropdown(name="gender", options=["M", "F"], default="M", label="Gender")
        d = f.to_dict()
        assert d["type"] == "dropdown"
        assert d["name"] == "gender"
        assert d["options"] == ["M", "F"]
        assert d["default"] == "M"
        assert d["label"] == "Gender"

    def test_dropdown_no_default(self):
        f = Dropdown(name="x", options=["a", "b"])
        d = f.to_dict()
        assert "default" not in d

    def test_multiselect(self):
        f = MultiSelect(
            name="comorbidities",
            options=["HTN", "DM", "CKD"],
            default=["HTN"],
            label="Comorbidities",
        )
        d = f.to_dict()
        assert d["type"] == "multiselect"
        assert d["name"] == "comorbidities"
        assert d["options"] == ["HTN", "DM", "CKD"]
        assert d["default"] == ["HTN"]

    def test_multiselect_empty_default(self):
        f = MultiSelect(name="x", options=["a"])
        d = f.to_dict()
        assert "default" not in d

    def test_slider(self):
        f = Slider(name="age", range=(18, 100), default=65, step=1, label="Age")
        d = f.to_dict()
        assert d["type"] == "slider"
        assert d["min"] == 18
        assert d["max"] == 100
        assert d["default"] == 65
        assert d["step"] == 1

    def test_range_slider(self):
        f = RangeSlider(
            name="age_range", range=(0, 120), default=(18, 65), label="Age Range"
        )
        d = f.to_dict()
        assert d["type"] == "range_slider"
        assert d["min"] == 0
        assert d["max"] == 120
        assert d["default"] == [18, 65]

    def test_checkbox(self):
        f = Checkbox(
            name="exclude_readmits", label="Exclude readmissions", default=True
        )
        d = f.to_dict()
        assert d["type"] == "checkbox"
        assert d["default"] is True
        assert d["label"] == "Exclude readmissions"

    def test_toggle(self):
        f = Toggle(name="active", label="Active only", default=False)
        d = f.to_dict()
        assert d["type"] == "toggle"
        assert d["default"] is False

    def test_radio_group(self):
        f = RadioGroup(
            name="severity", options=["mild", "moderate", "severe"], default="moderate"
        )
        d = f.to_dict()
        assert d["type"] == "radio"
        assert d["options"] == ["mild", "moderate", "severe"]
        assert d["default"] == "moderate"

    def test_text_input(self):
        f = TextInput(
            name="notes", label="Notes", default="", placeholder="Enter notes..."
        )
        d = f.to_dict()
        assert d["type"] == "text"
        assert d["placeholder"] == "Enter notes..."

    def test_date_range(self):
        f = DateRange(
            name="period", label="Study Period", default=("2020-01-01", "2020-12-31")
        )
        d = f.to_dict()
        assert d["type"] == "date_range"
        assert d["default"] == ["2020-01-01", "2020-12-31"]

    def test_number_input(self):
        f = NumberInput(
            name="threshold", label="Threshold", default=0.5, min=0, max=1, step=0.1
        )
        d = f.to_dict()
        assert d["type"] == "number"
        assert d["default"] == 0.5
        assert d["min"] == 0
        assert d["max"] == 1
        assert d["step"] == 0.1


# ================================================================
# TestFormRendering
# ================================================================


class TestFormRendering:
    def test_renders_form_card(self, store):
        form = Form(
            fields=[
                Slider(name="age", range=(0, 100)),
                Dropdown(name="sex", options=["M", "F"]),
            ]
        )
        card = render(form, title="Cohort Filter", store=store)
        assert card.card_type == CardType.FORM
        assert card.title == "Cohort Filter"

    def test_preview_has_fields(self, store):
        form = Form(
            fields=[
                Checkbox(name="active", default=True),
                TextInput(name="query"),
            ]
        )
        card = render(form, store=store)
        assert "fields" in card.preview
        assert len(card.preview["fields"]) == 2
        assert card.preview["fields"][0]["type"] == "checkbox"

    def test_no_artifact(self, store):
        form = Form(fields=[Toggle(name="x")])
        card = render(form, store=store)
        assert card.artifact_id is None
        assert card.artifact_type is None

    def test_stored_in_index(self, store):
        form = Form(fields=[Toggle(name="x")])
        render(form, store=store)
        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0].card_type == CardType.FORM


# ================================================================
# TestFormBlockingFlow
# ================================================================


class TestFormBlockingFlow:
    def test_form_wait_returns_values(self, store, mock_server):
        mock_server._mock_response = {
            "action": "confirm",
            "card_id": "test",
            "values": {"age": 65, "sex": "M"},
        }
        form = Form(
            fields=[
                Slider(name="age", range=(0, 100), default=50),
                Dropdown(name="sex", options=["M", "F"]),
            ]
        )
        result = display.show(form, wait=True, title="Filter")
        assert isinstance(result, DisplayResponse)
        assert result.action == "confirm"
        assert result.values == {"age": 65, "sex": "M"}

    def test_form_response_requested_set(self, store, mock_server):
        mock_server._mock_response = {"action": "confirm", "card_id": "x"}
        form = Form(fields=[Toggle(name="active")])
        display.show(form, wait=True)
        cards = store.list_cards()
        assert cards[0].response_requested is True


# ================================================================
# TestControlsParameter
# ================================================================


class TestControlsParameter:
    def test_controls_attached_to_table(self, store, mock_server):
        df = pd.DataFrame({"x": [1, 2, 3]})
        controls = [Slider(name="threshold", range=(0, 10), default=5)]
        display.show(df, title="Table", controls=controls)
        cards = store.list_cards()
        assert "controls" in cards[0].preview
        assert len(cards[0].preview["controls"]) == 1
        assert cards[0].preview["controls"][0]["type"] == "slider"

    def test_controls_multiple_fields(self, store, mock_server):
        df = pd.DataFrame({"val": [1]})
        controls = [
            Slider(name="min_age", range=(0, 120)),
            Dropdown(name="unit", options=["ICU", "Ward"]),
        ]
        display.show(df, controls=controls)
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
                Dropdown(name="sex", options=["M", "F"], default="M"),
                Slider(name="age", range=(0, 100), default=50),
            ]
        )
        card = render(form, title="Form Card", store=store, study="form-export")
        mgr.register_card(card.card_id, dir_name)

        out = tmp_path / "export.html"
        export_html(mgr, out, study="form-export")
        html = out.read_text()
        assert "Form Card" in html
        assert "sex" in html

    def test_json_export_contains_form(self, tmp_path):
        import zipfile

        from m4.vitrine.export import export_json

        mgr = StudyManager(tmp_path / "display2")
        _, store = mgr.get_or_create_study("form-json")
        dir_name = mgr._label_to_dir["form-json"]

        form = Form(fields=[Checkbox(name="active", default=True)])
        card = render(form, title="Check", store=store, study="form-json")
        mgr.register_card(card.card_id, dir_name)

        out = tmp_path / "export.zip"
        export_json(mgr, out, study="form-json")
        with zipfile.ZipFile(out) as zf:
            cards = json.loads(zf.read("cards.json"))
            assert len(cards) == 1
            assert cards[0]["card_type"] == "form"


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
    # Slider
    def test_slider_invalid_range(self):
        with pytest.raises(ValueError, match="range min"):
            Slider(name="x", range=(100, 0))

    def test_slider_default_out_of_range(self):
        with pytest.raises(ValueError, match="not in range"):
            Slider(name="x", range=(0, 10), default=20)

    def test_slider_valid(self):
        s = Slider(name="x", range=(0, 10), default=5)
        assert s.default == 5

    # RangeSlider
    def test_range_slider_invalid_range(self):
        with pytest.raises(ValueError, match="range min"):
            RangeSlider(name="x", range=(100, 0))

    def test_range_slider_default_reversed(self):
        with pytest.raises(ValueError, match="default min"):
            RangeSlider(name="x", range=(0, 100), default=(80, 20))

    def test_range_slider_default_out_of_range(self):
        with pytest.raises(ValueError, match="not within range"):
            RangeSlider(name="x", range=(10, 50), default=(5, 30))

    def test_range_slider_valid(self):
        rs = RangeSlider(name="x", range=(0, 100), default=(20, 80))
        assert rs.default == (20, 80)

    # Dropdown
    def test_dropdown_empty_options(self):
        with pytest.raises(ValueError, match="non-empty"):
            Dropdown(name="x", options=[])

    def test_dropdown_invalid_default(self):
        with pytest.raises(ValueError, match="not in options"):
            Dropdown(name="x", options=["a", "b"], default="c")

    def test_dropdown_valid_default(self):
        d = Dropdown(name="x", options=["a", "b"], default="a")
        assert d.default == "a"

    # MultiSelect
    def test_multiselect_empty_options(self):
        with pytest.raises(ValueError, match="non-empty"):
            MultiSelect(name="x", options=[])

    def test_multiselect_invalid_default(self):
        with pytest.raises(ValueError, match="not in options"):
            MultiSelect(name="x", options=["a", "b"], default=["c"])

    def test_multiselect_valid(self):
        ms = MultiSelect(name="x", options=["a", "b"], default=["a"])
        assert ms.default == ["a"]

    # RadioGroup
    def test_radio_empty_options(self):
        with pytest.raises(ValueError, match="non-empty"):
            RadioGroup(name="x", options=[])

    def test_radio_invalid_default(self):
        with pytest.raises(ValueError, match="not in options"):
            RadioGroup(name="x", options=["a", "b"], default="c")

    # NumberInput
    def test_number_min_gt_max(self):
        with pytest.raises(ValueError, match=r"min.*max"):
            NumberInput(name="x", min=10, max=5)

    def test_number_default_below_min(self):
        with pytest.raises(ValueError, match="less than min"):
            NumberInput(name="x", min=0, max=10, default=-1)

    def test_number_default_above_max(self):
        with pytest.raises(ValueError, match="greater than max"):
            NumberInput(name="x", min=0, max=10, default=20)

    def test_number_valid(self):
        n = NumberInput(name="x", min=0, max=10, default=5)
        assert n.default == 5

    # DateRange
    def test_date_range_reversed(self):
        with pytest.raises(ValueError, match=r"start.*end"):
            DateRange(name="x", default=("2025-12-31", "2025-01-01"))

    def test_date_range_valid(self):
        dr = DateRange(name="x", default=("2025-01-01", "2025-12-31"))
        assert dr.default == ("2025-01-01", "2025-12-31")

    # Form name uniqueness
    def test_form_duplicate_names(self):
        with pytest.raises(ValueError, match="Duplicate"):
            Form(
                fields=[
                    Slider(name="age", range=(0, 100)),
                    Slider(name="age", range=(0, 50)),
                ]
            )

    def test_form_unique_names(self):
        f = Form(
            fields=[
                Slider(name="age", range=(0, 100)),
                Slider(name="weight", range=(0, 200)),
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
