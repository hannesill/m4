"""Tests for m4.vitrine.dispatch — agent dispatch system.

Tests cover:
- DispatchInfo dataclass defaults and field behavior
- _parse_stream_event() for all event types
- build_prompt() with valid/invalid tasks
- _build_agent_preview() preview dict construction
- create_agent_card() card creation and persistence
- _update_agent_card() preview merging
- cancel_agent() cancellation flow
- get_agent_status() status reporting
- reconcile_orphaned_agents() orphan cleanup
- cleanup_dispatches() server shutdown cleanup
- Sandbox creation and cleanup helpers
- _is_pid_alive() PID checks
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from m4.vitrine._types import CardDescriptor, CardType
from m4.vitrine.dispatch import (
    DispatchInfo,
    _build_agent_preview,
    _cleanup_sandbox,
    _create_sandbox,
    _is_pid_alive,
    _parse_stream_event,
    build_prompt,
    cancel_agent,
    cleanup_dispatches,
    create_agent_card,
    get_agent_status,
    reconcile_orphaned_agents,
)
from m4.vitrine.study_manager import StudyManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def study_mgr(tmp_path):
    """Create a StudyManager for testing."""
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    return StudyManager(display_dir)


@pytest.fixture
def mock_server(study_mgr):
    """A minimal mock DisplayServer with study_manager and _dispatches."""
    server = MagicMock()
    server.study_manager = study_mgr
    server._dispatches = {}
    server._broadcast = AsyncMock()
    return server


@pytest.fixture
def mock_server_no_mgr():
    """A mock server with no study manager."""
    server = MagicMock()
    server.study_manager = None
    server._dispatches = {}
    server._broadcast = AsyncMock()
    return server


# ---------------------------------------------------------------------------
# DispatchInfo
# ---------------------------------------------------------------------------


class TestDispatchInfo:
    def test_defaults(self):
        info = DispatchInfo(task="reproduce", study="test-study")
        assert info.task == "reproduce"
        assert info.study == "test-study"
        assert info.card_id == ""
        assert info.model == "sonnet"
        assert info.budget is None
        assert info.status == "pending"
        assert info.process is None
        assert info.monitor_task is None
        assert info.pid is None
        assert info.error is None
        assert info.accumulated_output == ""
        assert info.extra == {}

    def test_custom_values(self):
        info = DispatchInfo(
            task="report",
            study="my-study",
            card_id="abc123",
            model="opus",
            budget=50.0,
            status="running",
        )
        assert info.model == "opus"
        assert info.budget == 50.0
        assert info.status == "running"

    def test_extra_dict_independence(self):
        """Each DispatchInfo gets its own extra dict."""
        a = DispatchInfo(task="reproduce", study="s1")
        b = DispatchInfo(task="reproduce", study="s2")
        a.extra["sandbox"] = "/tmp/a"
        assert "sandbox" not in b.extra


# ---------------------------------------------------------------------------
# _parse_stream_event
# ---------------------------------------------------------------------------


class TestParseStreamEvent:
    def test_invalid_json_returns_ignore(self):
        kind, text, usage = _parse_stream_event("not json at all")
        assert kind == "ignore"
        assert text == ""
        assert usage is None

    def test_empty_json_object_returns_ignore(self):
        kind, text, usage = _parse_stream_event("{}")
        assert kind == "ignore"

    def test_unknown_event_type_returns_ignore(self):
        event = json.dumps({"type": "system", "message": "starting"})
        kind, text, usage = _parse_stream_event(event)
        assert kind == "ignore"

    def test_assistant_text_block(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hello world"}],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "text"
        assert text == "Hello world"

    def test_assistant_multiple_text_blocks(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Part 1. "},
                        {"type": "text", "text": "Part 2."},
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "text"
        assert text == "Part 1. Part 2."

    def test_assistant_tool_use_read(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/foo/bar/protocol.md"},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "protocol.md" in text

    def test_assistant_tool_use_glob(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Glob",
                            "input": {"pattern": "**/*.py"},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "**/*.py" in text

    def test_assistant_tool_use_grep(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Grep",
                            "input": {"pattern": "def main"},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "def main" in text

    def test_assistant_tool_use_bash(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "python scripts/01_cohort.py"},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "python scripts/01_cohort.py" in text

    def test_assistant_tool_use_bash_long_command_truncated(self):
        long_cmd = "x" * 200
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": long_cmd},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "..." in text
        # The displayed command should be truncated to 80 chars + "..."
        assert len(text) < len(long_cmd) + 50

    def test_assistant_tool_use_other(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": "/tmp/out.txt"},
                        }
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "Write" in text

    def test_assistant_mixed_text_and_tool_use(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me check the file."},
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/foo/bar.py"},
                        },
                    ],
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "tool_use"
        assert "Let me check the file." in text
        assert "bar.py" in text

    def test_assistant_with_usage(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi"}],
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 200,
                        "cache_read_input_tokens": 500,
                        "cache_creation_input_tokens": 100,
                    },
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "text"
        assert usage is not None
        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 200
        assert usage["cache_read"] == 500
        assert usage["cache_creation"] == 100

    def test_result_event(self):
        event = json.dumps(
            {
                "type": "result",
                "result": "Analysis complete.",
                "total_cost_usd": 0.05,
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "result"
        assert text == "Analysis complete."
        assert usage is not None
        assert usage["cost_usd"] == 0.05

    def test_result_event_with_model_usage(self):
        event = json.dumps(
            {
                "type": "result",
                "result": "Done",
                "modelUsage": {
                    "claude-sonnet-4-5-20250929": {
                        "inputTokens": 50000,
                        "outputTokens": 3000,
                        "cacheReadInputTokens": 10000,
                        "cacheCreationInputTokens": 2000,
                        "contextWindow": 200000,
                        "costUSD": 0.12,
                    }
                },
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "result"
        assert text == "Done"
        assert usage is not None
        assert usage["input_tokens"] == 50000
        assert usage["output_tokens"] == 3000
        assert usage["cache_read"] == 10000
        assert usage["context_window"] == 200000
        assert usage["cost_usd"] == 0.12

    def test_result_event_no_usage(self):
        event = json.dumps({"type": "result", "result": "OK"})
        kind, text, usage = _parse_stream_event(event)
        assert kind == "result"
        assert text == "OK"
        assert usage is None

    def test_assistant_empty_content(self):
        event = json.dumps(
            {
                "type": "assistant",
                "message": {"content": []},
            }
        )
        kind, text, usage = _parse_stream_event(event)
        assert kind == "text"
        assert text == ""


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_unknown_task_raises(self, study_mgr):
        with pytest.raises(ValueError, match="Unknown dispatch task"):
            build_prompt("nonexistent", "test-study", study_mgr)

    def test_valid_task_includes_skill_content(self, study_mgr):
        # Create a study with a card so there's context
        _, store = study_mgr.get_or_create_study("test-study")
        prompt = build_prompt("reproduce", "test-study", study_mgr)
        assert "Study:" in prompt
        assert "test-study" in prompt
        assert "Output directory:" in prompt
        assert "scripts/" in prompt

    def test_valid_task_report(self, study_mgr):
        _, store = study_mgr.get_or_create_study("my-study")
        prompt = build_prompt("report", "my-study", study_mgr)
        assert "my-study" in prompt

    def test_sandbox_note_included(self, study_mgr, tmp_path):
        work_dir = tmp_path / "sandbox"
        work_dir.mkdir()
        prompt = build_prompt("reproduce", "test-study", study_mgr, work_dir=work_dir)
        assert "Sandbox" in prompt
        assert str(work_dir) in prompt

    def test_additional_prompt_included(self, study_mgr):
        prompt = build_prompt(
            "reproduce",
            "test-study",
            study_mgr,
            additional_prompt="Focus on the mortality analysis",
        )
        assert "Additional Instructions" in prompt
        assert "Focus on the mortality analysis" in prompt

    def test_additional_prompt_blank_not_included(self, study_mgr):
        prompt = build_prompt(
            "reproduce", "test-study", study_mgr, additional_prompt="   "
        )
        assert "Additional Instructions" not in prompt

    def test_missing_skill_file_raises(self, study_mgr, monkeypatch):
        """If the skill file is missing on disk, build_prompt raises."""
        monkeypatch.setattr(
            "m4.vitrine.dispatch._SKILLS_DIR",
            Path("/nonexistent/skills"),
        )
        with pytest.raises(ValueError, match="Skill file not found"):
            build_prompt("reproduce", "test-study", study_mgr)

    def test_output_dir_none_when_no_registration(self, study_mgr):
        prompt = build_prompt("reproduce", "test-study", study_mgr)
        assert "(none)" in prompt


# ---------------------------------------------------------------------------
# _build_agent_preview
# ---------------------------------------------------------------------------


class TestBuildAgentPreview:
    def test_default_preview(self):
        preview = _build_agent_preview("reproduce", "pending")
        assert preview["task"] == "reproduce"
        assert preview["status"] == "pending"
        assert preview["model"] == "sonnet"
        assert isinstance(preview["tools"], list)
        assert "Bash" in preview["tools"]
        assert preview["output"] == ""
        assert preview["started_at"] is None
        assert preview["error"] is None
        assert preview["usage"]["input_tokens"] == 0

    def test_custom_model(self):
        preview = _build_agent_preview("report", "running", model="opus")
        assert preview["model"] == "opus"
        assert preview["usage"]["context_window"] == 200_000

    def test_report_task_tools(self):
        preview = _build_agent_preview("report", "pending")
        assert "Read" in preview["tools"]
        assert "Glob" in preview["tools"]
        assert "Grep" in preview["tools"]
        # Report doesn't have Bash
        assert "Bash" not in preview["tools"]

    def test_unknown_task_fallback(self):
        """Unknown task produces empty tools and empty prompt."""
        preview = _build_agent_preview("unknown_task", "pending")
        assert preview["tools"] == []
        assert preview["full_prompt"] == ""

    def test_prompt_preview_truncated(self):
        preview = _build_agent_preview("reproduce", "pending")
        # The full prompt is the SKILL.md content
        assert len(preview["prompt_preview"]) <= 203  # 200 + "..."
        assert len(preview["full_prompt"]) > 200  # Real skill file is larger

    def test_additional_prompt_included(self):
        preview = _build_agent_preview(
            "reproduce", "pending", additional_prompt="Extra instructions"
        )
        assert preview["additional_prompt"] == "Extra instructions"

    def test_budget_included(self):
        preview = _build_agent_preview("reproduce", "pending", budget=25.0)
        assert preview["budget"] == 25.0


# ---------------------------------------------------------------------------
# create_agent_card
# ---------------------------------------------------------------------------


class TestCreateAgentCard:
    async def test_creates_card_and_returns_dispatch_info(self, mock_server):
        info = await create_agent_card("reproduce", "test-study", mock_server)
        assert info.task == "reproduce"
        assert info.study == "test-study"
        assert info.status == "pending"
        assert info.card_id != ""
        assert len(info.card_id) == 12

    async def test_card_persisted_in_store(self, mock_server, study_mgr):
        info = await create_agent_card("reproduce", "test-study", mock_server)
        _, store = study_mgr.get_or_create_study("test-study")
        cards = store.list_cards()
        agent_cards = [c for c in cards if c.card_type == CardType.AGENT]
        assert len(agent_cards) == 1
        assert agent_cards[0].card_id == info.card_id

    async def test_card_broadcast(self, mock_server):
        await create_agent_card("reproduce", "test-study", mock_server)
        mock_server._broadcast.assert_called_once()
        call_args = mock_server._broadcast.call_args[0][0]
        assert call_args["type"] == "display.add"
        assert call_args["card"]["card_type"] == "agent"

    async def test_dispatch_registered(self, mock_server):
        info = await create_agent_card("reproduce", "test-study", mock_server)
        assert info.card_id in mock_server._dispatches
        assert mock_server._dispatches[info.card_id] is info

    async def test_unknown_task_raises(self, mock_server):
        with pytest.raises(ValueError, match="Unknown task"):
            await create_agent_card("unknown", "test-study", mock_server)

    async def test_no_study_manager_raises(self, mock_server_no_mgr):
        with pytest.raises(ValueError, match="No study manager"):
            await create_agent_card("reproduce", "test-study", mock_server_no_mgr)

    async def test_report_task_card_title(self, mock_server):
        await create_agent_card("report", "my-study", mock_server)
        call_args = mock_server._broadcast.call_args[0][0]
        assert call_args["card"]["title"] == "Study Report"

    async def test_reproduce_task_card_title(self, mock_server):
        await create_agent_card("reproduce", "my-study", mock_server)
        call_args = mock_server._broadcast.call_args[0][0]
        assert call_args["card"]["title"] == "Reproducibility Audit"


# ---------------------------------------------------------------------------
# cancel_agent
# ---------------------------------------------------------------------------


class TestCancelAgent:
    async def test_cancel_not_found_returns_false(self, mock_server):
        result = await cancel_agent("nonexistent", mock_server)
        assert result is False

    async def test_cancel_not_running_returns_false(self, mock_server):
        info = DispatchInfo(
            task="reproduce", study="s1", card_id="abc", status="completed"
        )
        mock_server._dispatches["abc"] = info
        result = await cancel_agent("abc", mock_server)
        assert result is False

    async def test_cancel_running_returns_true(self, mock_server, study_mgr):
        # Create a study so the store exists
        _, store = study_mgr.get_or_create_study("s1")

        # Create a real agent card in the store
        card = CardDescriptor(
            card_id="abc",
            card_type=CardType.AGENT,
            title="Reproducibility Audit",
            study="s1",
            preview={"status": "running", "output": "some output"},
        )
        store.store_card(card)
        study_mgr.register_card("abc", study_mgr._label_to_dir["s1"])

        # Set up dispatch info with mock process
        proc = MagicMock(spec=subprocess.Popen)
        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="abc",
            status="running",
            started_at="2024-01-01T00:00:00+00:00",
        )
        info.process = proc
        info.accumulated_output = "partial output"
        mock_server._dispatches["abc"] = info

        result = await cancel_agent("abc", mock_server)
        assert result is True
        assert info.status == "cancelled"
        assert info.completed_at is not None
        proc.terminate.assert_called_once()

    async def test_cancel_preserves_output(self, mock_server, study_mgr):
        """Cancelled agent card shows accumulated output."""
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="abc",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "running", "output": ""},
        )
        store.store_card(card)
        study_mgr.register_card("abc", study_mgr._label_to_dir["s1"])

        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="abc",
            status="running",
            started_at="2024-01-01T00:00:00+00:00",
        )
        info.process = MagicMock(spec=subprocess.Popen)
        info.accumulated_output = "## Progress\nStep 1 done."
        mock_server._dispatches["abc"] = info

        await cancel_agent("abc", mock_server)

        # Check broadcast includes preserved output
        update_call = None
        for call in mock_server._broadcast.call_args_list:
            msg = call[0][0]
            if msg.get("type") == "display.update":
                update_call = msg
        assert update_call is not None
        preview = update_call["card"]["preview"]
        assert "## Progress" in preview["output"]
        assert "Cancelled by user" in preview["output"]

    async def test_cancel_cleans_sandbox(self, mock_server, study_mgr, tmp_path):
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="xyz",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "running"},
        )
        store.store_card(card)
        study_mgr.register_card("xyz", study_mgr._label_to_dir["s1"])

        sandbox = tmp_path / "sandbox_reproduce"
        sandbox.mkdir()
        (sandbox / "test.txt").write_text("data")

        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="xyz",
            status="running",
            started_at="2024-01-01T00:00:00+00:00",
        )
        info.process = MagicMock(spec=subprocess.Popen)
        info.extra["sandbox"] = str(sandbox)
        mock_server._dispatches["xyz"] = info

        await cancel_agent("xyz", mock_server)
        assert not sandbox.exists()


# ---------------------------------------------------------------------------
# get_agent_status
# ---------------------------------------------------------------------------


class TestGetAgentStatus:
    def test_unknown_card_returns_none(self, mock_server):
        assert get_agent_status("nonexistent", mock_server) is None

    def test_known_card_returns_dict(self, mock_server):
        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="abc",
            status="running",
            pid=12345,
            model="opus",
        )
        mock_server._dispatches["abc"] = info
        result = get_agent_status("abc", mock_server)
        assert result is not None
        assert result["status"] == "running"
        assert result["pid"] == 12345
        assert result["model"] == "opus"
        assert result["task"] == "reproduce"
        assert result["study"] == "s1"


# ---------------------------------------------------------------------------
# reconcile_orphaned_agents
# ---------------------------------------------------------------------------


class TestReconcileOrphanedAgents:
    def test_no_study_manager_returns_zero(self, mock_server_no_mgr):
        assert reconcile_orphaned_agents(mock_server_no_mgr) == 0

    def test_no_agent_cards_returns_zero(self, mock_server):
        assert reconcile_orphaned_agents(mock_server) == 0

    def test_fixes_orphaned_running_agent(self, mock_server, study_mgr):
        """Agent card stuck in 'running' with no dispatch gets marked failed."""
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="orphan1",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "running", "output": "partial"},
        )
        store.store_card(card)

        fixed = reconcile_orphaned_agents(mock_server)
        assert fixed == 1

        # Verify the card was updated
        cards = store.list_cards()
        updated = next(c for c in cards if c.card_id == "orphan1")
        assert updated.preview["status"] == "failed"
        assert "Server restarted" in updated.preview["error"]

    def test_skips_pending_agent(self, mock_server, study_mgr):
        """Pending agent cards are not touched."""
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="pending1",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "pending"},
        )
        store.store_card(card)

        fixed = reconcile_orphaned_agents(mock_server)
        assert fixed == 0

    def test_skips_completed_agent(self, mock_server, study_mgr):
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="done1",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "completed"},
        )
        store.store_card(card)

        fixed = reconcile_orphaned_agents(mock_server)
        assert fixed == 0

    def test_skips_running_agent_with_active_dispatch(self, mock_server, study_mgr):
        """Running agent with a live dispatch entry is NOT fixed."""
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="live1",
            card_type=CardType.AGENT,
            title="Test",
            study="s1",
            preview={"status": "running"},
        )
        store.store_card(card)
        # Register a dispatch for this card
        mock_server._dispatches["live1"] = DispatchInfo(
            task="reproduce", study="s1", card_id="live1", status="running"
        )

        fixed = reconcile_orphaned_agents(mock_server)
        assert fixed == 0

    def test_skips_non_agent_cards(self, mock_server, study_mgr):
        """Non-agent cards are skipped."""
        _, store = study_mgr.get_or_create_study("s1")
        card = CardDescriptor(
            card_id="md1",
            card_type=CardType.MARKDOWN,
            title="Test",
            study="s1",
            preview={"text": "hello"},
        )
        store.store_card(card)

        fixed = reconcile_orphaned_agents(mock_server)
        assert fixed == 0


# ---------------------------------------------------------------------------
# cleanup_dispatches
# ---------------------------------------------------------------------------


class TestCleanupDispatches:
    def test_terminates_running_processes(self, mock_server):
        proc = MagicMock(spec=subprocess.Popen)
        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="abc",
            status="running",
        )
        info.process = proc
        mock_server._dispatches["abc"] = info

        cleanup_dispatches(mock_server)
        proc.terminate.assert_called_once()
        assert info.status == "cancelled"
        assert len(mock_server._dispatches) == 0

    def test_skips_non_running(self, mock_server):
        info = DispatchInfo(
            task="reproduce",
            study="s1",
            card_id="abc",
            status="completed",
        )
        info.process = MagicMock(spec=subprocess.Popen)
        mock_server._dispatches["abc"] = info

        cleanup_dispatches(mock_server)
        info.process.terminate.assert_not_called()

    def test_cleans_sandbox(self, mock_server, tmp_path):
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "file.txt").write_text("x")

        info = DispatchInfo(
            task="reproduce", study="s1", card_id="abc", status="completed"
        )
        info.extra["sandbox"] = str(sandbox)
        mock_server._dispatches["abc"] = info

        cleanup_dispatches(mock_server)
        assert not sandbox.exists()

    def test_clears_dispatches_dict(self, mock_server):
        mock_server._dispatches["a"] = DispatchInfo(
            task="reproduce", study="s1", card_id="a", status="completed"
        )
        mock_server._dispatches["b"] = DispatchInfo(
            task="report", study="s2", card_id="b", status="failed"
        )
        cleanup_dispatches(mock_server)
        assert len(mock_server._dispatches) == 0

    def test_handles_terminate_oserror(self, mock_server):
        """OSError from terminate is silently caught."""
        proc = MagicMock(spec=subprocess.Popen)
        proc.terminate.side_effect = OSError("Process already dead")
        info = DispatchInfo(
            task="reproduce", study="s1", card_id="abc", status="running"
        )
        info.process = proc
        mock_server._dispatches["abc"] = info

        cleanup_dispatches(mock_server)  # Should not raise
        assert info.status == "cancelled"


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------


class TestSandboxHelpers:
    def test_create_sandbox(self, tmp_path):
        output_dir = tmp_path / "study-output"
        output_dir.mkdir()
        (output_dir / "scripts").mkdir()
        (output_dir / "scripts" / "01_cohort.py").write_text("print('hello')")
        (output_dir / "data").mkdir()
        (output_dir / "data" / "cohort.parquet").write_bytes(b"fake-parquet")

        sandbox = _create_sandbox(output_dir)
        assert sandbox.name == "study-output_reproduce"
        assert sandbox.exists()
        assert (sandbox / "scripts" / "01_cohort.py").exists()
        assert (sandbox / "scripts" / "01_cohort.py").read_text() == "print('hello')"
        assert (sandbox / "data" / "cohort.parquet").exists()

    def test_create_sandbox_replaces_existing(self, tmp_path):
        output_dir = tmp_path / "study-output"
        output_dir.mkdir()
        (output_dir / "file.txt").write_text("new")

        sandbox = output_dir.parent / "study-output_reproduce"
        sandbox.mkdir()
        (sandbox / "old_file.txt").write_text("old")

        result = _create_sandbox(output_dir)
        assert result == sandbox
        assert not (sandbox / "old_file.txt").exists()
        assert (sandbox / "file.txt").read_text() == "new"

    def test_cleanup_sandbox_removes_dir(self, tmp_path):
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        (sandbox / "file.txt").write_text("data")

        _cleanup_sandbox(sandbox)
        assert not sandbox.exists()

    def test_cleanup_sandbox_nonexistent_is_noop(self, tmp_path):
        sandbox = tmp_path / "nonexistent"
        _cleanup_sandbox(sandbox)  # Should not raise


# ---------------------------------------------------------------------------
# _is_pid_alive
# ---------------------------------------------------------------------------


class TestIsPidAlive:
    def test_current_process_is_alive(self):
        assert _is_pid_alive(os.getpid()) is True

    def test_very_large_pid_is_dead(self):
        assert _is_pid_alive(999_999_999) is False
