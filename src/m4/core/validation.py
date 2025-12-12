"""SQL validation and parameter sanitization utilities.

This module provides security functions for validating SQL queries
and sanitizing user input before execution. These are used by tool
classes to prevent SQL injection and other attacks.
"""

import sqlparse


def validate_limit(limit: int, max_limit: int = 1000) -> bool:
    """Validate limit parameter to prevent resource exhaustion.

    Args:
        limit: The limit value to validate
        max_limit: Maximum allowed limit (default: 1000)

    Returns:
        True if limit is valid, False otherwise
    """
    return isinstance(limit, int) and 0 < limit <= max_limit


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

            # Block common injection patterns
            injection_patterns = [
                ("1=1", "Classic injection pattern"),
                ("OR 1=1", "Boolean injection pattern"),
                ("AND 1=1", "Boolean injection pattern"),
                ("OR '1'='1'", "String injection pattern"),
                ("AND '1'='1'", "String injection pattern"),
                ("WAITFOR", "Time-based injection"),
                ("SLEEP(", "Time-based injection"),
                ("BENCHMARK(", "Time-based injection"),
                ("LOAD_FILE(", "File access injection"),
                ("INTO OUTFILE", "File write injection"),
                ("INTO DUMPFILE", "File write injection"),
            ]

            for pattern, description in injection_patterns:
                if pattern in sql_upper:
                    return False, f"Injection pattern detected: {description}"

            # Block suspicious identifiers not found in medical databases
            suspicious_names = [
                "PASSWORD",
                "ADMIN",
                "USER",
                "LOGIN",
                "AUTH",
                "TOKEN",
                "CREDENTIAL",
                "SECRET",
                "KEY",
                "HASH",
                "SALT",
                "SESSION",
                "COOKIE",
            ]

            for name in suspicious_names:
                if name in sql_upper:
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
        suggestions.append(
            "Use `get_database_schema()` to see exact table names"
        )
        suggestions.append(
            "Check if the table name matches exactly (case-sensitive)"
        )

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
        suggestions.append(
            "Use `get_table_info('table_name')` to understand the data"
        )

    suggestion_text = "\n".join(f"  - {s}" for s in suggestions)

    return f"""Error: {error}

How to fix:
{suggestion_text}

Recovery steps:
1. `get_database_schema()` - See what tables exist
2. `get_table_info('your_table')` - Check exact column names
3. Retry your query with correct names"""
