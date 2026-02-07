# CLAUDE.md

## Project Description & Vision

M4 provides infrastructure for AI-assisted clinical research. It offers a natural language interface for LLMs and autonomous agents to interact with EHR data, making clinical datasets accessible to researchers regardless of SQL expertise.

Who it's for: Clinical researchers who want to screen hypotheses and characterize cohorts without writing SQL, data scientists who want faster iteration across datasets, and AI engineers building research agents that need structured access to clinical data. The project prioritizes accessibility — advanced features are available through flags but never complicate the default experience.

How it works: Install via pip, point to a m4_data directory, and M4 initializes a local DuckDB database exposed through an MCP server. This local-first approach respects data governance requirements inherent to clinical research. BigQuery is available for users with cloud access to full datasets.

The vision: Clinical data exploration with LLMs fails most often due to clinical semantics — the LLM doesn't understand what "sepsis" maps to in ICD codes, or which lab values indicate kidney function. M4 addresses this through curated concept mappings, rich schema documentation, and few-shot examples that encode clinical knowledge. The goal is making LLM-assisted research reliable enough for real clinical workflows.

### Current Focus

1. **Clinical semantics**: Curated concept mappings (e.g., "sepsis" → ICD codes, "kidney function" → creatinine/GFR), schema documentation with clinical meaning, and Claude Skills / few-shot query examples for common questions / processes
2. **Deeper notes support**: Semantic search over clinical notes (beyond keyword matching) and entity extraction (medications, diagnoses, procedures from unstructured text)
3. **Cross-dataset portability**: Same natural language queries working across MIMIC-IV and eICU without dataset-specific code
4. **Code Execution**: Allow LLMs with sandbox access (e.g. Claude Code) to use the tools in code rather than through MCP. This should save context and allows for more extensive data analysis.

### Datasets & Modalities

We currently support tabular data and clinical notes across MIMIC-IV, MIMIC-IV-Note, and eICU. Future versions will add waveforms and imaging. The modality-based architecture allows tools to be dynamically filtered based on what each dataset supports.

### Future

Full provenance tracking (query logging, session export/replay, result fingerprints) for reproducible research is on the roadmap but not yet implemented.

## Near-Term Paper

Title: M4: Multi-Dataset Infrastructure for LLM-Assisted Clinical Research

The paper will demonstrate:
- Modality-based architecture that generalizes across heterogeneous clinical datasets
- Cross-dataset portability: equivalent clinical questions working on both MIMIC-IV and eICU
- How the abstraction layer maintains accuracy while eliminating per-dataset engineering

Building on M3's demonstration of 94% accuracy on MIMIC-IV.

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

Use `from m4.display import show` to present key results to the researcher in real-time.
The display renders interactive tables, charts, and markdown in a live browser tab.

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
- For the full API, invoke the `/m4-display` skill
