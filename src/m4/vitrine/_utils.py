"""Shared utilities for the vitrine package.

Deduplicates common patterns used across multiple modules:
PID checks, directory resolution, path escaping, health checks,
and file-type constants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PID check
# ---------------------------------------------------------------------------


def is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Vitrine directory resolution
# ---------------------------------------------------------------------------


def get_vitrine_dir() -> Path:
    """Resolve the vitrine directory at {project_root}/.vitrine/.

    Returns the path without performing migration (caller handles that).
    """
    try:
        from m4.config import _PROJECT_ROOT

        return _PROJECT_ROOT / ".vitrine"
    except Exception:
        import tempfile

        return Path(tempfile.gettempdir()) / ".vitrine"


# ---------------------------------------------------------------------------
# DuckDB path escaping
# ---------------------------------------------------------------------------


def duckdb_safe_path(path: Path | str) -> str:
    """Escape a file path for safe interpolation into DuckDB SQL string literals.

    Single quotes in the path are doubled to prevent SQL injection.
    """
    return str(path).replace("'", "''")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def health_check(url: str, session_id: str | None = None) -> bool:
    """GET /api/health and optionally validate session_id matches."""
    try:
        import urllib.request

        req = urllib.request.Request(f"{url}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data.get("status") != "ok":
                return False
            if session_id is not None:
                return data.get("session_id") == session_id
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# File-type constants
# ---------------------------------------------------------------------------

TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".sql",
        ".r",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".txt",
        ".cfg",
        ".log",
        ".sh",
        ".bash",
        ".ini",
        ".env",
    }
)

IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


# ---------------------------------------------------------------------------
# Option description resolution
# ---------------------------------------------------------------------------


def resolve_option_descriptions(
    values: dict[str, Any],
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cross-reference selected values with field specs to get option descriptions.

    For single-select fields, returns::

        {"field_name": {"selected": "label", "description": "desc"}}

    For multi-select fields, returns::

        {"field_name": {"selected": ["a", "b"], "descriptions": ["desc_a", "desc_b"]}}

    Fields whose selected value doesn't match any option (e.g. "Other" free-text)
    are included with an empty description.

    Args:
        values: Submitted form values (``{field_name: label_or_list}``).
        fields: Field specs from ``card.preview["fields"]``.

    Returns:
        Dict mapping field names to enriched selection dicts.
    """
    # Build a lookup: field_name -> {label: description}
    field_options: dict[str, dict[str, str]] = {}
    for f in fields:
        name = f.get("name", "")
        opts = f.get("options", [])
        label_to_desc: dict[str, str] = {}
        for opt in opts:
            if isinstance(opt, dict):
                label_to_desc[opt.get("label", "")] = opt.get("description", "")
            elif isinstance(opt, str):
                label_to_desc[opt] = ""
        field_options[name] = label_to_desc

    result: dict[str, Any] = {}
    for field_name, selected in values.items():
        descs = field_options.get(field_name, {})
        if isinstance(selected, list):
            result[field_name] = {
                "selected": selected,
                "descriptions": [descs.get(s, "") for s in selected],
            }
        else:
            result[field_name] = {
                "selected": selected,
                "description": descs.get(selected, "") if selected else "",
            }
    return result
