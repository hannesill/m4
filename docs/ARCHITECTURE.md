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
3. **Agent Skills**: Skills for the Python API and validated clinical research patterns (SOFA scoring, Sepsis-3 criteria, KDIGO AKI staging) extracted from MIT-LCP repositories. For the canonical list, see `src/m4/skills/SKILLS_INDEX.md`.

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

### Derived Table System (`core/derived/`)

Pre-computed clinical concept tables materialized from vendored SQL. This system provides ~63 derived tables for MIMIC-IV, covering severity scores, sepsis definitions, organ failure staging, medications, measurements, and more.

**Architecture:**

```
core/derived/
├── __init__.py              # Public API: materialize_all()
├── materializer.py          # Orchestrates CREATE TABLE execution
└── builtins/
    ├── __init__.py           # Execution order parsing, listing
    └── mimic_iv/
        ├── duckdb.sql        # Orchestrator (defines dependency order)
        ├── score/            # SOFA, SAPS-II, APACHE III, OASIS, LODS, SIRS
        ├── sepsis/           # Sepsis-3, suspicion of infection
        ├── organfailure/     # KDIGO creatinine/UO/stages, MELD
        ├── medication/       # Vasopressors, antibiotics, ACE inhibitors, NSAIDs, etc.
        ├── measurement/      # Labs, vitals, GCS, blood gas, urine output, etc.
        ├── demographics/     # Age, ICU stay details, weight durations
        ├── firstday/         # First-day labs, vitals, GCS, SOFA, etc.
        ├── treatment/        # Ventilation, RRT, CRRT, invasive lines
        └── comorbidity/      # Charlson comorbidity index
```

**Vendored SQL approach:** The SQL files are sourced from the [mimic-code](https://github.com/MIT-LCP/mimic-code) repository, which is peer-reviewed and used in hundreds of published studies. The files are vendored (copied into M4's source tree) rather than fetched at runtime, ensuring reproducibility and offline operation. Each SQL file creates a table in the `mimiciv_derived` schema.

**Materialization flow:**
1. User runs `m4 init-derived mimic-iv` (or accepts the prompt during `m4 init mimic-iv`)
2. The materializer opens a read-write DuckDB connection to the existing database
3. A pre-flight check verifies that required base schemas (`mimiciv_hosp`, `mimiciv_icu`) exist — these are created by `m4 init` via schema mapping
4. It drops and recreates the `mimiciv_derived` schema
5. The `duckdb.sql` orchestrator defines execution order (respecting inter-table dependencies)
6. Each SQL file is executed sequentially, creating tables like `mimiciv_derived.sofa`, `mimiciv_derived.sepsis3`, etc.
7. Tables become immediately queryable via `execute_query`

**Schema dependency:** The vendored SQL references schema-qualified tables (e.g., `mimiciv_icu.chartevents`, `mimiciv_hosp.patients`). These schemas are created by `m4 init` using the dataset's `schema_mapping`. If you initialized your database with an older version of M4 that used flat naming (e.g., `icu_chartevents`), you must reinitialize with `m4 init mimic-iv --force` before running `init-derived`.

**DuckDB-specific SQL modifications:** Most vendored SQL is used as-is from mimic-code. Where the upstream SQL causes severe performance problems under DuckDB (but runs fine on PostgreSQL/BigQuery), we apply targeted rewrites that preserve identical output. These are documented in comments at the top of each modified file. Current modifications:

- `sepsis/suspicion_of_infection.sql`: The upstream query uses `OR` conditions in its JOIN clauses (one branch for cultures with `charttime`, another for cultures with only `chartdate`). `OR` in join predicates prevents DuckDB's IEJoin range-join optimization, causing nested-loop scans (~18 min on full MIMIC-IV). The rewrite splits the `OR` into two separate `INNER JOIN` + `UNION ALL` paths with identical comparison operators, enabling IEJoin on each path.

**Backend note:** Derived table materialization is a DuckDB-only operation. BigQuery users already have these tables available at `physionet-data.mimiciv_derived` and do not need to run `init-derived`.

**Dataset support:** Currently limited to MIMIC-IV (full dataset). Not available for mimic-iv-demo or eICU.

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

| Dataset | Modalities | Patients | Access | Derived Tables |
|---------|------------|----------|--------|----------------|
| mimic-iv-demo | TABULAR | 100 | Free | No |
| mimic-iv | TABULAR | 365k | PhysioNet credentialed | Yes (63 tables) |
| mimic-iv-note | NOTES | 331k notes | PhysioNet credentialed | No |
| eicu | TABULAR | 200k+ | PhysioNet credentialed | No |

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
