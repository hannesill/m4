# Architecture and Vision

M4 is infrastructure for AI-assisted clinical research. This document explains the design philosophy, architecture, and why M4 exists.

## Why M4?

### The Problem: Clinical Semantics

LLM-assisted clinical data exploration fails most often due to **clinical semantics**, not SQL syntax. An LLM can write syntactically correct SQL, but it doesn't know:

- What "sepsis" maps to in ICD codes
- Which lab values indicate kidney function (creatinine? GFR? both?)
- That SOFA scores require specific chartevents itemids
- How to join MIMIC-IV tables without duplicating rows
- That eICU structures data differently than MIMIC-IV

Without this knowledge, even sophisticated models produce queries that are syntactically correct but clinically meaningless.

### The Solution: Infrastructure Layer

M4 addresses this by providing three layers of clinical intelligence:

1. **Schema Documentation**: Tables and columns annotated with clinical meaning, not just data types
2. **Concept Mappings**: Curated mappings from clinical concepts ("sepsis", "kidney function") to database-specific implementations
3. **Agent Skills**: 17 skills—1 for the Python API and 16 validated clinical research patterns (SOFA scoring, Sepsis-3 criteria, KDIGO AKI staging) extracted from MIT-LCP repositories

This transforms M4 from "an MCP server that runs SQL" into "infrastructure that understands clinical research."


## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AI Clients                           │
│          (Claude Desktop, Cursor, Claude Code)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     M4 Infrastructure                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  MCP Server  │  │  Python API  │  │ Agent Skills │       │
│  │   (tools)    │  │ (code exec)  │  │ (knowledge)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                              │                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │           Modality-Based Tool System             │       │
│  │  (TABULAR, NOTES, future: WAVEFORMS, IMAGING)    │       │
│  └──────────────────────────────────────────────────┘       │
│                              │                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │             Backend Abstraction                  │       │
│  │        (DuckDB local, BigQuery cloud)            │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Clinical Datasets                       │
│       MIMIC-IV  │  MIMIC-IV-Note  │  eICU  │  Custom        │
└─────────────────────────────────────────────────────────────┘
```

### Three Access Patterns

**1. MCP Server (Natural Language)**

For exploratory questions: "What tables exist?", "Show me patients over 80", "Search notes for pneumonia."

```
AI Client → MCP Protocol → M4 Tools → Backend → Dataset
```

**2. Python API (Code Execution)**

For complex analysis: multi-step workflows, statistical computations, survival analysis.

```python
from m4 import set_dataset, execute_query
set_dataset("mimic-iv")
df = execute_query("SELECT * FROM mimiciv_hosp.patients")  # Returns DataFrame
```

**3. Agent Skills (Knowledge)**

For clinical intelligence: validated SQL patterns, concept definitions, methodological guidance.

```
User: "Calculate SOFA scores for my sepsis cohort"
Claude: [Uses sofa-score skill with validated MIT-LCP SQL]
```


## Core Design Principles

### 1. Modality-Based Tools

Datasets contain different data types (modalities):
- **TABULAR**: Structured tables (labs, demographics, vitals)
- **NOTES**: Clinical narratives (discharge summaries, radiology reports)
- Future: **WAVEFORMS**, **IMAGING**

Tools declare which modalities they require:

```python
class ExecuteQueryTool:
    required_modalities = frozenset({Modality.TABULAR})

class SearchNotesTool:
    required_modalities = frozenset({Modality.NOTES})
```

When you switch datasets, M4 automatically shows only compatible tools. Query a tabular dataset? You get SQL tools. Switch to MIMIC-IV-Note? You get notes search tools.

### 2. Backend Abstraction

The same queries work on local files or cloud databases:

| Backend | Use Case | Setup |
|---------|----------|-------|
| **DuckDB** | Local development, data governance | Parquet files on disk |
| **BigQuery** | Full datasets, cloud collaboration | Google Cloud credentials |

Researchers can prototype locally with the demo dataset, then scale to full MIMIC-IV on BigQuery without changing queries.

### 3. Cross-Dataset Portability

The same clinical question should work across datasets:

```
"Find patients with sepsis"
```

On MIMIC-IV: Uses ICD-10 codes, mimiciv_derived tables
On eICU: Uses ICD-9 codes, different table structure

M4's skills and concept mappings handle these translations, enabling external validation studies without per-dataset engineering.


## Component Details

### MCP Server (`mcp_server.py`)

FastMCP server exposing tools via Model Context Protocol. Thin adapter over core functionality.

**Tools exposed:**
- Dataset management: `list_datasets`, `set_dataset`
- Tabular: `get_database_schema`, `get_table_info`, `execute_query`
- Notes: `search_notes`, `get_note`, `list_patient_notes`

### Python API (`api.py`)

Direct programmatic access returning native Python types:

| Function | Returns |
|----------|---------|
| `execute_query(sql)` | `pd.DataFrame` |
| `get_schema()` | `dict` |
| `get_table_info(table)` | `dict` with DataFrame values |
| `search_notes(query)` | `dict` with DataFrame values |

### Tool System (`core/tools/`)

Protocol-based design (structural typing). Tools implement:

```python
class Tool(Protocol):
    name: str
    description: str
    required_modalities: frozenset[Modality]

    def invoke(self, dataset, params) -> ToolOutput: ...
    def is_compatible(self, dataset) -> bool: ...
```

The `ToolSelector` filters tools based on active dataset modalities.

### Backend System (`core/backends/`)

Backend protocol for query execution:

```python
class Backend(Protocol):
    def execute_query(self, sql, dataset) -> QueryResult: ...
    def get_table_list(self, dataset) -> list[str]: ...
```

Implementations handle database-specific details (DuckDB views, BigQuery schemas).


## Data Flow Example

**User asks:** "What's the mortality rate for patients with AKI?"

**Without M4:**
1. LLM guesses at table names, column names
2. May not know KDIGO staging criteria
3. Produces syntactically correct but clinically incorrect SQL

**With M4:**
1. `kdigo-aki-staging` skill activates with validated SQL
2. LLM uses proper MIMIC-IV table joins
3. Query uses peer-reviewed AKI definitions from MIT-LCP

```python
# Claude Code with M4 skills generates:
from m4 import set_dataset, execute_query

set_dataset("mimic-iv")

# KDIGO AKI staging (validated)
aki_cohort = execute_query("""
    SELECT
        k.stay_id,
        k.aki_stage,
        a.hospital_expire_flag
    FROM mimiciv_derived.kdigo_stages k
    JOIN admissions a ON k.hadm_id = a.hadm_id
    WHERE k.aki_stage >= 1
""")

mortality_rate = aki_cohort['hospital_expire_flag'].mean()
```


## Supported Datasets

| Dataset | Modalities | Patients | Access |
|---------|------------|----------|--------|
| mimic-iv-demo | TABULAR | 100 | Free |
| mimic-iv | TABULAR | 365k | PhysioNet credentialed |
| mimic-iv-note | NOTES | 331k notes | PhysioNet credentialed |
| eicu | TABULAR | 200k+ | PhysioNet credentialed |

Custom datasets can be added via JSON definition. See [Custom Datasets](CUSTOM_DATASETS.md).


## Future Directions

### Additional Modalities
- **WAVEFORMS**: ECG, arterial blood pressure waveforms
- **IMAGING**: Chest X-rays, CT scans

### Enhanced Clinical Semantics
- Semantic search over clinical notes (beyond keyword matching)
- Entity extraction from unstructured text
- Expanded concept mappings for more clinical domains

### Provenance and Reproducibility
- Query logging with timestamps
- Session export/replay
- Result fingerprints for audit trails


## References

- MIMIC-IV: https://mimic.mit.edu/docs/iv/
- eICU: https://eicu-crd.mit.edu/
- MIT-LCP Code Repositories: https://github.com/MIT-LCP
- Model Context Protocol: https://modelcontextprotocol.io/
