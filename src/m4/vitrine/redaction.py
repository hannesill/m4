"""PHI/PII redaction guardrails for the display pipeline.

Clinical data demands safe defaults. This module provides configurable
redaction that runs before any data leaves the Python process, ensuring
columns matching identifier patterns are masked and row counts are capped.

Configuration via environment variables:
    M4_VITRINE_REDACT: Enable PHI redaction (default: "1", set "0" to disable)
    M4_VITRINE_MAX_ROWS: Max rows stored per artifact (default: 10000)
    M4_VITRINE_REDACT_PATTERNS: Custom regex patterns, comma-separated
    M4_VITRINE_HASH_IDS: Hash subject_id etc. instead of raw values (default: "0")
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Default patterns for columns likely to contain PHI
_DEFAULT_IDENTIFIER_PATTERNS = [
    r"(?i)(first|last|middle)_?name",
    r"(?i)address|street|city|zip|postal",
    r"(?i)phone|fax|email|ssn|mrn",
    r"(?i)date_of_birth|dob",
]

_DEFAULT_MAX_ROWS = 10_000


class Redactor:
    """Configurable PHI/PII redaction for display output.

    Safe by default: redaction is enabled unless explicitly disabled via
    M4_VITRINE_REDACT=0. Researchers working with de-identified datasets
    (like MIMIC) can disable it. The opt-out is intentionally explicit —
    forgetting to configure is safe, not unsafe.

    Args:
        enabled: Override the M4_VITRINE_REDACT env var.
        max_rows: Override the M4_VITRINE_MAX_ROWS env var.
        patterns: Override the default identifier patterns.
        hash_ids: Override the M4_VITRINE_HASH_IDS env var.
    """

    def __init__(
        self,
        enabled: bool | None = None,
        max_rows: int | None = None,
        patterns: list[str] | None = None,
        hash_ids: bool | None = None,
    ) -> None:
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("M4_VITRINE_REDACT", "1") != "0"

        if max_rows is not None:
            self.max_rows = max_rows
        else:
            try:
                self.max_rows = int(
                    os.getenv("M4_VITRINE_MAX_ROWS", str(_DEFAULT_MAX_ROWS))
                )
            except ValueError:
                self.max_rows = _DEFAULT_MAX_ROWS

        if patterns is not None:
            self._patterns = [re.compile(p) for p in patterns]
        else:
            env_patterns = os.getenv("M4_VITRINE_REDACT_PATTERNS")
            if env_patterns:
                self._patterns = [
                    re.compile(p.strip()) for p in env_patterns.split(",") if p.strip()
                ]
            else:
                self._patterns = [re.compile(p) for p in _DEFAULT_IDENTIFIER_PATTERNS]

        if hash_ids is not None:
            self.hash_ids = hash_ids
        else:
            self.hash_ids = os.getenv("M4_VITRINE_HASH_IDS", "0") != "0"

    def redact_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mask columns matching identifier patterns.

        Returns a copy with matched columns replaced by '[REDACTED]'.
        The original DataFrame is never modified.

        Args:
            df: Input DataFrame to redact.

        Returns:
            A new DataFrame with PHI columns masked.
        """
        if not self.enabled:
            return df

        import hashlib

        import pandas as pd

        result = df.copy()

        for col in result.columns:
            if self._matches_pattern(col):
                result[col] = "[REDACTED]"

        if self.hash_ids:
            id_pattern = re.compile(r"(?i)(subject|patient|hadm|stay|icustay)_?id")
            for col in result.columns:
                if id_pattern.search(col):
                    result[col] = result[col].map(
                        lambda v: (
                            hashlib.sha256(str(v).encode()).hexdigest()[:12]
                            if pd.notna(v)
                            else v
                        )
                    )

        return result

    def enforce_row_limit(self, df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
        """Cap rows at the configured limit.

        Args:
            df: Input DataFrame.

        Returns:
            Tuple of (possibly truncated DataFrame, was_truncated flag).
        """
        if not self.enabled:
            return df, False

        if len(df) > self.max_rows:
            return df.head(self.max_rows), True

        return df, False

    def _matches_pattern(self, column_name: str) -> bool:
        """Check if a column name matches any identifier pattern.

        Args:
            column_name: The column name to check.

        Returns:
            True if the column name matches a PHI pattern.
        """
        return any(p.search(column_name) for p in self._patterns)
