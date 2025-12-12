"""SQL validation and parameter sanitization utilities.

This module provides security functions for validating SQL queries
and sanitizing user input before execution. These are used by tool
classes to prevent SQL injection and other attacks.
"""

import re

import sqlparse


def validate_table_name(name: str) -> bool:
    """Validate table name to prevent SQL injection.

    Table names must start with a letter or underscore, followed by
    alphanumeric characters or underscores only. This prevents SQL
    injection through malicious table names like:
    - "icustays; DROP TABLE patients; --"
    - "icustays UNION SELECT * FROM passwords"

    Args:
        name: The table name to validate

    Returns:
        True if the table name is safe, False otherwise
    """
    if not name:
        return False
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))


def validate_patient_id(patient_id: int | None) -> tuple[bool, int | None]:
    """Validate and sanitize patient_id to prevent SQL injection.

    This function ensures the patient_id is a valid integer, preventing
    injection attacks through string-like objects or malformed values.

    Args:
        patient_id: The patient ID to validate (can be int or None)

    Returns:
        Tuple of (is_valid, sanitized_value)
        - is_valid: True if patient_id is None or a valid integer
        - sanitized_value: The patient_id cast to int, or None
    """
    if patient_id is None:
        return True, None

    try:
        # Explicitly cast to int to prevent injection via string-like objects
        sanitized = int(patient_id)
        return True, sanitized
    except (ValueError, TypeError):
        return False, None


def validate_limit(limit: int, max_limit: int = 1000) -> bool:
    """Validate limit parameter to prevent resource exhaustion.

    Args:
        limit: The limit value to validate
        max_limit: Maximum allowed limit (default: 1000)

    Returns:
        True if limit is valid, False otherwise
    """
    return isinstance(limit, int) and 0 < limit <= max_limit


def validate_lab_item(lab_item: str | None) -> tuple[bool, str | None, bool]:
    """Validate and sanitize lab_item parameter for safe SQL queries.

    Lab items can be either:
    - An integer itemid (e.g., "50912" for creatinine)
    - A text label pattern (e.g., "glucose" to search for glucose-related tests)

    The function sanitizes string input to prevent SQL injection while
    preserving useful search functionality.

    Args:
        lab_item: The lab item to search for (itemid or label pattern)

    Returns:
        Tuple of (is_valid, sanitized_value, is_numeric)
        - is_valid: True if lab_item is None or valid
        - sanitized_value: The sanitized lab_item for use in queries
        - is_numeric: True if the lab_item is a numeric itemid
    """
    if lab_item is None:
        return True, None, False

    if not isinstance(lab_item, str):
        return False, None, False

    lab_item = lab_item.strip()
    if not lab_item:
        return True, None, False

    # Check if it's a numeric itemid
    try:
        itemid = int(lab_item)
        return True, str(itemid), True
    except ValueError:
        pass

    # Sanitize string for safe LIKE query
    # Allow only alphanumeric, spaces, hyphens, and common punctuation
    # This prevents SQL injection while allowing reasonable lab test searches
    if not re.match(r"^[a-zA-Z0-9\s\-_,.'()]+$", lab_item):
        return False, None, False

    # Limit length to prevent abuse
    if len(lab_item) > 100:
        return False, None, False

    # Escape SQL LIKE special characters (% and _) to treat them as literals
    # Then wrap with % for substring matching
    sanitized = lab_item.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    return True, sanitized, False


def is_safe_query(sql_query: str) -> tuple[bool, str]:
    """Validate SQL query for injection attacks and dangerous operations.

    This function performs comprehensive security validation:
    1. Blocks multiple statements (main injection vector)
    2. Allows only SELECT and PRAGMA queries
    3. Blocks dangerous write operations within SELECT
    4. Detects common injection patterns
    5. Blocks suspicious table/column names

    Args:
        sql_query: The SQL query string to validate

    Returns:
        Tuple of (is_safe, message). If safe, message is "Safe" or similar.
        If not safe, message explains why.

    Example:
        is_safe, msg = is_safe_query("SELECT * FROM patients LIMIT 10")
        if not is_safe:
            raise ValueError(f"Unsafe query: {msg}")
    """
    try:
        if not sql_query or not sql_query.strip():
            return False, "Empty query"

        # Parse SQL to validate structure
        parsed = sqlparse.parse(sql_query.strip())
        if not parsed:
            return False, "Invalid SQL syntax"

        # Block multiple statements (main injection vector)
        if len(parsed) > 1:
            return False, "Multiple statements not allowed"

        statement = parsed[0]
        statement_type = statement.get_type()

        # Allow SELECT and PRAGMA (PRAGMA is needed for schema exploration)
        if statement_type not in (
            "SELECT",
            "UNKNOWN",
        ):  # PRAGMA shows as UNKNOWN in sqlparse
            return False, "Only SELECT and PRAGMA queries allowed"

        # Check if it's a PRAGMA statement (these are safe for schema exploration)
        sql_upper = sql_query.strip().upper()
        if sql_upper.startswith("PRAGMA"):
            return True, "Safe PRAGMA statement"

        # For SELECT statements, block dangerous injection patterns
        if statement_type == "SELECT":
            # Block dangerous write operations within SELECT
            dangerous_keywords = {
                "INSERT",
                "UPDATE",
                "DELETE",
                "DROP",
                "CREATE",
                "ALTER",
                "TRUNCATE",
                "REPLACE",
                "MERGE",
                "EXEC",
                "EXECUTE",
            }

            for keyword in dangerous_keywords:
                if f" {keyword} " in f" {sql_upper} ":
                    return False, f"Write operation not allowed: {keyword}"

            # Block common injection patterns using regex for flexible matching
            # Use \s* to handle variations with spaces (e.g., "1 = 1" vs "1=1")
            injection_regex_patterns = [
                (r"\b\d+\s*=\s*\d+\b", "Classic injection pattern (tautology)"),
                (r"\bOR\s+\d+\s*=\s*\d+", "Boolean injection pattern"),
                (r"\bAND\s+\d+\s*=\s*\d+", "Boolean injection pattern"),
                (r"\bOR\s+['\"].*['\"]\s*=\s*['\"]", "String injection pattern"),
                (r"\bAND\s+['\"].*['\"]\s*=\s*['\"]", "String injection pattern"),
                (r"\bWAITFOR\b", "Time-based injection"),
                (r"\bSLEEP\s*\(", "Time-based injection"),
                (r"\bBENCHMARK\s*\(", "Time-based injection"),
                (r"\bLOAD_FILE\s*\(", "File access injection"),
                (r"\bINTO\s+OUTFILE\b", "File write injection"),
                (r"\bINTO\s+DUMPFILE\b", "File write injection"),
            ]

            for pattern, description in injection_regex_patterns:
                if re.search(pattern, sql_upper, re.IGNORECASE):
                    return False, f"Injection pattern detected: {description}"

            # Block suspicious identifiers not found in medical databases
            # Use word boundary matching to avoid false positives on legitimate
            # column names like "PRIMARY_KEY", "FOREIGN_KEY", "SESSION_ID" etc.
            suspicious_names = [
                "PASSWORD",
                "ADMIN",
                "LOGIN",
                "AUTH",
                "TOKEN",
                "CREDENTIAL",
                "SECRET",
                "HASH",
                "SALT",
                "COOKIE",
            ]

            for name in suspicious_names:
                # Use word boundary regex to match standalone words only
                # This allows "PRIMARY_KEY" but blocks standalone "PASSWORD"
                if re.search(rf"\b{name}\b", sql_upper):
                    return (
                        False,
                        f"Suspicious identifier detected: {name} (not medical data)",
                    )

        return True, "Safe"

    except Exception as e:
        return False, f"Validation error: {e}"


def format_error_with_guidance(
    error: str,
    tool_type: str = "query",
) -> str:
    """Format an error message with helpful guidance for the user.

    Args:
        error: The error message
        tool_type: Type of tool that failed (query, schema, etc.)

    Returns:
        Formatted error message with suggestions
    """
    error_lower = error.lower()
    suggestions = []

    if "no such table" in error_lower or "table not found" in error_lower:
        suggestions.append("Use `get_database_schema()` to see exact table names")
        suggestions.append("Check if the table name matches exactly (case-sensitive)")

    if "no such column" in error_lower or "column not found" in error_lower:
        suggestions.append(
            "Use `get_table_info('table_name')` to see available columns"
        )
        suggestions.append(
            "Column might be named differently (e.g., 'anchor_age' not 'age')"
        )

    if "syntax error" in error_lower:
        suggestions.append("Check quotes, commas, and parentheses")
        suggestions.append("Try simpler: `SELECT * FROM table_name LIMIT 5`")

    if not suggestions:
        suggestions.append("Use `get_database_schema()` to see available tables")
        suggestions.append("Use `get_table_info('table_name')` to understand the data")

    suggestion_text = "\n".join(f"  - {s}" for s in suggestions)

    return f"""Error: {error}

How to fix:
{suggestion_text}

Recovery steps:
1. `get_database_schema()` - See what tables exist
2. `get_table_info('your_table')` - Check exact column names
3. Retry your query with correct names"""
