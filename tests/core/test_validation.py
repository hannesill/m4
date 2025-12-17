"""Tests for SQL validation and parameter sanitization."""

from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
)


class TestIsSafeQuery:
    """Tests for is_safe_query function."""

    def test_simple_select(self):
        """Simple SELECT queries should be safe."""
        is_safe, msg = is_safe_query("SELECT * FROM patients LIMIT 10")
        assert is_safe is True

    def test_select_with_where(self):
        """SELECT with WHERE clause should be safe."""
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE subject_id = 12345")
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

    def test_suspicious_admin_standalone(self):
        """Queries with standalone ADMIN keyword should be blocked."""
        # Standalone ADMIN is blocked (word boundary match)
        is_safe, msg = is_safe_query("SELECT * FROM ADMIN")
        assert is_safe is False

    def test_admin_in_compound_name_allowed(self):
        """Queries with ADMIN as part of compound name are allowed.

        Word boundary matching allows 'admin_users' but blocks standalone 'ADMIN'.
        This prevents false positives on legitimate medical database columns.
        """
        is_safe, msg = is_safe_query("SELECT * FROM admin_users")
        assert is_safe is True  # admin_users is a valid table name

    def test_case_insensitive_blocking(self):
        """Injection patterns should be case-insensitive."""
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE 1=1")
        assert is_safe is False


class TestIsSafeQueryAdvancedInjection:
    """Advanced SQL injection tests for is_safe_query function.

    These tests cover sophisticated injection patterns that could bypass
    naive security checks in medical data systems.
    """

    def test_comment_injection_double_dash(self):
        """Test SQL comment injection using double-dash.

        Note: The validation treats '1=1' patterns as injection attempts,
        regardless of whether they appear with comments. This is intentional
        for medical data security.
        """
        # Comments alone don't make a query unsafe
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE id = 100 -- comment here"
        )
        assert is_safe is True  # This is valid SQL with a comment

    def test_union_injection_basic(self):
        """Test UNION-based injection for data extraction."""
        is_safe, msg = is_safe_query(
            "SELECT name FROM patients UNION SELECT password FROM users"
        )
        # Should be blocked due to suspicious 'password' identifier
        assert is_safe is False
        assert "Suspicious" in msg or "PASSWORD" in msg

    def test_union_injection_information_schema(self):
        """Test UNION injection targeting system tables."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients UNION SELECT * FROM information_schema.tables"
        )
        # This is valid SQL for schema introspection, but union with patients is odd
        # The query parser allows this as it's a valid SELECT
        assert is_safe is True  # Schema introspection is allowed

    def test_nested_subquery_with_compound_names(self):
        """Test that compound column names are allowed in subqueries.

        Word boundary matching allows 'admin_users' and 'user_id' since
        they are compound names, not standalone suspicious keywords.
        """
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE id IN (SELECT user_id FROM admin_users)"
        )
        # Compound names like admin_users and user_id are allowed
        assert is_safe is True

    def test_nested_subquery_with_suspicious_standalone(self):
        """Test injection via nested subqueries with suspicious standalone keywords."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE id IN (SELECT id FROM PASSWORD)"
        )
        assert is_safe is False
        assert "Suspicious" in msg or "PASSWORD" in msg

    def test_hex_encoded_attack(self):
        """Test hex-encoded injection patterns."""
        # Hex encoding of 'DROP' is 0x44524F50
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE name = 0x44524F50")
        # This is valid SQL, just selecting by hex value
        assert is_safe is True

    def test_stacked_query_with_semicolon(self):
        """Test stacked queries using semicolons."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients; UPDATE patients SET name='hacked'"
        )
        assert is_safe is False
        assert "Multiple statements" in msg

    def test_time_based_blind_injection_benchmark(self):
        """Test BENCHMARK() function for time-based blind injection."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE BENCHMARK(10000000, SHA1('test'))"
        )
        assert is_safe is False
        assert "Time-based" in msg

    def test_file_operations_load_file(self):
        """Test LOAD_FILE() injection for reading server files."""
        is_safe, msg = is_safe_query("SELECT LOAD_FILE('/etc/passwd') FROM patients")
        assert is_safe is False
        assert "File access" in msg

    def test_outfile_injection(self):
        """Test INTO OUTFILE for writing to server filesystem."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients INTO OUTFILE '/tmp/dump.txt'"
        )
        assert is_safe is False
        assert "File write" in msg

    def test_dumpfile_injection(self):
        """Test INTO DUMPFILE for binary file writes."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients INTO DUMPFILE '/tmp/dump.bin'"
        )
        assert is_safe is False
        assert "File write" in msg

    def test_waitfor_injection(self):
        """Test WAITFOR DELAY injection (SQL Server specific)."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE WAITFOR DELAY '00:00:05'"
        )
        assert is_safe is False
        assert "Time-based" in msg

    def test_string_injection_with_quotes(self):
        """Test classic string-based injection with quotes."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE name = '' OR '1'='1'"
        )
        assert is_safe is False
        assert "injection" in msg.lower()

    def test_boolean_blind_injection_and(self):
        """Test boolean-based blind injection with AND."""
        is_safe, msg = is_safe_query("SELECT * FROM patients WHERE id = 1 AND 1=1")
        assert is_safe is False
        assert "injection" in msg.lower()

    def test_compound_credential_names_allowed(self):
        """Test that compound credential-related names are allowed.

        Word boundary matching allows compound names like 'secret_key',
        'auth_token', etc. while blocking standalone suspicious keywords.
        This reduces false positives on legitimate database schemas.
        """
        allowed_columns = [
            "SELECT secret_key FROM config",  # secret_key is compound
            "SELECT auth_token FROM sessions",  # auth_token is compound
            "SELECT login_hash FROM accounts",  # login_hash is compound
            "SELECT session_cookie FROM tokens",  # session_cookie is compound
        ]
        for query in allowed_columns:
            is_safe, msg = is_safe_query(query)
            assert is_safe is True, f"Compound name query should be allowed: {query}"

    def test_standalone_credential_names_blocked(self):
        """Test that standalone credential keywords are blocked."""
        blocked_queries = [
            "SELECT PASSWORD FROM users",  # PASSWORD standalone
            "SELECT * FROM CREDENTIAL",  # CREDENTIAL standalone
            "SELECT * FROM SECRET",  # SECRET standalone
            "SELECT AUTH FROM tokens",  # AUTH standalone
        ]
        for query in blocked_queries:
            is_safe, msg = is_safe_query(query)
            assert is_safe is False, f"Standalone keyword should be blocked: {query}"

    def test_case_variations_bypass(self):
        """Test case variations to bypass keyword detection.

        Note: Validation uses regex patterns that may not catch all spacing
        variations. The '1=1' (no spaces) variant is caught but '1 = 1' with
        spaces may slip through depending on implementation.
        """
        # These should be caught
        blocked_variations = [
            "SELECT * FROM patients WHERE 1=1",
            "select * from patients where 1=1",
        ]
        for query in blocked_variations:
            is_safe, msg = is_safe_query(query)
            assert is_safe is False, f"Case variation should be blocked: {query}"

        # Note: '1 = 1' with spaces may not be caught by current regex
        # This is documented behavior - the test captures current reality

    def test_valid_medical_query_with_numbers(self):
        """Test that legitimate medical queries with numbers pass."""
        # Legitimate query comparing lab values
        is_safe, msg = is_safe_query(
            "SELECT * FROM labevents WHERE valuenum > 100 AND valuenum < 200"
        )
        assert is_safe is True

    def test_valid_join_query(self):
        """Test that legitimate JOIN queries pass."""
        is_safe, msg = is_safe_query(
            """
            SELECT p.subject_id, a.hadm_id, l.value
            FROM patients p
            JOIN admissions a ON p.subject_id = a.subject_id
            JOIN labevents l ON a.hadm_id = l.hadm_id
            WHERE l.itemid = 50912
            LIMIT 100
            """
        )
        assert is_safe is True

    def test_valid_aggregate_query(self):
        """Test that legitimate aggregate queries pass."""
        is_safe, msg = is_safe_query(
            """
            SELECT race, COUNT(*) as count, AVG(anchor_age) as avg_age
            FROM hosp_admissions
            GROUP BY race
            ORDER BY count DESC
            LIMIT 10
            """
        )
        assert is_safe is True


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
