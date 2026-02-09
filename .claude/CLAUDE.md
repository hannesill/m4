# CLAUDE.md

## Project Description & Vision

M4 is infrastructure for AI agents doing clinical research. It gives AI agents clinical intelligence — curated concept mappings, validated scoring algorithms, and deep schema knowledge — alongside structured access to EHR datasets (MIMIC-IV, eICU, custom datasets) via MCP and a Python API. The goal is enabling AI agents to conduct rigorous, reproducible clinical research autonomously or in collaboration with human researchers.

Who it's for: Clinical researchers who want to screen hypotheses and characterize cohorts without writing SQL, data scientists who want faster iteration across datasets, and AI engineers building clinical research agents. The project prioritizes accessibility — advanced features are available through flags but never complicate the default experience.

How it works: Install via pip, run `m4 init`, and M4 sets up a local DuckDB database. AI agents connect via MCP (Claude Desktop, Cursor, etc.) or import the Python API directly for programmatic analysis. BigQuery is available for cloud access to full datasets. The local-first approach respects data governance requirements inherent to clinical research.

### Vision

**Short-term — Paper:** Demonstrate that M4's architecture (modality-based tool system, agent skills, cross-dataset portability) enables AI agents to conduct clinically accurate research across heterogeneous EHR datasets. Building on M3's 94% accuracy on MIMIC-IV, the paper will show how clinical semantics encoded as agent skills and concept mappings generalize across MIMIC-IV and eICU.

**Mid/long-term — Clinical research infrastructure for AI agents:** M4 becomes the standard infrastructure layer for AI agents conducting clinical research. This means: agents that can autonomously design studies, select cohorts, run analyses, and produce reproducible results — with guardrails that enforce scientific integrity. The platform expands to cover more datasets, modalities (waveforms, imaging), and research patterns, making it possible for AI agents to tackle increasingly complex clinical questions.

### What's Built

1. **Agent Skills**: 20+ skills that teach AI agents clinical research patterns — severity scores (SOFA, APACHE III, SAPS-II, OASIS, LODS, SIRS), sepsis identification (Sepsis-3, suspected infection), organ failure staging (KDIGO AKI), measurements (GCS, baseline creatinine, vasopressor equivalents), cohort selection, and research methodology. Skills activate automatically when relevant.
2. **Python API / Code Execution**: `from m4 import execute_query, set_dataset, get_schema` — returns DataFrames for multi-step analyses, statistical computation, and reproducible notebooks. Same tools as MCP but returns Python types.
3. **Cross-dataset portability**: AI agents switch between datasets at runtime (`m4 use mimic-iv`, `set_dataset("eicu")`). Same clinical questions work across MIMIC-IV and eICU.
4. **M4 Apps**: Interactive UIs rendered directly in AI clients (e.g., Cohort Builder with live filtering). For hosts supporting the MCP Apps protocol.
5. **Display system (vitrine)**: `from m4.vitrine import show` — real-time interactive tables, charts, and markdown in a live browser tab for researcher-in-the-loop workflows.
6. **Derived tables**: 63 pre-computed clinical concept tables materialized from vendored mimic-code SQL.
7. **Custom datasets**: Any PhysioNet or custom dataset can be added following documented conventions.

### Current Focus

1. **More clinical semantics**: Expanding concept mappings (comorbidity indices, medication classes) and agent skills
2. **Semantic search over clinical notes**: Beyond keyword matching — entity extraction and deeper NLP
3. **New modalities**: Waveforms (ECG, arterial blood pressure) and imaging (chest X-rays)
4. **Research agent guardrails**: Skills and checks that enforce scientific integrity, documentation standards, and best practices
5. **Provenance**: Query logging, session export/replay, result fingerprints for reproducible and auditable research

### Datasets & Modalities

We support tabular data and clinical notes across MIMIC-IV, MIMIC-IV-Note, eICU, and custom datasets. Future versions will add waveforms and imaging. The modality-based architecture dynamically filters tools based on what each dataset supports.

## Quick Reference

```bash
uv run pytest -v                    # Run all tests
uv run pytest tests/test_mcp_server.py -v  # Run single test file
uv run pytest -k "test_name" -v     # Run tests matching pattern
uv run pre-commit run --all-files   # Lint + format + test
uv run ruff check src/              # Lint only
uv run ruff format src/             # Format only
```

## Architecture Overview

M4 bridges AI clients (Claude Desktop, Cursor) and medical datasets via the Model Context Protocol. The system has three main layers:

### 1. Modality-Based Tool System (`src/m4/core/`)

The core architecture uses modalities to dynamically filter which MCP tools are exposed based on the active dataset:

- **Modality** (`datasets.py`): Data types a dataset contains (`TABULAR`, `NOTES`). Future: `WAVEFORMS`, `IMAGING`
- **DatasetDefinition** (`datasets.py`): Dataset metadata with declared modalities and related datasets
- **Tool Protocol** (`tools/base.py`): Tools declare `required_modalities` they need from a dataset
- **ToolSelector** (`tools/registry.py`): Filters tools based on dataset compatibility via `tool.is_compatible(dataset)`

Example flow: If a dataset lacks the `NOTES` modality, clinical notes tools (`search_notes`, `get_note`, `list_patient_notes`) won't be exposed.

### 2. Derived Table System (`src/m4/core/derived/`)

Pre-computed clinical concept tables (~63) materialized from vendored [mimic-code](https://github.com/MIT-LCP/mimic-code) SQL. MIMIC-IV only. Created via `m4 init-derived mimic-iv` into the `mimiciv_derived` schema. BigQuery users already have these via `physionet-data.mimiciv_derived`.

- **materializer.py**: `materialize_all()` — opens read-write DuckDB connection, executes SQL in dependency order
- **builtins/**: Vendored SQL organized by category (score/, sepsis/, medication/, measurement/, etc.)
- **builtins/\_\_init\_\_.py**: `get_execution_order()`, `list_builtins()`, `has_derived_support()`, `get_tables_by_category()`

### 3. Backend Abstraction (`src/m4/core/backends/`)

- **Backend Protocol** (`base.py`): Interface for query execution (`execute_query`, `get_table_list`, `get_table_info`)
- **DuckDBBackend** (`duckdb.py`): Local Parquet files via DuckDB views
- **BigQueryBackend** (`bigquery.py`): Cloud access to full datasets

### 4. MCP Server Layer (`src/m4/mcp_server.py`)

FastMCP server exposing tools as MCP endpoints. Tool registration flows through `ToolRegistry` → `ToolSelector` → MCP.

## Key Patterns

- **Internal functions**: Prefix with `_` (e.g., `_execute_duckdb_query`) to prevent MCP tools calling MCP tools
- **Logging**: `from m4.config import logger`
- **SQL Safety**: All queries validated via `_is_safe_query()` before execution
- **OAuth2**: `@require_oauth2` decorator guards sensitive tools
- **Frozensets**: Use `frozenset()` for immutable modality sets in tool definitions

## Testing

- pytest with `asyncio_mode = "auto"` (no need for `@pytest.mark.asyncio`)
- Tests mirror `src/m4/` structure in `tests/`
- CI runs on Python 3.10 and 3.12

## Code Style

- Ruff for linting/formatting (line-length 88)
- Full type hints required
- Google-style docstrings on public APIs

## Display Output

When executing Python analysis, always save outputs to files for reproducibility:
- DataFrames → CSV/Parquet files
- Figures → PNG/SVG files
- Reports → Markdown/HTML files

Use `from m4.vitrine import show` to present key results to the researcher in real-time.
Vitrine renders interactive tables, charts, and markdown in a live browser tab.

Show what matters for the conversation — not everything:
- Cohort summaries the researcher needs to review before proceeding
- Charts that inform a decision ("does this distribution look right?")
- Key findings, intermediate conclusions, and decision points
- Research protocol drafts for approval

Don't show() routine intermediate DataFrames, debugging output, or exhaustive tables —
those belong in files only.

Quick reference:
- `show(df, title="...")` — interactive table with paging/sorting
- `show(fig)` — Plotly or matplotlib chart
- `show("## Finding\n...")` — markdown card
- `section("Phase 2")` — visual divider
- `run_id="study-name"` — group related outputs
- `show(df, wait=True, prompt="Proceed?")` — block until researcher responds
- For the full API, invoke the `/m4-vitrine` skill
