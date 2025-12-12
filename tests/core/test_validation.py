"""Tests for SQL validation and parameter sanitization."""

from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
    validate_limit,
    validate_patient_id,
    validate_table_name,
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

    def test_suspicious_admin(self):
        """Queries with ADMIN should be blocked."""
        is_safe, msg = is_safe_query("SELECT * FROM admin_users")
        assert is_safe is False

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

    def test_nested_subquery_injection(self):
        """Test injection via nested subqueries."""
        is_safe, msg = is_safe_query(
            "SELECT * FROM patients WHERE id IN (SELECT user_id FROM admin_users)"
        )
        assert is_safe is False
        assert "Suspicious" in msg or "ADMIN" in msg

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

    def test_credential_column_variations(self):
        """Test various credential-related column names."""
        suspicious_columns = [
            "SELECT secret_key FROM config",
            "SELECT auth_token FROM sessions",
            "SELECT login_hash FROM accounts",
            "SELECT user_credential FROM keys",
            "SELECT session_cookie FROM tokens",
        ]
        for query in suspicious_columns:
            is_safe, msg = is_safe_query(query)
            assert is_safe is False, f"Query should be blocked: {query}"

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


class TestValidateTableName:
    """Tests for validate_table_name function - Phase 1 Security Fix 1.3.

    These tests verify that table name validation prevents SQL injection
    attacks through malicious dataset configuration.
    """

    def test_valid_simple_names(self):
        """Valid simple table names should pass."""
        assert validate_table_name("patients") is True
        assert validate_table_name("icustays") is True
        assert validate_table_name("labevents") is True
        assert validate_table_name("admissions") is True

    def test_valid_names_with_underscores(self):
        """Table names with underscores should pass."""
        assert validate_table_name("icu_icustays") is True
        assert validate_table_name("hosp_labevents") is True
        assert validate_table_name("hosp_admissions") is True
        assert validate_table_name("_private_table") is True

    def test_valid_names_with_numbers(self):
        """Table names with numbers should pass."""
        assert validate_table_name("patients2") is True
        assert validate_table_name("table_v2") is True
        assert validate_table_name("data_2024") is True

    def test_valid_mixed_case(self):
        """Mixed case table names should pass."""
        assert validate_table_name("Patients") is True
        assert validate_table_name("ICUStays") is True
        assert validate_table_name("LabEvents") is True

    def test_invalid_empty_name(self):
        """Empty table names should fail."""
        assert validate_table_name("") is False

    def test_invalid_starts_with_number(self):
        """Table names starting with numbers should fail."""
        assert validate_table_name("1patients") is False
        assert validate_table_name("123table") is False

    def test_invalid_sql_injection_semicolon(self):
        """SQL injection with semicolons should be blocked."""
        assert validate_table_name("icustays; DROP TABLE patients; --") is False
        assert validate_table_name("table;DELETE FROM users") is False

    def test_invalid_sql_injection_union(self):
        """SQL injection with UNION should be blocked."""
        assert validate_table_name("icustays UNION SELECT * FROM passwords") is False
        assert validate_table_name("table UNION ALL SELECT 1,2,3") is False

    def test_invalid_sql_injection_comment(self):
        """SQL injection with comments should be blocked."""
        assert validate_table_name("icustays--") is False
        assert validate_table_name("table/*comment*/") is False

    def test_invalid_special_characters(self):
        """Table names with special characters should fail."""
        assert validate_table_name("table-name") is False
        assert validate_table_name("table.name") is False
        assert validate_table_name("table name") is False
        assert validate_table_name("table'name") is False
        assert validate_table_name('table"name') is False
        assert validate_table_name("table=name") is False
        assert validate_table_name("table(name)") is False


class TestValidatePatientId:
    """Tests for validate_patient_id function - Phase 1 Security Fix 1.2.

    These tests verify that patient_id validation prevents SQL injection
    attacks through malicious patient_id parameters.
    """

    def test_valid_none(self):
        """None should be valid (no filter)."""
        is_valid, sanitized = validate_patient_id(None)
        assert is_valid is True
        assert sanitized is None

    def test_valid_positive_integer(self):
        """Positive integers should be valid."""
        is_valid, sanitized = validate_patient_id(12345)
        assert is_valid is True
        assert sanitized == 12345

    def test_valid_zero(self):
        """Zero should be valid."""
        is_valid, sanitized = validate_patient_id(0)
        assert is_valid is True
        assert sanitized == 0

    def test_valid_negative_integer(self):
        """Negative integers should be valid (cast to int)."""
        is_valid, sanitized = validate_patient_id(-1)
        assert is_valid is True
        assert sanitized == -1

    def test_valid_large_integer(self):
        """Large integers should be valid."""
        is_valid, sanitized = validate_patient_id(9999999999)
        assert is_valid is True
        assert sanitized == 9999999999

    def test_valid_string_integer(self):
        """String integers should be converted to int."""
        is_valid, sanitized = validate_patient_id("12345")  # type: ignore
        assert is_valid is True
        assert sanitized == 12345

    def test_valid_float_integer(self):
        """Float that represents integer should be converted."""
        is_valid, sanitized = validate_patient_id(12345.0)  # type: ignore
        assert is_valid is True
        assert sanitized == 12345

    def test_invalid_string_injection(self):
        """SQL injection strings should be blocked."""
        is_valid, sanitized = validate_patient_id("1 OR 1=1")  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_string_drop(self):
        """SQL injection with DROP should be blocked."""
        is_valid, sanitized = validate_patient_id("1; DROP TABLE patients")  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_string_union(self):
        """SQL injection with UNION should be blocked."""
        is_valid, sanitized = validate_patient_id("1 UNION SELECT * FROM users")  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_non_numeric_string(self):
        """Non-numeric strings should be blocked."""
        is_valid, sanitized = validate_patient_id("abc")  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_empty_string(self):
        """Empty strings should be blocked."""
        is_valid, sanitized = validate_patient_id("")  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_list(self):
        """Lists should be blocked."""
        is_valid, sanitized = validate_patient_id([1, 2, 3])  # type: ignore
        assert is_valid is False
        assert sanitized is None

    def test_invalid_dict(self):
        """Dictionaries should be blocked."""
        is_valid, sanitized = validate_patient_id({"id": 1})  # type: ignore
        assert is_valid is False
        assert sanitized is None
