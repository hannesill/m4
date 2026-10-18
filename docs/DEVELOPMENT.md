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

# Show dataset status (detailed view)
uv run m4 status --dataset mimic-iv

# List all datasets (compact table)
uv run m4 status --all

# Show per-table derived materialization status
uv run m4 status --dataset mimic-iv --derived
```

### CLI JSON Output

Automation-friendly commands print JSON only to stdout when `--json` is used.
Validation errors handled inside the command use a stable envelope and exit
non-zero.

`m4 status --json` prints a status snapshot:

```json
{
  "version": 1,
  "selected_dataset": "mimic-iv",
  "backend": "duckdb",
  "bigquery_project_id": "my-project",
  "datasets": [
    {
      "name": "mimic-iv",
      "title": "MIMIC-IV",
      "summary": "Hospital and ICU records of patients admitted to ...",
      "version": "3.1",
      "builtin": true,
      "modalities": ["TABULAR"],
      "dataset_page_url": "https://physionet.org/content/mimiciv/",
      "dua_url": "https://physionet.org/content/mimiciv/",
      "download_size_gb": null,
      "selected": true,
      "raw_present": true,
      "parquet_present": true,
      "db_present": true,
      "prepared": true,
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

Each dataset also says what it is, for someone choosing one to download:
`title`, `summary`, `version` (the PhysioNet version M4 downloads),
`dataset_page_url`, `dua_url` (where the data use agreement of a credentialed
dataset is signed), `download_size_gb` (about how many GB, of 1024^3 bytes, the
raw CSV.gz files M4 downloads take), `modalities`, and `builtin` (false for a
dataset defined by a JSON file in the datasets folder). What M4 does not know
is null; PhysioNet shows the file sizes of a credentialed dataset only to people
with access to it. `m4 list-datasets --json` lists the same entries.

`prepared` is true, and `setup_state` is `ready`, only when `m4 init` ran to the
end for the dataset: every raw file has its table, the views exist, and the
verification query answered where the dataset has one. Parquet files and a
database that merely exist do not count, because an interrupted `m4 init`
leaves both. Other values of `setup_state` are `credentials_required`,
`missing_raw_files`, `missing_parquet`, `missing_database`, and `incomplete`
(files exist but the last initialization did not finish, a raw file in M4's
raw folder has no table yet, or the files were made by M4 0.5.5 or earlier,
which did not record that it finished). A raw file in a folder that the
dataset maps to no schema is converted, but M4 makes no view for it.

Running `m4 init DATASET` again finishes the dataset: it converts only the raw
files that have no finished Parquet file yet. Pass the same `--src` again to
go on with a run that read from another folder, and leave it out to convert
what has come into M4's own raw folder since.
A conversion that was interrupted is finished from the folder it read from,
or from one that holds the raw files of the tables it did not get to. From any
other folder `m4 init` fails with `raw_files_missing` instead of building a
database without those tables.

M4 keeps this state in three small files. `<database>.m4-prepared.json`, next
to the DuckDB file (the file itself, where its path is a link), is written
last by `m4 init` and lists the Parquet files the views were verified over; a
dataset stops being ready when those files change.
`.m4-converting.json`, in the dataset's Parquet folder, exists while a
conversion is unfinished and lists the tables it set out to make. A table
that is being converted is named `<table>.parquet.<id>.part`.
`.m4-downloading.json`, in a raw folder, exists while a download by M4 into
that folder is unfinished. A file that is being downloaded is named
`<file>.csv.gz.part`; one that is left without its finished file says that a
download did not finish, whoever made it.

Raw local paths are hidden by default in machine-facing output. Pass
`--paths` or set `M4_PATH_DISCLOSURE=1` to include path fields such as
`raw_root`, `parquet_root`, and `db_path`.

Dataset `warnings` is a list of stable warning codes. Currently documented
status warnings:

- `parquet_path_mismatch`: row-count verification could not read the Parquet
  path referenced by the local DuckDB views.

`m4 backend BACKEND --json` wraps command results in an `ok` envelope:

```json
{
  "version": 1,
  "ok": true,
  "command": "backend",
  "backend": "duckdb",
  "warnings": []
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
`invalid_backend`, `invalid_option`, `project_id_required`,
`dataset_incompatible`, and `active_dataset_removed`. Dataset setup can also return `missing_credentials`,
`physionet_auth_failed`, `physionet_access_forbidden`, `physionet_url_required`,
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
  "prepared": true,
  "warnings": []
}
```

Init step status is one of `skipped`, `completed`, `blocked`, or `failed`.
`prepared` says whether the dataset is now ready, as `m4 status` reports it.
A run that succeeds can still answer false: status reads M4's default
database, not one made with `--db-path`, and a raw file may have come into
M4's own raw folder that this run did not convert.
For credentialed datasets, missing raw/parquet/database artifacts are an
`ok: false` `raw_files_missing` result unless `--download` is requested.
When PhysioNet refuses the login (`physionet_access_forbidden`), `m4 download`,
`m4 init --download` and `m4 fetch-images` name the dataset's agreement page in
`error.hint`; an account needs each dataset's agreement signed.

A download that did not finish is finished before anything is converted.
`m4 init` fetches the rest of an open dataset itself. For a credentialed
dataset it needs `--download` and the credentials: without `--download` it
fails with `raw_files_missing`, without the credentials with
`missing_credentials`. Files that are complete are skipped. With `--download`,
raw files in M4's own raw folder are gone over again even when no download is
known to be unfinished, for a credentialed dataset only if the credentials are
given. `m4 download` removes its note once every file is there; if the files
arrived another way, deleting `.m4-downloading.json` says so.

`raw_files_missing` is also the answer when the raw files are not all of the
dataset as far as M4 can tell, or are not where the dataset has them:

- The folder holds a download that did not finish, `--src` or not.
  `error.hint` names the `m4 download` command that finishes it.
- M4's own raw folder has no file for one of the dataset's folders, such as
  `icu/`, and there are no tables for it either. That is all M4 can tell of a
  download that left nothing behind to say it stopped. A folder named with
  `--src` is taken as it is, which is also how to initialize a dataset that is
  meant to hold only some of its folders.
- `--src` is not the folder that holds the dataset's files directly (for
  example the `physionet.org/` folder a plain `wget -r` creates). `error.hint`
  names the folder to use when exactly one fits, and lists them when several
  do, as in a tree that holds more than one dataset.

For progress-aware wrappers, add `--events ndjson`:

```bash
m4 init mimic-iv --json --events ndjson --no-interactive --download \
  --physionet-credentials-file /path/to/physionet-credentials.json
```

With `--events ndjson`, stdout changes from one JSON object to a newline-delimited
JSON stream. The final command payload appears in `operation_completed.result`;
setup failures appear in `operation_failed.error`.

M4 downloads and converts raw files ending in `.csv.gz` or `.csv`. A file that is not UTF-8 is read again as UTF-16 when it starts
with that byte order mark, and as Latin-1 otherwise; init then fails with
`csv_encoding_unsupported` if that does not work either, and two files that
would make one table fail it with `table_name_collision`. Files read with a
fallback add to the result's `conversion_warnings` (each with `code`, `file`,
and for decimal commas `columns`, also sent as `conversion_warning` events) and
their codes to `warnings`: `csv_read_as_latin1`, and
`decimal_comma_columns_kept_as_text` for text columns of a `;`-separated file
that hold numbers such as `3,5`. A file whose header line holds no `;` is not
looked at for those, and PhysioNet's files are converted as before.

`conversion_started.file_count` counts the files this run converts.
`skipped_count` counts the raw files that already had a finished Parquet file,
which is not zero when an interrupted run is continued. When nothing is left to
convert, no conversion events are emitted.

PhysioNet credentials files, and the login sent with
`--physionet-credentials-stdin`, are JSON in UTF-8 on every platform:

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

M4 sends the login only with requests to `https://physionet.org/`. A dataset
whose address is anywhere else fails with `physionet_url_required` before
anything is sent, and the login is left out when PhysioNet redirects to another
host. The password is kept out of the credentials object's repr, and the CLI's
tracebacks do not print local variables.

`m4 fetch-images DATASET --from-csv FILE` downloads the images of a cohort
from an imaging dataset (one with the `IMAGING` modality, such as
`mimic-cxr-jpg`). `m4 download` and `m4 init` fetch only such a dataset's
tables, and nothing in M4 fetches all of its images. The CSV file names each
image by `image_path` (or `path`), as the dataset's images view
(`mimic_cxr.images`) has it, or by its id (`dicom_id`), which M4 looks up in
that view of the initialized dataset. An image lands at its `image_path` below
the dataset's raw folder (`--target` names another), which is also its path
below the PhysioNet listing. Four images load at a time. A failure other than
a refused login is retried four times, the pause doubling from 5 s; an
interrupted image is resumed from its `.part` file, and an image that is there
is not requested again, so the same command run again finishes what a run
left. Images that are all on disk need no login: without one, the command
fails with `missing_credentials` only when an image is missing, and before
anything is fetched, so a caller can try without a login first. A list with
more than 10,000 images to fetch is refused unless `--max-images` allows it.
`m4.local_image_paths(dataset, rows)` says where each row's image is and
whether it is there, without fetching.

With `--json` the result holds `dataset`, `root`, `image_count`, `fetched`,
`skipped` (there already), `failed` (each with `image_path`, `code` and
`message`), `bytes_downloaded`, and `status`. Error codes are
`dataset_not_found`, `not_an_imaging_dataset`, `missing_credentials` (with
`data`; `image_count` less `skipped` is what is missing),
`image_list_invalid` (no usable column, a path that is not one of the dataset's
images, or an id the view does not have), `dataset_not_initialized` (ids, but
no images view to look them up in), `too_many_images`, `physionet_auth_failed`,
`physionet_access_forbidden` (its `hint` names the agreement page:
MIMIC-CXR-JPG has a DUA of its own), `physionet_url_required`,
`download_filesystem_failed`, `download_interrupted`, and `images_incomplete`
(some images failed, the others are there). An error after fetching began
carries `data` with the result's fields.

With `--events ndjson` the stream holds `m4 download`'s events:
`operation_started`, `download_started` (`file_count`), then for each image
`download_file_started` and `download_file_progress` (`path`,
`bytes_downloaded`, `bytes_total`; about once a second while it loads) and one
of `download_file_completed`, `download_file_skipped` (it was there), or
`download_file_failed` (`path`, `code`, `message`), then `download_completed`
and `operation_completed`, or `operation_failed` with `error` and `data`. Four
images load at once, so their events interleave; an image that loads within a
second may have no `download_file_started`.

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
changing saved backend configuration. `agent-env --mode protected` omits
`M4_DATA_DIR` so a caller can expose only a service, socket, MCP server, or
gateway to agents.

`m4 define-dataset NAME --src DIR --json` uses the same envelope. It saves
`<data dir>/datasets/NAME.json`, inferred from the CSV files in `DIR` and
its subfolders (see [Custom Datasets](CUSTOM_DATASETS.md)); `m4 init NAME --src
DIR` then converts them. `data` holds `name`, `title`, `summary`,
`definition_path`, `defined_from`, `schemas` (schema to number of tables),
`tables`, `table_count`, `primary_verification_table`, `dry_run`, `replaced`
(a definition of that name was replaced), `init_command`, and the saved
`definition`. Its error codes are `invalid_dataset_name`,
`builtin_dataset`, `database_name_taken` (the name would share another
dataset's DuckDB file, as `mimic_iv` would with `mimic-iv`), `dataset_exists`
(a hand-written definition, replaced only with `--force`, or one in another
file, never replaced), `dataset_prepared` (the definition it would replace has
Parquet files or a database; run `m4 remove-dataset NAME` first),
`source_not_found`, `source_not_a_directory`, `raw_files_missing` (no CSV
files), `unsupported_layout` (files more than one folder deep),
`invalid_table_name`, `table_name_collision` (two files, such as `labs.csv`
and `labs.csv.gz`, would make one table), and `definition_write_failed`.
`--dry-run` checks everything and saves nothing.

`m4 remove-dataset NAME --json` (with `--keep-definition` and `--dry-run`) uses
it too. It removes the dataset's DuckDB file with the `.wal` and prepared
marker beside it, its Parquet folder with any unfinished conversion,
`raw_files/NAME`, and a custom dataset's definition. A database made with
`m4 init --db-path` is recorded nowhere, so it is not removed. `data` holds `name`,
`builtin`, `removed` (`path` and `bytes` of each, as it would be with
`--dry-run`), `freed_bytes`, `definition_removed`, `source_kept` (the
`defined_from` folder, which is never touched), `skipped`, and `dry_run`. Each
`skipped` entry has `path`, `resolves_to` and a `reason`: `outside_data_dir`
(the path, a link resolved, leads out of the data directory),
`dataset_source` (it is or holds the folder the dataset was defined from),
`shared_with_another_dataset` (another dataset has the same DuckDB file),
`not_a_database_file` (the database path is not a file of its own in the
databases folder; M4 never removes a folder there), or `configured_path`
(`config.json` sets it). A dataset with nothing on disk is
removed with an empty `removed`; an empty folder is removed without being
listed. Error codes are `invalid_dataset_name`, `dataset_not_found`,
`dataset_in_use` (another process has the database open, checked before
anything is removed; on Windows also a file that cannot be removed while
open), and `remove_failed`. These two errors carry `data` with what was
removed before them.

Like `list-datasets`, both commands hide raw local paths unless `--paths` is
given or `M4_PATH_DISCLOSURE=1` is set, and say so in `raw_paths_hidden`. A
hidden path in the data directory reads `<M4_DATA_DIR>/...`; any other, such
as the folder a dataset was defined from, is null, and `init_command` reads
`m4 init NAME --src <folder>`.

### Runtime Environment

Durable environment controls:

| Variable | Purpose |
|----------|---------|
| `M4_DATA_DIR` | Exact M4 data directory containing `databases/`, `parquet/`, `datasets/`, and `raw_files/`. |
| `M4_HOME` | Runtime home for config and default telemetry when separate from the data directory. |
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
servers, `M4_BACKEND` may be supplied in the environment to override saved
backend configuration for that process. Datasets are selected per request.

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

The `ToolSelector` filters tools based on the request's explicit dataset. If a dataset lacks a required modality, the tool returns a helpful error message instead of failing silently.

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
    dataset = DatasetRegistry.get("mimic-iv")
    if dataset is None:
        return "Dataset 'mimic-iv' is not registered."
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
