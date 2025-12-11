"""
M4 MCP Server - MIMIC-IV + MCP + Models
Provides MCP tools for querying MIMIC-IV data via DuckDB (local) or BigQuery.
"""

import os
from pathlib import Path

import duckdb
import sqlparse
from fastmcp import FastMCP

from m4.auth import init_oauth2, require_oauth2
from m4.config import (
    detect_available_local_datasets,
    get_active_dataset,
    get_default_database_path,
    set_active_dataset,
)
from m4.core.datasets import DatasetRegistry
from m4.core.tools import ToolRegistry, ToolSelector, init_tools

# Create FastMCP server instance
mcp = FastMCP("m4")

# Initialize capability-based tool system (Phase 4)
init_tools()
_tool_selector = ToolSelector()

# Global variables for backend configuration
_backend = None
# Cache for BigQuery client to avoid re-initializing on every request
_bq_client_cache = {"client": None, "project_id": None}


def _get_active_dataset_def():
    """Get the currently active dataset definition."""
    # 1. Try currently active dataset from config/env
    active_ds_name = get_active_dataset()
    if active_ds_name:
        return DatasetRegistry.get(active_ds_name)

    # 2. Fallback for BigQuery: try to find a full definition
    if _backend == "bigquery":
        # Use mimic-iv-full as reference if available, else demo
        return DatasetRegistry.get("mimic-iv-full") or DatasetRegistry.get(
            "mimic-iv-demo"
        )

    # 3. Fallback for DuckDB: demo
    return DatasetRegistry.get("mimic-iv-demo")


def _get_db_path():
    """Get the current DuckDB path."""
    # 1. Env var overrides everything (static mode)
    env_path = os.getenv("M4_DB_PATH")
    if env_path:
        return env_path

    # 2. Dynamic resolution based on active dataset
    ds_def = _get_active_dataset_def()
    if ds_def:
        path = get_default_database_path(ds_def.name)
        return str(path) if path else None

    return None


def _get_bq_client():
    """Get or create a BigQuery client for the current project."""
    try:
        from google.cloud import bigquery
    except ImportError:
        raise ImportError(
            "BigQuery dependencies not found. Install with: pip install google-cloud-bigquery"
        )

    # Determine target project ID
    # Priority: Env Var > Dataset Config > Default
    env_project = os.getenv("M4_PROJECT_ID")
    ds_def = _get_active_dataset_def()
    ds_project = ds_def.bigquery_project_id if ds_def else None

    target_project_id = env_project or ds_project or "physionet-data"

    # Check cache
    if (
        _bq_client_cache["client"]
        and _bq_client_cache["project_id"] == target_project_id
    ):
        return _bq_client_cache["client"], target_project_id

    # Create new client
    try:
        client = bigquery.Client(project=target_project_id)
        _bq_client_cache["client"] = client
        _bq_client_cache["project_id"] = target_project_id
        return client, target_project_id
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize BigQuery client for project {target_project_id}: {e}"
        )


def _validate_limit(limit: int) -> bool:
    """Validate limit parameter to prevent resource exhaustion."""
    return isinstance(limit, int) and 0 < limit <= 1000


def _is_safe_query(sql_query: str, internal_tool: bool = False) -> tuple[bool, str]:
    """Secure SQL validation - blocks injection attacks, allows legitimate queries."""
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

            # Block common injection patterns that are rarely used in legitimate analytics
            injection_patterns = [
                # Classic SQL injection patterns
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

            # Context-aware protection: Block suspicious table/column names not in medical databases
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


def _init_backend():
    """Initialize the backend based on environment variables."""
    global _backend

    # Initialize OAuth2 authentication
    init_oauth2()

    _backend = os.getenv("M4_BACKEND", "duckdb")

    if _backend not in ["duckdb", "bigquery"]:
        raise ValueError(
            f"Unsupported backend: {_backend}. Supported backends: duckdb, bigquery"
        )


_init_backend()


def _get_backend_info() -> str:
    """Get current backend information for display in responses."""
    ds_def = _get_active_dataset_def()
    ds_name = ds_def.name if ds_def else "unknown"

    if _backend == "duckdb":
        db_path = _get_db_path()
        return f"🔧 **Current Backend:** DuckDB (local database)\n📦 **Active Dataset:** {ds_name}\n📁 **Database Path:** {db_path}\n"
    else:
        # Resolve project ID dynamically for display
        _, project_id = _get_bq_client()
        return f"🔧 **Current Backend:** BigQuery (cloud database)\n📦 **Active Dataset:** {ds_name}\n☁️ **Project ID:** {project_id}\n"


def _check_tool_compatibility(tool_name: str) -> tuple[bool, str]:
    """Check if a tool is compatible with the current dataset.

    Uses the ToolSelector to perform capability-based filtering.
    This replaces manual tag-based checks like `if "mimic" not in ds_def.tags`.

    Args:
        tool_name: Name of the tool to check

    Returns:
        Tuple of (is_compatible, error_message).
        If compatible, error_message is empty.
        If not compatible, error_message explains why and suggests alternatives.
    """
    ds_def = _get_active_dataset_def()
    if not ds_def:
        return (
            False,
            "❌ **Error:** No active dataset. Use `list_datasets()` to see available datasets.",
        )

    tool = ToolRegistry.get(tool_name)
    if not tool:
        return True, ""  # Unknown tool - let it proceed (backward compat)

    if not _tool_selector.is_tool_available(tool_name, ds_def):
        # Build helpful error message based on missing capabilities
        missing_modalities = tool.required_modalities - ds_def.modalities
        missing_capabilities = tool.required_capabilities - ds_def.capabilities

        msg_parts = [
            f"❌ **Error:** Tool `{tool_name}` is not available for dataset '{ds_def.name}'."
        ]

        if missing_modalities:
            modality_names = ", ".join(m.name for m in missing_modalities)
            msg_parts.append(f"\n📋 **Missing data types:** {modality_names}")

        if missing_capabilities:
            cap_names = ", ".join(c.name for c in missing_capabilities)
            msg_parts.append(f"\n⚙️ **Missing capabilities:** {cap_names}")

        # Suggest compatible tools
        compatible_tools = _tool_selector.tools_for_dataset(ds_def)
        if compatible_tools:
            tool_names = ", ".join(f"`{t.name}`" for t in compatible_tools[:5])
            msg_parts.append(
                f"\n\n💡 **Available tools for this dataset:** {tool_names}"
            )

        msg_parts.append(
            "\n\n🔄 Use `list_datasets()` to see other datasets that may support this operation."
        )

        return False, "".join(msg_parts)

    return True, ""


# ==========================================
# INTERNAL QUERY EXECUTION FUNCTIONS
# ==========================================
# These functions perform the actual database operations
# and are called by the MCP tools. This prevents MCP tools
# from calling other MCP tools, which violates the MCP protocol.


def _execute_duckdb_query(sql_query: str) -> str:
    """Execute DuckDB query - internal function."""
    db_path = _get_db_path()
    if not db_path or not Path(db_path).exists():
        return "❌ Error: Database file not found. Please initialize a dataset using 'm4 init'."

    try:
        conn = duckdb.connect(db_path)
        try:
            df = conn.execute(sql_query).df()
            if df.empty:
                return "No results found"
            if len(df) > 50:
                out = (
                    df.head(50).to_string(index=False)
                    + f"\n... ({len(df)} total rows, showing first 50)"
                )
            else:
                out = df.to_string(index=False)
            return out
        finally:
            conn.close()
    except Exception as e:
        # Re-raise the exception so the calling function can handle it with enhanced guidance
        raise e


def _execute_bigquery_query(sql_query: str) -> str:
    """Execute BigQuery query - internal function."""
    try:
        from google.cloud import bigquery

        client, _ = _get_bq_client()

        job_config = bigquery.QueryJobConfig()
        query_job = client.query(sql_query, job_config=job_config)
        df = query_job.to_dataframe()

        if df.empty:
            return "No results found"

        # Limit output size
        if len(df) > 50:
            result = df.head(50).to_string(index=False)
            result += f"\n... ({len(df)} total rows, showing first 50)"
        else:
            result = df.to_string(index=False)

        return result

    except Exception as e:
        # Re-raise the exception so the calling function can handle it with enhanced guidance
        raise e


def _execute_query_internal(sql_query: str) -> str:
    """Internal query execution function that handles backend routing."""
    # Security check
    is_safe, message = _is_safe_query(sql_query)
    if not is_safe:
        if "describe" in sql_query.lower() or "show" in sql_query.lower():
            return f"""❌ **Security Error:** {message}

        🔍 **For table structure:** Use `get_table_info('table_name')` instead of DESCRIBE
        📋 **Why this is better:** Shows columns, types, AND sample data to understand the actual data

        💡 **Recommended workflow:**
        1. `get_database_schema()` ← See available tables
        2. `get_table_info('table_name')` ← Explore structure
        3. `execute_mimic_query('SELECT ...')` ← Run your analysis"""

        return f"❌ **Security Error:** {message}\n\n💡 **Tip:** Only SELECT statements are allowed for data analysis."

    try:
        if _backend == "duckdb":
            return _execute_duckdb_query(sql_query)
        else:  # bigquery
            return _execute_bigquery_query(sql_query)
    except Exception as e:
        error_msg = str(e).lower()

        # Provide specific, actionable error guidance
        suggestions = []

        if "no such table" in error_msg or "table not found" in error_msg:
            suggestions.append(
                "🔍 **Table name issue:** Use `get_database_schema()` to see exact table names"
            )
            suggestions.append(
                f"📋 **Backend-specific naming:** {_backend} has specific table naming conventions"
            )
            suggestions.append(
                "💡 **Quick fix:** Check if the table name matches exactly (case-sensitive)"
            )

        if "no such column" in error_msg or "column not found" in error_msg:
            suggestions.append(
                "🔍 **Column name issue:** Use `get_table_info('table_name')` to see available columns"
            )
            suggestions.append(
                "📝 **Common issue:** Column might be named differently (e.g., 'anchor_age' not 'age')"
            )
            suggestions.append(
                "👀 **Check sample data:** `get_table_info()` shows actual column names and sample values"
            )

        if "syntax error" in error_msg:
            suggestions.append(
                "📝 **SQL syntax issue:** Check quotes, commas, and parentheses"
            )
            suggestions.append(
                f"🎯 **Backend syntax:** Verify your SQL works with {_backend}"
            )
            suggestions.append(
                "💭 **Try simpler:** Start with `SELECT * FROM table_name LIMIT 5`"
            )

        if "describe" in error_msg.lower() or "show" in error_msg.lower():
            suggestions.append(
                "🔍 **Schema exploration:** Use `get_table_info('table_name')` instead of DESCRIBE"
            )
            suggestions.append(
                "📋 **Better approach:** `get_table_info()` shows columns AND sample data"
            )

        if not suggestions:
            suggestions.append(
                "🔍 **Start exploration:** Use `get_database_schema()` to see available tables"
            )
            suggestions.append(
                "📋 **Check structure:** Use `get_table_info('table_name')` to understand the data"
            )

        suggestion_text = "\n".join(f"   {s}" for s in suggestions)

        return f"""❌ **Query Failed:** {e}

🛠️ **How to fix this:**
{suggestion_text}

🎯 **Quick Recovery Steps:**
1. `get_database_schema()` ← See what tables exist
2. `get_table_info('your_table')` ← Check exact column names
3. Retry your query with correct names

📚 **Current Backend:** {_backend} - table names and syntax are backend-specific"""


# ==========================================
# MCP TOOLS - PUBLIC API
# ==========================================
# These are the tools exposed via MCP protocol.
# They should NEVER call other MCP tools - only internal functions.


@mcp.tool()
def list_datasets() -> str:
    """List all available datasets and their status.

    Returns:
        A formatted string listing available datasets, indicating which one is active,
        and showing availability of local database and BigQuery support.
    """
    active = get_active_dataset() or "(unset)"
    availability = detect_available_local_datasets()

    if not availability:
        return "No datasets detected."

    output = [f"Active dataset: {active}\n"]
    output.append(
        f"Backend: {'local (DuckDB)' if _backend == 'duckdb' else 'cloud (BigQuery)'}\n"
    )

    for label, info in availability.items():
        is_active = " (Active)" if label == active else ""
        output.append(f"=== {label.upper()}{is_active} ===")

        parquet_icon = "✅" if info["parquet_present"] else "❌"
        db_icon = "✅" if info["db_present"] else "❌"

        output.append(f"  Local Parquet: {parquet_icon}")
        output.append(f"  Local Database: {db_icon}")

        # BigQuery status
        ds_def = DatasetRegistry.get(label)
        if ds_def:
            bq_status = "✅" if ds_def.bigquery_dataset_ids else "❌"
            output.append(f"  BigQuery Support: {bq_status}")
        output.append("")

    return "\n".join(output)


@mcp.tool()
def set_dataset(dataset_name: str) -> str:
    """Switch the active dataset.

    Args:
        dataset_name: The name of the dataset to switch to (e.g., 'mimic-iv-demo', 'mimic-iv-full').

    Returns:
        Confirmation message or error if dataset not found.
    """
    dataset_name = dataset_name.lower()
    availability = detect_available_local_datasets()

    if dataset_name not in availability:
        supported = ", ".join(availability.keys())
        return (
            f"❌ Error: Dataset '{dataset_name}' not found. "
            f"Supported datasets: {supported}"
        )

    set_active_dataset(dataset_name)

    # Get details about the new dataset to provide context
    info = availability[dataset_name]
    status_msg = f"✅ Active dataset switched to '{dataset_name}'."

    if not info["db_present"] and _backend == "duckdb":
        status_msg += (
            "\n⚠️ Note: Local database not found. "
            "You may need to run initialization if using DuckDB."
        )

    ds_def = DatasetRegistry.get(dataset_name)
    if ds_def and not ds_def.bigquery_dataset_ids and _backend == "bigquery":
        status_msg += "\n⚠️ Warning: This dataset is not configured for BigQuery."

    return status_msg


@mcp.tool()
@require_oauth2
def get_database_schema() -> str:
    """🔍 Discover what data is available in the MIMIC-IV database.

    **When to use:** Start here when you need to understand what tables exist, or when someone asks about data that might be in multiple tables.

    **What this does:** Shows all available tables so you can identify which ones contain the data you need.

    **Next steps after using this:**
    - If you see relevant tables, use `get_table_info(table_name)` to explore their structure
    - Common tables: `patients` (demographics), `admissions` (hospital stays), `icustays` (ICU data), `labevents` (lab results)

    Returns:
        List of all available tables in the database with current backend info
    """
    if _backend == "duckdb":
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY table_name
        """
        result = _execute_query_internal(query)
        return f"{_get_backend_info()}\n📋 **Available Tables:**\n{result}"

    elif _backend == "bigquery":
        # Dynamic schema discovery based on active dataset definition
        ds_def = _get_active_dataset_def()
        if not ds_def or not ds_def.bigquery_dataset_ids:
            return f"{_get_backend_info()}❌ **Error:** No BigQuery datasets configured for the active dataset."

        project_id = ds_def.bigquery_project_id or "physionet-data"
        queries = []

        for dataset_id in ds_def.bigquery_dataset_ids:
            queries.append(f"""
             SELECT CONCAT('`{project_id}.{dataset_id}.', table_name, '`') as query_ready_table_name
             FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
             """)

        if not queries:
            return (
                f"{_get_backend_info()}❌ **Error:** No BigQuery datasets configured."
            )

        query = " UNION ALL ".join(queries) + " ORDER BY query_ready_table_name"

        result = _execute_query_internal(query)
        return f"{_get_backend_info()}\n📋 **Available Tables (query-ready names):**\n{result}\n\n💡 **Copy-paste ready:** These table names can be used directly in your SQL queries!"


@mcp.tool()
@require_oauth2
def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """📋 Explore a specific table's structure and see sample data.

    **When to use:** After you know which table you need (from `get_database_schema()`), use this to understand the columns and data format.

    **What this does:**
    - Shows column names, types, and constraints
    - Displays sample rows so you understand the actual data format
    - Helps you write accurate SQL queries

    **Pro tip:** Always look at sample data! It shows you the actual values, date formats, and data patterns.

    Args:
        table_name: Exact table name from the schema (case-sensitive). Can be simple name or fully qualified BigQuery name.
        show_sample: Whether to include sample rows (default: True, recommended)

    Returns:
        Complete table structure with sample data to help you write queries
    """
    backend_info = _get_backend_info()

    if _backend == "duckdb":
        # Get column information
        pragma_query = f"PRAGMA table_info('{table_name}')"
        try:
            result = _execute_duckdb_query(pragma_query)
            if "error" in result.lower():
                return f"{backend_info}❌ Table '{table_name}' not found. Use get_database_schema() to see available tables."

            info_result = f"{backend_info}📋 **Table:** {table_name}\n\n**Column Information:**\n{result}"

            if show_sample:
                sample_query = f"SELECT * FROM '{table_name}' LIMIT 3"
                sample_result = _execute_duckdb_query(sample_query)
                info_result += (
                    f"\n\n📊 **Sample Data (first 3 rows):**\n{sample_result}"
                )

            return info_result
        except Exception as e:
            return f"{backend_info}❌ Error examining table '{table_name}': {e}\n\n💡 Use get_database_schema() to see available tables."

    else:  # bigquery
        # Handle both simple names (patients) and fully qualified names (`physionet-data.mimiciv_3_1_hosp.patients`)
        # Detect qualified names by content: dots + project ID pattern or backticks
        is_qualified = "." in table_name

        if is_qualified:
            # Qualified name (format-agnostic: works with or without backticks)
            clean_name = table_name.strip("`")
            full_table_name = f"`{clean_name}`"
            parts = clean_name.split(".")

            # Validate BigQuery qualified name format: project.dataset.table
            if len(parts) != 3:
                error_msg = (
                    f"{backend_info}❌ **Invalid qualified table name:** `{table_name}`\n\n"
                    "**Expected format:** `project.dataset.table`\n"
                    "**Example:** `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`\n"
                )
                return error_msg

            simple_table_name = parts[2]  # table name
            dataset_ref = f"{parts[0]}.{parts[1]}"  # project.dataset
        else:
            # Simple name - try to find it in configured datasets
            simple_table_name = table_name
            full_table_name = None
            dataset_ref = None

        # If we have a fully qualified name, try that first
        if full_table_name:
            try:
                # Get column information using the dataset from the full name
                dataset_parts = dataset_ref.split(".")
                if len(dataset_parts) >= 2:
                    project_dataset = f"`{dataset_parts[0]}.{dataset_parts[1]}`"
                    info_query = f"""
                    SELECT column_name, data_type, is_nullable
                    FROM {project_dataset}.INFORMATION_SCHEMA.COLUMNS
                    WHERE table_name = '{simple_table_name}'
                    ORDER BY ordinal_position
                    """

                    info_result = _execute_bigquery_query(info_query)
                    if "No results found" not in info_result:
                        result = f"{backend_info}📋 **Table:** {full_table_name}\n\n**Column Information:**\n{info_result}"

                        if show_sample:
                            sample_query = f"SELECT * FROM {full_table_name} LIMIT 3"
                            sample_result = _execute_bigquery_query(sample_query)
                            result += f"\n\n📊 **Sample Data (first 3 rows):**\n{sample_result}"

                        return result
            except Exception:
                pass  # Fall through to try search approach if direct lookup fails (unlikely but safe)

        # Try configured datasets with simple name
        ds_def = _get_active_dataset_def()
        if ds_def and ds_def.bigquery_dataset_ids:
            project_id = ds_def.bigquery_project_id or "physionet-data"
            for dataset_id in ds_def.bigquery_dataset_ids:
                try:
                    full_table_name = f"`{project_id}.{dataset_id}.{simple_table_name}`"

                    # Get column information
                    info_query = f"""
                    SELECT column_name, data_type, is_nullable
                    FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS`
                    WHERE table_name = '{simple_table_name}'
                    ORDER BY ordinal_position
                    """

                    info_result = _execute_bigquery_query(info_query)
                    if "No results found" not in info_result:
                        result = f"{backend_info}📋 **Table:** {full_table_name}\n\n**Column Information:**\n{info_result}"

                        if show_sample:
                            sample_query = f"SELECT * FROM {full_table_name} LIMIT 3"
                            sample_result = _execute_bigquery_query(sample_query)
                            result += f"\n\n📊 **Sample Data (first 3 rows):**\n{sample_result}"

                        return result
                except Exception:
                    continue

        return f"{backend_info}❌ Table '{table_name}' not found in any dataset. Use get_database_schema() to see available tables."


@mcp.tool()
@require_oauth2
def execute_mimic_query(sql_query: str) -> str:
    """🚀 Execute SQL queries to analyze MIMIC-IV data.

    **💡 Pro tip:** For best results, explore the database structure first!

    **Recommended workflow (especially for smaller models):**
    1. **See available tables:** Use `get_database_schema()` to list all tables
    2. **Examine table structure:** Use `get_table_info('table_name')` to see columns and sample data
    3. **Write your SQL query:** Use exact table/column names from exploration

    **Why exploration helps:**
    - Table names vary between backends (SQLite vs BigQuery)
    - Column names may be unexpected (e.g., age might be 'anchor_age')
    - Sample data shows actual formats and constraints

    Args:
        sql_query: Your SQL SELECT query (must be SELECT only)

    Returns:
        Query results or helpful error messages with next steps
    """
    return _execute_query_internal(sql_query)


@mcp.tool()
@require_oauth2
def get_icu_stays(patient_id: int | None = None, limit: int = 10) -> str:
    """🏥 Get ICU stay information and length of stay data.

    **⚠️ Note:** This is a convenience function that assumes standard MIMIC-IV table structure.
    **For reliable queries:** Use `get_database_schema()` → `get_table_info()` → `execute_mimic_query()` workflow.

    **What you'll get:** Patient IDs, admission times, length of stay, and ICU details.

    Args:
        patient_id: Specific patient ID to query (optional)
        limit: Maximum number of records to return (default: 10)

    Returns:
        ICU stay data as formatted text or guidance if table not found
    """
    # Capability-based compatibility check (Phase 4)
    is_compatible, error_msg = _check_tool_compatibility("get_icu_stays")
    if not is_compatible:
        return error_msg

    ds_def = _get_active_dataset_def()
    # Security validation
    if not _validate_limit(limit):
        return "Error: Invalid limit. Must be a positive integer between 1 and 10000."

    # Try common ICU table names based on backend
    if _backend == "duckdb":
        icustays_table = "icu_icustays"
    else:  # bigquery
        # Try to find icustays in configured datasets
        project_id = (
            ds_def.bigquery_project_id or "physionet-data"
            if ds_def
            else "physionet-data"
        )
        found = False
        dataset_ids = ds_def.bigquery_dataset_ids if ds_def else []
        for ds in dataset_ids:
            if "icu" in ds:
                icustays_table = f"`{project_id}.{ds}.icustays`"
                found = True
                break
        if not found:
            # Fallback
            icustays_table = "`physionet-data.mimiciv_3_1_icu.icustays`"

    if patient_id:
        query = f"SELECT * FROM {icustays_table} WHERE subject_id = {patient_id}"
    else:
        query = f"SELECT * FROM {icustays_table} LIMIT {limit}"

    # Execute with error handling that suggests proper workflow
    result = _execute_query_internal(query)
    if "error" in result.lower() or "not found" in result.lower():
        return f"""❌ **Convenience function failed:** {result}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_mimic_query('your_sql')` ← Use exact names

This ensures compatibility across different MIMIC-IV setups."""

    return result


@mcp.tool()
@require_oauth2
def get_lab_results(
    patient_id: int | None = None, lab_item: str | None = None, limit: int = 20
) -> str:
    """🧪 Get laboratory test results quickly.

    **⚠️ Note:** This is a convenience function that assumes standard MIMIC-IV table structure.
    **For reliable queries:** Use `get_database_schema()` → `get_table_info()` → `execute_mimic_query()` workflow.

    **What you'll get:** Lab values, timestamps, patient IDs, and test details.

    Args:
        patient_id: Specific patient ID to query (optional)
        lab_item: Lab item to search for in the value field (optional)
        limit: Maximum number of records to return (default: 20)

    Returns:
        Lab results as formatted text or guidance if table not found
    """
    # Capability-based compatibility check (Phase 4)
    is_compatible, error_msg = _check_tool_compatibility("get_lab_results")
    if not is_compatible:
        return error_msg

    ds_def = _get_active_dataset_def()
    # Security validation
    if not _validate_limit(limit):
        return "Error: Invalid limit. Must be a positive integer between 1 and 10000."

    # Try common lab table names based on backend
    if _backend == "duckdb":
        labevents_table = "hosp_labevents"
    else:  # bigquery
        # Try to find labevents in configured datasets
        project_id = (
            ds_def.bigquery_project_id or "physionet-data"
            if ds_def
            else "physionet-data"
        )
        found = False
        dataset_ids = ds_def.bigquery_dataset_ids if ds_def else []
        for ds in dataset_ids:
            if "hosp" in ds:
                labevents_table = f"`{project_id}.{ds}.labevents`"
                found = True
                break
        if not found:
            # Fallback
            labevents_table = "`physionet-data.mimiciv_3_1_hosp.labevents`"

    # Build query conditions
    conditions = []
    if patient_id:
        conditions.append(f"subject_id = {patient_id}")
    if lab_item:
        # Escape single quotes for safety in LIKE clause
        escaped_lab_item = lab_item.replace("'", "''")
        conditions.append(f"value LIKE '%{escaped_lab_item}%'")

    base_query = f"SELECT * FROM {labevents_table}"
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += f" LIMIT {limit}"

    # Execute with error handling that suggests proper workflow
    result = _execute_query_internal(base_query)
    if "error" in result.lower() or "not found" in result.lower():
        return f"""❌ **Convenience function failed:** {result}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_mimic_query('your_sql')` ← Use exact names

This ensures compatibility across different MIMIC-IV setups."""

    return result


@mcp.tool()
@require_oauth2
def get_race_distribution(limit: int = 10) -> str:
    """📊 Get race distribution from hospital admissions.

    **⚠️ Note:** This is a convenience function that assumes standard MIMIC-IV table structure.
    **For reliable queries:** Use `get_database_schema()` → `get_table_info()` → `execute_mimic_query()` workflow.

    **What you'll get:** Count of patients by race category, ordered by frequency.

    Args:
        limit: Maximum number of race categories to return (default: 10)

    Returns:
        Race distribution as formatted text or guidance if table not found
    """
    # Capability-based compatibility check (Phase 4)
    is_compatible, error_msg = _check_tool_compatibility("get_race_distribution")
    if not is_compatible:
        return error_msg

    ds_def = _get_active_dataset_def()
    # Security validation
    if not _validate_limit(limit):
        return "Error: Invalid limit. Must be a positive integer between 1 and 10000."

    # Try common admissions table names based on backend
    if _backend == "duckdb":
        admissions_table = "hosp_admissions"
    else:  # bigquery
        # Try to find admissions in configured datasets
        project_id = (
            ds_def.bigquery_project_id or "physionet-data"
            if ds_def
            else "physionet-data"
        )
        found = False
        dataset_ids = ds_def.bigquery_dataset_ids if ds_def else []
        for ds in dataset_ids:
            if "hosp" in ds:
                admissions_table = f"`{project_id}.{ds}.admissions`"
                found = True
                break
        if not found:
            # Fallback
            admissions_table = "`physionet-data.mimiciv_3_1_hosp.admissions`"

    query = f"SELECT race, COUNT(*) as count FROM {admissions_table} GROUP BY race ORDER BY count DESC LIMIT {limit}"

    # Execute with error handling that suggests proper workflow
    result = _execute_query_internal(query)
    if "error" in result.lower() or "not found" in result.lower():
        return f"""❌ **Convenience function failed:** {result}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_mimic_query('your_sql')` ← Use exact names

This ensures compatibility across different MIMIC-IV setups."""

    return result


# Internal wrapper functions for capability-based tools (Phase 2)
# These delegate to the existing MCP tool functions, enabling the new
# tool classes to reuse existing logic without duplication.


def _list_datasets_internal() -> str:
    """Internal wrapper for list_datasets tool."""
    return list_datasets()


def _set_dataset_internal(dataset_name: str) -> str:
    """Internal wrapper for set_dataset tool."""
    return set_dataset(dataset_name)


def _get_database_schema_internal() -> str:
    """Internal wrapper for get_database_schema tool."""
    return get_database_schema()


def _get_table_info_internal(table_name: str, show_sample: bool = True) -> str:
    """Internal wrapper for get_table_info tool."""
    return get_table_info(table_name, show_sample)


def _get_icu_stays_internal(patient_id: int | None = None, limit: int = 10) -> str:
    """Internal wrapper for get_icu_stays tool."""
    return get_icu_stays(patient_id, limit)


def _get_lab_results_internal(patient_id: int | None = None, limit: int = 20) -> str:
    """Internal wrapper for get_lab_results tool."""
    return get_lab_results(patient_id, None, limit)


def _get_race_distribution_internal(limit: int = 10) -> str:
    """Internal wrapper for get_race_distribution tool."""
    return get_race_distribution(limit)


def main():
    """Main entry point for MCP server."""
    # Run the FastMCP server
    mcp.run()


if __name__ == "__main__":
    main()
