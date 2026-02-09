"""Tests for m4.vitrine.redaction.

Tests cover:
- Redactor creation with defaults and overrides
- Pattern matching on column names
- Pass-through behavior (stub implementation)
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


class TestPassThrough:
    """Verify the stub implementation is a clean pass-through."""

    def test_redact_dataframe_returns_same(self):
        r = Redactor()
        df = pd.DataFrame({"first_name": ["Alice"], "age": [30]})
        result = r.redact_dataframe(df)
        # Currently pass-through — same object returned
        assert result is df

    def test_enforce_row_limit_returns_same(self):
        r = Redactor()
        df = pd.DataFrame({"x": range(20_000)})
        result_df, was_truncated = r.enforce_row_limit(df)
        # Currently pass-through
        assert result_df is df
        assert was_truncated is False
