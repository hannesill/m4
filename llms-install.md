# M4 MCP Server - Installation Guide for AI Agents

This guide helps AI agents like Cline install and configure the M4 MCP server.

## Installation Method

Use `uvx` for zero-installation setup:

```bash
uvx m4-infra
```

## Backend Configuration

M4 supports two backends. Choose one:

### Option 1: DuckDB (Demo Database - Recommended for Testing)

**MCP Configuration:**
```json
{
  "mcpServers": {
    "m4": {
      "command": "uvx",
      "args": ["m4-infra"],
      "env": {
        "M4_BACKEND": "duckdb"
      }
    }
  }
}
```

**Features:**
- No setup required
- Demo database (100 patients, 275 admissions) downloads automatically
- Perfect for testing and development

### Option 2: BigQuery (Full MIMIC-IV Dataset)

**Prerequisites:**
1. User must have Google Cloud credentials configured
2. User must have access to MIMIC-IV on BigQuery (requires PhysioNet credentialing)

**MCP Configuration:**
```json
{
  "mcpServers": {
    "m4": {
      "command": "uvx",
      "args": ["m4-infra"],
      "env": {
        "M4_BACKEND": "bigquery",
        "M4_PROJECT_ID": "user-project-id"
      }
    }
  }
}
```

**Setup Steps:**
1. Install Google Cloud SDK: `brew install google-cloud-sdk` (macOS)
2. Authenticate: `gcloud auth application-default login`
3. Replace `user-project-id` with the user's actual GCP project ID

## Verification

After configuration, test by asking:
- "What tools do you have for MIMIC-IV data?"
- "Show me patient demographics from the ICU"

## Troubleshooting

**If SQLite backend fails:**
- The demo database downloads automatically on first query
- No manual `m4 init` needed

**If BigQuery backend fails:**
- Verify GCP authentication: `gcloud auth list`
- Confirm PhysioNet access to MIMIC-IV dataset
- Check project ID is correct

## Available Tools

- `get_database_schema` - List available tables
- `get_table_info` - Get column info and sample data
- `execute_query` - Execute SQL queries
- `get_icu_stays` - ICU stay information
- `get_lab_results` - Laboratory test results
- `get_race_distribution` - Patient demographics

## Additional Resources

- Full documentation: https://github.com/rafiattrach/m4
- Video tutorials: https://rafiattrach.github.io/m4/
