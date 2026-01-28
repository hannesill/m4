# M4 - Installation Guide for AI Agents

This guide helps AI agents like Cline, Cursor, and other MCP clients install and configure M4 for clinical data analysis.

## What is M4?

M4 is infrastructure for AI-assisted clinical research. It provides:
- **MCP Server**: Query clinical datasets (MIMIC-IV, eICU) via natural language
- **Python API**: Direct programmatic access returning pandas DataFrames
- **Clinical Skills**: 17 skills (1 API + 16 clinical research skills for severity scores, sepsis, AKI staging, and more)

## Installation

### Option 1: uvx (Zero-Installation)

```bash
uvx m4-infra
```

### Option 2: pip

```bash
pip install m4-infra
```

## MCP Configuration

### DuckDB Backend (Recommended for Getting Started)

```json
{
  "mcpServers": {
    "m4": {
      "command": "uvx",
      "args": ["m4-infra"]
    }
  }
}
```

**Features:**
- Demo database (100 patients) downloads automatically
- No setup required
- Perfect for testing and development

### BigQuery Backend (Full Datasets)

First, switch the active backend:
```bash
m4 backend bigquery
```

Then use this MCP configuration:
```json
{
  "mcpServers": {
    "m4": {
      "command": "uvx",
      "args": ["m4-infra"],
      "env": {
        "M4_PROJECT_ID": "user-project-id"
      }
    }
  }
}
```

**Prerequisites:**
1. Google Cloud credentials configured (`gcloud auth application-default login`)
2. PhysioNet credentialed access to MIMIC-IV or eICU

## Available MCP Tools

### Dataset Management
| Tool | Description |
|------|-------------|
| `list_datasets` | List available datasets and their status |
| `set_dataset` | Switch the active dataset |

### Tabular Data (MIMIC-IV, eICU)
| Tool | Description |
|------|-------------|
| `get_database_schema` | List all tables in the database |
| `get_table_info` | Get column details and sample data for a table |
| `execute_query` | Run SQL SELECT queries |

### Clinical Notes (MIMIC-IV-Note)
| Tool | Description |
|------|-------------|
| `search_notes` | Full-text search with snippets |
| `get_note` | Retrieve a single note by ID |
| `list_patient_notes` | List notes for a patient (metadata only) |

## Python API (Code Execution)

For AI agents with code execution capabilities (Claude Code, Cursor), M4 provides a Python API that returns native types instead of formatted strings:

```python
from m4 import set_dataset, execute_query, get_schema

set_dataset("mimic-iv")

# Returns pandas DataFrame
df = execute_query("""
    SELECT subject_id, gender, anchor_age
    FROM mimiciv_hosp.patients
    WHERE anchor_age > 65
""")

# Full pandas power: filter, aggregate, visualize
print(df.describe())
df.plot(kind='bar', x='gender', y='anchor_age')
```

**When to use the Python API:**
- Multi-step analyses where each query informs the next
- Statistical computations and survival analysis
- Large result sets that shouldn't flood context
- Building reproducible analysis notebooks

## Clinical Research Skills

M4 ships with 17 skills: 1 for the Python API (`m4-api`) and 16 clinical research skills extracted from MIT-LCP validated code:

### Severity Scores
- `sofa-score` - Sequential Organ Failure Assessment
- `apsiii-score` - APACHE III with mortality prediction
- `sapsii-score` - SAPS-II score
- `oasis-score` - Oxford Acute Severity of Illness Score
- `lods-score` - Logistic Organ Dysfunction Score
- `sirs-criteria` - Systemic Inflammatory Response Syndrome

### Sepsis and Infection
- `sepsis-3-cohort` - Sepsis-3 identification (SOFA >= 2 + infection)
- `suspicion-of-infection` - Suspected infection events

### Organ Failure
- `kdigo-aki-staging` - KDIGO AKI staging (creatinine + urine output)

### Medications
- `vasopressor-equivalents` - Norepinephrine-equivalent dose

### Laboratory
- `baseline-creatinine` - Baseline creatinine estimation
- `gcs-calculation` - Glasgow Coma Scale extraction

### Cohort Definitions
- `first-icu-stay` - First ICU stay selection

### Data Quality
- `mimic-table-relationships` - Table relationships and join patterns
- `mimic-eicu-mapping` - Cross-database concept mapping
- `clinical-research-pitfalls` - Common methodological mistakes

Install skills for Claude Code:
```bash
m4 skills --tools claude
```

## Verification

After configuration, test by asking:
- "What tables are available in the database?"
- "Show me patient demographics"
- "Search for notes mentioning diabetes"

## Troubleshooting

**DuckDB backend fails:**
- The demo database downloads automatically on first query
- No manual `m4 init` needed when using uvx

**BigQuery backend fails:**
- Verify GCP authentication: `gcloud auth list`
- Confirm PhysioNet access to the dataset
- Check project ID is correct

**Tools not appearing:**
- Ensure the MCP client configuration is valid JSON
- Restart the MCP client after configuration changes

## Resources

- GitHub: https://github.com/hannesill/m4
- Documentation: https://github.com/hannesill/m4/tree/main/docs
- Python API Guide: https://github.com/hannesill/m4/blob/main/docs/CODE_EXECUTION.md
- Skills Guide: https://github.com/hannesill/m4/blob/main/docs/SKILLS.md
