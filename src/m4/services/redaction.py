from __future__ import annotations

from pathlib import Path
from typing import Any

_sensitive_values: set[str] = set()


def register_sensitive_value(value: str | None) -> None:
    if value:
        _sensitive_values.add(value)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact_sensitive(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, Path):
        return redact_sensitive(str(value))
    if isinstance(value, str):
        redacted = value
        for sensitive in sorted(_sensitive_values, key=len, reverse=True):
            if sensitive:
                redacted = redacted.replace(sensitive, "<redacted>")
        return redacted
    return value
