"""Tool call telemetry for M4.

Tracks every tool invocation regardless of interface (MCP server or Python API).
Caller context (interface type, agent ID) flows via contextvars — no signature
changes to Tool protocol or tool implementations.

Records are written as JSONL to m4_data/telemetry/tool_calls.jsonl and logged
via the standard logging module. Disable file output with M4_TELEMETRY=off.
"""

import dataclasses
import json
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from m4.core.datasets import DatasetDefinition
from m4.core.tools.base import Tool, ToolInput

logger = logging.getLogger("m4.telemetry")

# ---------------------------------------------------------------------------
# Context variables — set by MCP server / Python API / external agents
# ---------------------------------------------------------------------------

_interface_var: ContextVar[str] = ContextVar("m4_interface", default="unknown")
_agent_id_var: ContextVar[str | None] = ContextVar("m4_agent_id", default=None)


def set_interface(name: str) -> None:
    """Set the current interface context (e.g. 'mcp', 'python_api')."""
    _interface_var.set(name)


def set_agent_id(agent_id: str) -> None:
    """Set the current agent ID for telemetry attribution."""
    _agent_id_var.set(agent_id)


# ---------------------------------------------------------------------------
# ToolCallRecord
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    tool_name: str
    interface: str
    agent_id: str | None
    dataset_name: str | None
    timestamp: str  # ISO 8601
    duration_ms: float
    success: bool
    error_type: str | None
    error_message: str | None
    params_summary: dict[str, Any]


# ---------------------------------------------------------------------------
# JSON encoder that gracefully handles non-serializable values
# ---------------------------------------------------------------------------


class _SafeEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        return str(o)


def _to_json(obj: Any) -> str:
    return json.dumps(obj, cls=_SafeEncoder)


# ---------------------------------------------------------------------------
# TelemetryWriter — manages the JSONL file handler
# ---------------------------------------------------------------------------


class TelemetryWriter:
    """Manages the rotating JSONL file handler for telemetry records.

    Lazily initialised on first write. Respects M4_TELEMETRY=off.
    """

    def __init__(self) -> None:
        self._handler: RotatingFileHandler | None = None
        self._initialized = False

    def _init_handler(self) -> None:
        self._initialized = True

        if os.environ.get("M4_TELEMETRY", "").lower() == "off":
            return

        from m4.config import get_telemetry_dir

        telemetry_dir = get_telemetry_dir()
        self._handler = RotatingFileHandler(
            telemetry_dir / "tool_calls.jsonl",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record_json: str) -> None:
        if not self._initialized:
            self._init_handler()
        if self._handler is None:
            return
        log_record = logging.LogRecord(
            name="m4.telemetry",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=record_json,
            args=None,
            exc_info=None,
        )
        self._handler.emit(log_record)

    def reset(self) -> None:
        """Reset state (for testing)."""
        self._handler = None
        self._initialized = False


_writer = TelemetryWriter()


# ---------------------------------------------------------------------------
# invoke_tracked — the main wrapper
# ---------------------------------------------------------------------------


def invoke_tracked(tool: Tool, dataset: DatasetDefinition, params: ToolInput) -> Any:
    """Invoke a tool with telemetry tracking.

    Wraps tool.invoke() to record timing, success/failure, and context.
    Records are written to JSONL and logged at INFO level.
    On failure, the original exception is re-raised.
    """
    interface = _interface_var.get()
    agent_id = _agent_id_var.get()
    dataset_name = getattr(dataset, "name", None)

    # Build params summary
    try:
        params_summary = dataclasses.asdict(params)
    except (TypeError, AttributeError):
        params_summary = {}

    start = time.monotonic()
    success = True
    error_type = None
    error_message = None

    try:
        result = tool.invoke(dataset, params)
        return result
    except Exception as exc:
        success = False
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        record = ToolCallRecord(
            tool_name=tool.name,
            interface=interface,
            agent_id=agent_id,
            dataset_name=dataset_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            error_message=error_message,
            params_summary=params_summary,
        )

        record_json = _to_json(dataclasses.asdict(record))

        logger.info(record_json)
        _writer.emit(record_json)
