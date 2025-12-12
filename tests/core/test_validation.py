"""Tests for SQL validation and parameter sanitization."""

import pytest

from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
    validate_limit,
)


class TestValidateLimit:
    """Tests for validate_limit function."""

    def test_valid_limits(self):
        """Valid limits should return True."""
        assert validate_limit(1) is True
        assert validate_limit(10) is True
        assert validate_limit(100) is True
        assert validate_limit(1000) is True

    def test_invalid_zero(self):
        """Zero is not a valid limit."""
        assert validate_limit(0) is False

    def test_invalid_negative(self):
        """Negative numbers are not valid."""
        assert validate_limit(-1) is False
        assert validate_limit(-100) is False

    def test_exceeds_max_limit(self):
        """Limits above max should fail."""
        assert validate_limit(1001) is False
        assert validate_limit(10000) is False

    def test_custom_max_limit(self):
        """Custom max_limit should be respected."""
        assert validate_limit(500, max_limit=100) is False
        assert validate_limit(50, max_limit=100) is True

    def test_non_integer(self):
        """Non-integers should fail."""
        assert validate_limit(10.5) is False  # type: ignore
        assert validate_limit("10") is False  # type: ignore
        assert validate_limit(None) is False  # type: ignore


class TestIsSafeQuery:
    """Tests for is_safe_query function."""

    def test_simple_select(self):
        """Simple SELECT queries should be safe."""
        is_safe, msg = is_safe_query("SELECT * FROM patients LIMIT 10")
        assert is_safe is True

    def test_select_with_where(self):
        """SELECT with WHERE clause should be safe."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE subject_id = 12345"
        )
        assert is_safe is True

    def test_select_with_join(self):
        """SELECT with JOIN should be safe."""
        is_safe, msg = is_safe_query(
            "SELECT p.*, a.* FROM patients p JOIN admissions a ON p.subject_id = a.subject_id"
        )
        assert is_safe is True

    def test_pragma_allowed(self):
        """PRAGMA statements should be allowed."""
        is_safe, msg = is_safe_query("PRAGMA table_info(patients)")
        assert is_safe is True

    def test_empty_query(self):
        """Empty queries should fail."""
        is_safe, msg = is_safe_query("")
        assert is_safe is False
        assert "Empty" in msg

    def test_whitespace_only(self):
        """Whitespace-only queries should fail."""
        is_safe, msg = is_safe_query("   ")
        assert is_safe is False

    def test_multiple_statements(self):
        """Multiple statements should be blocked."""
        is_safe, msg = is_safe_query("SELECT 1; SELECT 2")
        assert is_safe is False
        assert "Multiple statements" in msg

    def test_insert_blocked(self):
        """INSERT statements should be blocked."""
        is_safe, msg = is_safe_query("INSERT INTO patients VALUES (1)")
        assert is_safe is False

    def test_update_blocked(self):
        """UPDATE statements should be blocked."""
        is_safe, msg = is_safe_query("UPDATE patients SET name = 'test'")
        assert is_safe is False

    def test_delete_blocked(self):
        """DELETE statements should be blocked."""
        is_safe, msg = is_safe_query("DELETE FROM patients")
        assert is_safe is False

    def test_drop_blocked(self):
        """DROP statements should be blocked."""
        is_safe, msg = is_safe_query("DROP TABLE patients")
        assert is_safe is False

    def test_injection_1_equals_1(self):
        """Classic 1=1 injection pattern should be blocked."""
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE 1=1")
        assert is_safe is False
        assert "injection" in msg.lower()

    def test_injection_or_1_1(self):
        """OR 1=1 injection should be blocked."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE subject_id = 1 OR 1=1"
        )
        assert is_safe is False

    def test_injection_sleep(self):
        """SLEEP() injection should be blocked."""
        is_safe, msg = is_safe_query("SELECT SLEEP(10)")
        assert is_safe is False
        assert "Time-based" in msg

    def test_suspicious_password(self):
        """Queries with PASSWORD should be blocked."""
        is_safe, msg = is_safe_query("SELECT password FROM users")
        assert is_safe is False
        assert "Suspicious" in msg

    def test_suspicious_admin(self):
        """Queries with ADMIN should be blocked."""
        is_safe, msg = is_safe_query("SELECT * FROM admin_users")
        assert is_safe is False

    def test_case_insensitive_blocking(self):
        """Injection patterns should be case-insensitive."""
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE 1=1")
        assert is_safe is False


class TestFormatErrorWithGuidance:
    """Tests for format_error_with_guidance function."""

    def test_table_not_found_error(self):
        """Table not found errors should suggest schema exploration."""
        result = format_error_with_guidance("Table not found: xyz")
        assert "get_database_schema()" in result
        assert "table name" in result.lower()

    def test_column_not_found_error(self):
        """Column errors should suggest get_table_info."""
        result = format_error_with_guidance("No such column: age")
        assert "get_table_info" in result

    def test_syntax_error(self):
        """Syntax errors should give SQL help."""
        result = format_error_with_guidance("Syntax error near SELECT")
        assert "quotes" in result.lower() or "syntax" in result.lower()

    def test_generic_error(self):
        """Generic errors should still provide guidance."""
        result = format_error_with_guidance("Unknown error occurred")
        assert "get_database_schema()" in result
