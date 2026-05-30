from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, TextIO

from m4.services.redaction import redact_sensitive


@dataclass
class EventReporter:
    command: str = "init"
    enabled: bool = False

    def emit(self, event: str, **fields: Any) -> None:
        return None

    def operation_started(self, **fields: Any) -> None:
        self.emit("operation_started", command=self.command, **fields)

    def operation_completed(self, result: dict[str, Any]) -> None:
        self.emit("operation_completed", command=self.command, result=result)

    def operation_failed(self, error: dict[str, Any]) -> None:
        self.emit("operation_failed", command=self.command, error=error)


@dataclass
class NoopEventReporter(EventReporter):
    enabled: bool = False


@dataclass
class NdjsonEventReporter(EventReporter):
    stream: TextIO = field(default_factory=lambda: sys.stdout)
    enabled: bool = True
    _sequence: int = field(default=0, init=False)

    def emit(self, event: str, **fields: Any) -> None:
        self._sequence += 1
        payload = {
            "version": 1,
            "sequence": self._sequence,
            "time": time.time(),
            "event": event,
            **fields,
        }
        self.stream.write(json.dumps(redact_sensitive(payload), allow_nan=False) + "\n")
        self.stream.flush()


def get_event_reporter(reporter: EventReporter | None) -> EventReporter:
    return reporter if reporter is not None else NoopEventReporter()
