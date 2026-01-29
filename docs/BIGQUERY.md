# BigQuery Setup

Use Google Cloud BigQuery to access full clinical datasets without downloading files locally.

## Prerequisites

1. **Google Cloud account** with BigQuery access
2. **PhysioNet credentialed access** for MIMIC-IV or eICU ([apply here](https://physionet.org/)). Scroll to the bottom of the page and request access to the BigQuery dataset.
3. **gcloud CLI** installed ([installation guide](https://cloud.google.com/sdk/docs/install))

## Setup

### 1. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

This opens a browser to complete authentication.

### 2. Switch to BigQuery backend

```bash
m4 backend bigquery
```

### 3. Configure your MCP client

**Claude Desktop:**
```bash
m4 config claude --backend bigquery --project-id YOUR_PROJECT_ID
```

**Other clients:**
```bash
m4 config --backend bigquery --project-id YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` with your own billing project for BigQuery usage, not the PhysioNet dataset project. The variable is mandatory to ensure billing is correctly attributed.

### 4. Set the dataset

```bash
m4 use mimic-iv    # or eicu
```

### 5. Restart your MCP client

The AI client will now query BigQuery directly.

## BigQuery Dataset IDs

M4 uses these PhysioNet BigQuery datasets:

| Dataset | BigQuery Project | Dataset IDs |
|---------|-----------------|-------------|
| mimic-iv | `physionet-data` | `mimiciv_3_1_hosp`, `mimiciv_3_1_icu` |
| mimic-iv-note | `physionet-data` | `mimiciv_note` |
| eicu | `physionet-data` | `eicu_crd` |

## Derived Tables on BigQuery

BigQuery users already have access to ~63 pre-computed derived concept tables (SOFA scores, sepsis cohorts, KDIGO AKI staging, medications, etc.) via `physionet-data.mimiciv_derived`. These tables are maintained by PhysioNet and are the same concepts that local DuckDB users materialize with `m4 init-derived mimic-iv`.

You do **not** need to run `m4 init-derived` when using BigQuery -- the tables are already available. Query them directly:

```sql
SELECT * FROM mimiciv_derived.sofa LIMIT 10
```

The `mimiciv_derived` schema is accessible alongside the standard `mimiciv_hosp` and `mimiciv_icu` schemas.

## Environment Variables

You can also override the backend via environment variables (these take priority over `m4 backend`):

```bash
export M4_BACKEND=bigquery
export M4_PROJECT_ID=your-project-id
```

## Cost Considerations

BigQuery charges based on data scanned. Tips to minimize costs:

- Use `LIMIT` clauses in queries
- Query specific columns instead of `SELECT *`
- Use the `limit` parameter in `execute_query` (default: 100 rows)

## Troubleshooting

**"Access Denied" error:**
- Ensure you've completed PhysioNet credentialing for the dataset
- Verify your Google account is linked to PhysioNet
- Re-run `gcloud auth application-default login`

**"Project not found" error:**
- Check the project ID is correct
- Ensure BigQuery API is enabled in your project

**Slow queries:**
- BigQuery has network latency; consider local DuckDB for development
- Use smaller `LIMIT` values while exploring
