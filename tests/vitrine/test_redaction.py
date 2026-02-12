"""Tests for m4.vitrine.redaction.

Tests cover:
- Redactor creation with defaults and overrides
- Pattern matching on column names
- redact_dataframe() with PHI masking and ID hashing
- enforce_row_limit() with truncation
- Environment variable configuration
"""

import pandas as pd

from m4.vitrine.redaction import Redactor


class TestRedactorDefaults:
    def test_enabled_by_default(self):
        r = Redactor()
        assert r.enabled is True

    def test_default_max_rows(self):
        r = Redactor()
        assert r.max_rows == 10_000

    def test_hash_ids_disabled_by_default(self):
        r = Redactor()
        assert r.hash_ids is False

    def test_has_default_patterns(self):
        r = Redactor()
        assert len(r._patterns) > 0


class TestRedactorOverrides:
    def test_disable(self):
        r = Redactor(enabled=False)
        assert r.enabled is False

    def test_custom_max_rows(self):
        r = Redactor(max_rows=500)
        assert r.max_rows == 500

    def test_custom_patterns(self):
        r = Redactor(patterns=[r"(?i)custom_col"])
        assert len(r._patterns) == 1

    def test_hash_ids_override(self):
        r = Redactor(hash_ids=True)
        assert r.hash_ids is True


class TestRedactorEnvConfig:
    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_REDACT", "0")
        r = Redactor()
        assert r.enabled is False

    def test_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_REDACT", "1")
        r = Redactor()
        assert r.enabled is True

    def test_max_rows_via_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_MAX_ROWS", "2000")
        r = Redactor()
        assert r.max_rows == 2000

    def test_invalid_max_rows_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_MAX_ROWS", "not_a_number")
        r = Redactor()
        assert r.max_rows == 10_000

    def test_hash_ids_via_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_HASH_IDS", "1")
        r = Redactor()
        assert r.hash_ids is True

    def test_custom_patterns_via_env(self, monkeypatch):
        monkeypatch.setenv("M4_VITRINE_REDACT_PATTERNS", r"(?i)foo,(?i)bar")
        r = Redactor()
        assert len(r._patterns) == 2


class TestPatternMatching:
    def test_matches_name_columns(self):
        r = Redactor()
        assert r._matches_pattern("first_name") is True
        assert r._matches_pattern("last_name") is True
        assert r._matches_pattern("FirstName") is True

    def test_matches_address_columns(self):
        r = Redactor()
        assert r._matches_pattern("address") is True
        assert r._matches_pattern("street") is True
        assert r._matches_pattern("zip") is True

    def test_matches_contact_columns(self):
        r = Redactor()
        assert r._matches_pattern("phone") is True
        assert r._matches_pattern("email") is True
        assert r._matches_pattern("ssn") is True

    def test_matches_dob(self):
        r = Redactor()
        assert r._matches_pattern("date_of_birth") is True
        assert r._matches_pattern("dob") is True

    def test_no_match_on_safe_columns(self):
        r = Redactor()
        assert r._matches_pattern("age") is False
        assert r._matches_pattern("diagnosis") is False
        assert r._matches_pattern("subject_id") is False


class TestRedactDataFrame:
    """Test redact_dataframe() implementation."""

    def test_redacts_phi_columns(self):
        r = Redactor()
        df = pd.DataFrame({"first_name": ["Alice", "Bob"], "age": [30, 25]})
        result = r.redact_dataframe(df)
        assert result is not df  # Returns a copy
        assert list(result["first_name"]) == ["[REDACTED]", "[REDACTED]"]
        assert list(result["age"]) == [30, 25]  # Untouched

    def test_disabled_returns_same_object(self):
        r = Redactor(enabled=False)
        df = pd.DataFrame({"first_name": ["Alice"], "age": [30]})
        result = r.redact_dataframe(df)
        assert result is df

    def test_hash_ids_columns(self):
        r = Redactor(hash_ids=True)
        df = pd.DataFrame({"subject_id": [12345], "age": [30]})
        result = r.redact_dataframe(df)
        val = result["subject_id"].iloc[0]
        assert isinstance(val, str)
        assert len(val) == 12
        # Should be hex
        int(val, 16)

    def test_hash_ids_preserves_nan(self):
        import numpy as np

        r = Redactor(hash_ids=True)
        df = pd.DataFrame({"subject_id": [12345, np.nan, 67890]})
        result = r.redact_dataframe(df)
        assert pd.isna(result["subject_id"].iloc[1])
        assert isinstance(result["subject_id"].iloc[0], str)

    def test_hash_ids_deterministic(self):
        r = Redactor(hash_ids=True)
        df1 = pd.DataFrame({"patient_id": [100]})
        df2 = pd.DataFrame({"patient_id": [100]})
        r1 = r.redact_dataframe(df1)
        r2 = r.redact_dataframe(df2)
        assert r1["patient_id"].iloc[0] == r2["patient_id"].iloc[0]

    def test_custom_patterns(self):
        r = Redactor(patterns=[r"(?i)secret"])
        df = pd.DataFrame({"secret_field": ["xyz"], "normal": [1]})
        result = r.redact_dataframe(df)
        assert list(result["secret_field"]) == ["[REDACTED]"]
        assert list(result["normal"]) == [1]


class TestEnforceRowLimit:
    """Test enforce_row_limit() implementation."""

    def test_truncation_over_limit(self):
        r = Redactor(max_rows=100)
        df = pd.DataFrame({"x": range(200)})
        result_df, was_truncated = r.enforce_row_limit(df)
        assert len(result_df) == 100
        assert was_truncated is True

    def test_no_truncation_under_limit(self):
        r = Redactor(max_rows=100)
        df = pd.DataFrame({"x": range(50)})
        result_df, was_truncated = r.enforce_row_limit(df)
        assert len(result_df) == 50
        assert was_truncated is False

    def test_exact_limit(self):
        r = Redactor(max_rows=100)
        df = pd.DataFrame({"x": range(100)})
        result_df, was_truncated = r.enforce_row_limit(df)
        assert len(result_df) == 100
        assert was_truncated is False

    def test_disabled_skips_limit(self):
        r = Redactor(enabled=False, max_rows=10)
        df = pd.DataFrame({"x": range(100)})
        result_df, was_truncated = r.enforce_row_limit(df)
        assert result_df is df
        assert was_truncated is False
