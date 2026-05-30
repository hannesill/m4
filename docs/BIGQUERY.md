# BigQuery Setup

Use Google Cloud BigQuery to access full clinical datasets without downloading files locally.

For local DuckDB workflows, use `m4 download DATASET` followed by
`m4 init DATASET`. For BigQuery workflows, skip local download entirely and
configure credentials/project billing as described below.

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

You can also emit agent-ready environment guidance without changing config:

```bash
m4 setup-agent --backend bigquery --project-id YOUR_PROJECT_ID --format dotenv
m4 doctor --json
```

### 4. Query with an explicit dataset

```bash
m4 status --dataset mimic-iv --backend bigquery
```

### 5. Restart your MCP client

The AI client will now query BigQuery directly.

## BigQuery Dataset IDs

M4 uses these PhysioNet BigQuery datasets:

| Dataset | BigQuery Project | Dataset IDs |
|---------|-----------------|-------------|
| mimic-iv | `physionet-data` | `mimiciv_3_1_hosp`, `mimiciv_3_1_icu` |
| mimic-iv-note | `physionet-data` | `mimiciv_note` |
| mimic-iv-ed | `physionet-data` | `mimiciv_ed` |
| eicu | `physionet-data` | `eicu_crd` |

## Derived Tables on BigQuery

BigQuery users already have access to pre-computed derived concept tables (SOFA scores, sepsis cohorts, KDIGO AKI staging, medications, etc.) via `physionet-data.mimiciv_derived`. These tables are maintained by PhysioNet and are the same concepts that local DuckDB users materialize with `m4 init-derived mimic-iv`.

You do **not** need to run `m4 init-derived` when using BigQuery -- the tables are already available. Query them directly:

```sql
SELECT * FROM mimiciv_derived.sofa LIMIT 10
```

The `mimiciv_derived` schema is accessible alongside the standard `mimiciv_hosp` and `mimiciv_icu` schemas.

## Environment Variables

You can also override the backend and project via environment variables. These
take priority over saved CLI configuration for the current process:

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
- Confirm `M4_PROJECT_ID` or `m4 config --project-id` refers to your billing project

**Slow queries:**
- BigQuery has network latency; consider local DuckDB for development
- Use smaller `LIMIT` values while exploring

**Local download layout problems:**
- Run `m4 download mimic-iv` or `m4 download eicu` to print dataset-specific
  recovery guidance and a resumable `wget` command.
- If files landed under `physionet.org/files/...`, move the dataset contents up
  to `m4_data/raw_files/DATASET` or rerun `wget` with the generated
  `--cut-dirs` and `-nH` flags.
