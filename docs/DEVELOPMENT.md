# Development Guide

This guide is for contributors who want to develop M4 locally.

## Setup

### Clone and install

```bash
git clone https://github.com/hannesill/m4.git
cd m4
uv venv
uv sync
```

### Initialize test data

```bash
uv run m4 init mimic-iv-demo
```

## CLI Commands

### Dataset Management

```bash
# Initialize a dataset (downloads demo data if needed)
uv run m4 init mimic-iv-demo

# Materialize derived concept tables (MIMIC-IV only)
# Requires a database initialized with current M4 schema mapping.
# If you get a "Required schemas not found" error, reinitialize first:
#   uv run m4 init mimic-iv --force
uv run m4 init-derived mimic-iv

# List available derived tables without materializing
uv run m4 init-derived mimic-iv --list

# Switch active dataset
uv run m4 use mimic-iv

# Show active dataset status (detailed view)
uv run m4 status

# List all datasets (compact table)
uv run m4 status --all

# Show per-table derived materialization status
uv run m4 status --derived
```

### CLI JSON Output

Automation-friendly commands print JSON only to stdout when `--json` is used.
Validation errors handled inside the command use a stable envelope and exit
non-zero.

`m4 status --json` prints a status snapshot:

```json
{
  "version": 1,
  "active_dataset": "mimic-iv",
  "backend": "duckdb",
  "bigquery_project_id": "my-project",
  "datasets": [
    {
      "name": "mimic-iv",
      "active": true,
      "raw_present": true,
      "parquet_present": true,
      "db_present": true,
      "requires_authentication": true,
      "download_available": true,
      "setup_state": "ready",
      "bigquery_available": true,
      "row_count": 431231,
      "parquet_size_gb": 8.5,
      "derived": {
        "supported": true,
        "total": 63,
        "materialized": 63,
        "bigquery": false
      },
      "warnings": []
    }
  ]
}
```

Raw local paths are hidden by default in machine-facing output. Pass
`--paths` or set `M4_PATH_DISCLOSURE=1` to include path fields such as
`raw_root`, `parquet_root`, and `db_path`.

Dataset `warnings` is a list of stable warning codes. Currently documented
status warnings:

- `parquet_path_mismatch`: row-count verification could not read the Parquet
  path referenced by the local DuckDB views.

`m4 use TARGET --json` and `m4 backend BACKEND --json` wrap command results in
an `ok` envelope:

```json
{
  "version": 1,
  "ok": true,
  "command": "use",
  "active_dataset": "mimic-iv",
  "backend": "duckdb",
  "warnings": ["local_db_missing"]
}
```

Command errors use the same envelope with `ok: false`:

```json
{
  "version": 1,
  "ok": false,
  "command": "backend",
  "error": {
    "code": "project_id_required",
    "message": "BigQuery backend requires a project ID.",
    "hint": "Set it with: m4 backend bigquery --project-id <ID>"
  }
}
```

Stable command error codes are `dataset_not_found`, `backend_incompatible`,
`invalid_backend`, `invalid_option`, `project_id_required`, and
`dataset_incompatible`. Dataset setup can also return `missing_credentials`,
`physionet_auth_failed`, `physionet_access_forbidden`,
`download_network_failed`, `download_filesystem_failed`,
`download_interrupted`, `raw_files_missing`, `conversion_failed`,
`duckdb_init_failed`, and `verification_failed`.

`m4 init DATASET --json` uses the same result/error envelope and runs
non-interactively. Human prompts, progress panels, and download output are
suppressed from stdout. Successful results include deterministic paths and step
states:

```json
{
  "version": 1,
  "ok": true,
  "command": "init",
  "dataset": "mimic-iv",
  "db_path": "/absolute/path/to/mimic_iv.duckdb",
  "parquet_root": "/absolute/path/to/parquet/mimic-iv",
  "raw_root": "/absolute/path/to/raw_files/mimic-iv",
  "steps": [
    {"name": "raw_files", "status": "completed", "message": "Raw files are present."},
    {"name": "parquet", "status": "completed", "message": "Converted CSV to Parquet."},
    {"name": "database", "status": "completed", "message": "Created DuckDB views."}
  ],
  "warnings": []
}
```

Init step status is one of `skipped`, `completed`, `blocked`, or `failed`.
For credentialed datasets, missing raw/parquet/database artifacts are an
`ok: false` `raw_files_missing` result unless `--download` is requested.

For progress-aware wrappers, add `--events ndjson`:

```bash
m4 init mimic-iv --json --events ndjson --no-interactive --download \
  --physionet-credentials-file /path/to/physionet-credentials.json
```

With `--events ndjson`, stdout changes from one JSON object to a newline-delimited
JSON stream. The final command payload appears in `operation_completed.result`;
setup failures appear in `operation_failed.error`.

PhysioNet credentials files are JSON:

```json
{
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}
```

Do not expose passwords as command-line flags. M4 follows the same source basis
as PhysioNet's documented recursive resumable downloads (`wget -r -N -c -np`
from `/files/...`) but performs the download internally so wrappers can receive
structured progress and error events.

Agent-oriented commands use a stable envelope with `version`, `ok`, `command`,
`context`, `data`, `warnings`, and optional provenance fields:

```bash
m4 agent-env --dataset mimic-iv --backend duckdb --json
m4 list-datasets --json --no-interactive
m4 schema --dataset mimic-iv --backend duckdb --json --no-interactive
m4 describe-table mimiciv_hosp.patients --dataset mimic-iv --json --no-interactive
m4 query --dataset mimic-iv --backend duckdb --sql "SELECT 1 AS one" --json --no-interactive
m4 provenance export --json
```

These commands accept `--dataset` and `--backend` to resolve context without
changing saved active configuration. `agent-env --mode protected` omits
`M4_DATA_DIR` so a caller can expose only a service, socket, MCP server, or
gateway to agents.

### Runtime Environment

Durable environment controls:

| Variable | Purpose |
|----------|---------|
| `M4_DATA_DIR` | Exact M4 data directory containing `databases/`, `parquet/`, `datasets/`, and `raw_files/`. |
| `M4_HOME` | Runtime home for config and default telemetry when separate from the data directory. |
| `M4_DATASET` | Active dataset override. |
| `M4_BACKEND` | Active backend override, such as `duckdb` or `bigquery`. |
| `M4_PROJECT_ID` | BigQuery billing/project override. |
| `M4_TELEMETRY_DIR` | Directory for telemetry JSONL when `M4_EVENT_LOG` is not set. |
| `M4_EVENT_LOG` | Exact telemetry/provenance JSONL file path. |
| `M4_TELEMETRY` | Set to `off` to disable telemetry file output. |
| `M4_LOG_SQL` | SQL logging mode: `full`, `hash`, or `off`. |
| `M4_STUDY_ID`, `M4_SESSION_ID`, `M4_ACTOR` | Attribution fields added to telemetry/provenance records. |
| `M4_PATH_DISCLOSURE` | Set to `1`, `true`, `yes`, `on`, or `paths` to disclose raw local paths. |

`M4_DATA_DIR` now points directly at the data directory. Legacy values that
point at a parent directory containing `m4_data/` are accepted only as a
compatibility path and emit a deprecation warning.

### MCP Client Configuration

```bash
# Auto-configure Claude Desktop
uv run m4 config claude

# Generate config for other clients
uv run m4 config --quick
```

### Development Commands

```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/test_mcp_server.py -v

# Run tests matching pattern
uv run pytest -k "test_name" -v

# Lint and format
uv run pre-commit run --all-files

# Lint only
uv run ruff check src/

# Format only
uv run ruff format src/
```

## MCP Configuration for Development

Point your MCP client to your local development environment:

```json
{
  "mcpServers": {
    "m4": {
      "command": "/absolute/path/to/m4/.venv/bin/python",
      "args": ["-m", "m4.mcp_server"],
      "cwd": "/absolute/path/to/m4"
    }
  }
}
```

For normal local development, configure the active backend with
`m4 backend duckdb` or `m4 backend bigquery`. For isolated agents or MCP
servers, `M4_BACKEND` and `M4_DATASET` may be supplied in the environment to
override saved configuration for that process.

## Architecture Overview

M4 has three main layers:

```
MCP Layer (mcp_server.py)
    │
    ├── Exposes tools via Model Context Protocol
    └── Thin adapter over core functionality

Core Layer (src/m4/core/)
    │
    ├── datasets.py    - Dataset definitions and modalities
    ├── tools/         - Tool implementations (tabular, notes, management)
    ├── backends/      - Database backends (DuckDB, BigQuery)
    └── derived/       - Derived concept tables (vendored mimic-code SQL)

Infrastructure Layer
    │
    ├── data_io.py     - Download, convert, initialize databases
    ├── cli.py         - Command-line interface
    └── config.py      - Configuration management
```

### Modality-Based Tool System

Tools declare required modalities to specify which data types they need:

```python
class ExecuteQueryTool:
    required_modalities = frozenset({Modality.TABULAR})
```

The `ToolSelector` automatically filters tools based on the active dataset's modalities. If a dataset lacks a required modality, the tool returns a helpful error message instead of failing silently.

### Backend Abstraction

The `Backend` protocol defines the interface for query execution:

```python
class Backend(Protocol):
    def execute_query(self, sql: str, dataset: DatasetDefinition) -> QueryResult: ...
    def get_table_list(self, dataset: DatasetDefinition) -> list[str]: ...
```

Implementations:
- `DuckDBBackend` - Local Parquet files via DuckDB views
- `BigQueryBackend` - Google Cloud BigQuery

## Adding a New Tool

M4 uses a **protocol-based design** (structural typing). Tools don't inherit from a base class - they simply implement the required interface.

1. Create the tool class in `src/m4/core/tools/`:

```python
from dataclasses import dataclass
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.tools.base import ToolInput, ToolOutput

# Define input parameters
@dataclass
class MyNewToolInput(ToolInput):
    param1: str
    limit: int = 10

# Define tool class (no inheritance needed!)
class MyNewTool:
    """Tool description for documentation."""

    name = "my_new_tool"
    description = "Description shown to LLMs"
    input_model = MyNewToolInput
    output_model = ToolOutput

    # Modality constraints (use frozenset!)
    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = None  # None = all compatible

    def invoke(
        self, dataset: DatasetDefinition, params: MyNewToolInput
    ) -> ToolOutput:
        """Execute the tool."""
        # Implementation here
        return ToolOutput(result="Success")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if tool works with this dataset."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        return True
```

2. Register it in `src/m4/core/tools/__init__.py`:

```python
from .my_module import MyNewTool

def init_tools():
    ToolRegistry.register(MyNewTool())
```

3. Add the MCP handler in `mcp_server.py`:

```python
@mcp.tool()
@require_oauth2
def my_new_tool(param1: str, limit: int = 10) -> str:
    dataset = DatasetRegistry.get_active()
    result = _tool_selector.check_compatibility("my_new_tool", dataset)
    if not result.compatible:
        return result.error_message
    tool = ToolRegistry.get("my_new_tool")
    return tool.invoke(dataset, MyNewToolInput(param1=param1, limit=limit)).result
```

## Code Style

- **Formatter:** Ruff (line-length 88)
- **Type hints:** Required on all functions
- **Docstrings:** Google style on public APIs
- **Tests:** pytest with `asyncio_mode = "auto"`

## Testing

Tests mirror the `src/m4/` structure:

```
tests/
├── test_mcp_server.py
├── core/
│   ├── test_datasets.py
│   ├── tools/
│   │   └── test_tabular.py
│   └── backends/
│       └── test_duckdb.py
```

Run the full test suite before submitting PRs:

```bash
uv run pre-commit run --all-files
```

If you change the cohort-builder UI under `src/m4/apps/cohort_builder/ui/`,
regenerate the packaged single-file app and verify it matches the tracked
artifact:

```bash
cd src/m4/apps/cohort_builder/ui && npm ci
cd -
uv run python scripts/check_cohort_builder_bundle.py --update
uv run python scripts/check_cohort_builder_bundle.py
```

## Updating Vendored Derived SQL

The derived table SQL in `src/m4/core/derived/builtins/mimic_iv/` is vendored from the [mimic-code](https://github.com/MIT-LCP/mimic-code) repository. When mimic-code releases updated SQL (e.g., bug fixes or new concept tables), follow these steps to update:

1. **Check upstream changes:** Review the mimic-code repository for changes to the `mimic-iv/concepts_duckdb/` directory.

2. **Copy updated SQL files:** Replace the corresponding files under `src/m4/core/derived/builtins/mimic_iv/`. Preserve the existing directory structure (score/, sepsis/, medication/, etc.).

3. **Update the orchestrator:** If new tables were added or execution order changed, update `duckdb.sql` to reflect the new `.read` directives from mimic-code's orchestrator.

4. **Test materialization:** Run `m4 init-derived mimic-iv` against a local MIMIC-IV database to verify all tables build successfully.

5. **Update documentation:** If new table categories or tables were added, run `uv run python scripts/update_derived_docs.py` and update related README prose as needed. Use `uv run python scripts/update_derived_docs.py --check` to verify docs freshness.

The vendored approach means M4 works offline and ensures reproducibility -- users get the exact SQL version bundled with their M4 release, regardless of upstream changes.

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run `uv run pre-commit run --all-files`
5. Submit a PR with a clear description

## Docker

For containerized development:

**Local (DuckDB):**
```bash
docker build -t m4:lite --target lite .
docker run -d --name m4-server m4:lite tail -f /dev/null
```

**BigQuery:**
```bash
docker build -t m4:bigquery --target bigquery .
docker run -d --name m4-server \
  -e M4_BACKEND=bigquery \
  -e M4_PROJECT_ID=your-project-id \
  -v $HOME/.config/gcloud:/root/.config/gcloud:ro \
  m4:bigquery tail -f /dev/null
```

MCP config for Docker:
```json
{
  "mcpServers": {
    "m4": {
      "command": "docker",
      "args": ["exec", "-i", "m4-server", "python", "-m", "m4.mcp_server"]
    }
  }
}
```
