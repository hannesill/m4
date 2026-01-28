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

# Switch active dataset
uv run m4 use mimic-iv

# Show active dataset status (detailed view)
uv run m4 status

# List all datasets (compact table)
uv run m4 status --all
```

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

The active backend is configured via `m4 backend duckdb` (or `bigquery`), not through the MCP env block.

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
    └── backends/      - Database backends (DuckDB, BigQuery)

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
