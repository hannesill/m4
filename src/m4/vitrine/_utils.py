"""Shared utilities for the vitrine package.

Deduplicates common patterns used across multiple modules:
PID checks, directory resolution, path escaping, health checks,
and file-type constants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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
