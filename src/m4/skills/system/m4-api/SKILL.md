---
name: m4-api
description: Use the M4 Python API to query clinical datasets programmatically. Use when writing code to access clinical databases, executing SQL via Python, or performing multi-step data analysis.
tier: community
category: system
---

# M4 Python API

The M4 Python API provides programmatic access to clinical datasets for code execution environments. It mirrors the MCP tools but returns native Python types (DataFrames, dicts) instead of formatted strings.

## When to Use the API vs MCP Tools

**Use the Python API when:**
- **Complex clinical analysis** - Multi-step analyses that require intermediate results, joins across queries, or statistical computations
- **Large result sets** - Query results with thousands of rows can be stored in DataFrames without dumping into context
- **Mathematical operations** - Aggregations, percentile calculations, statistical tests, and counting that benefit from pandas/numpy
- **Iterative exploration** - Building up analysis through multiple queries where each step informs the next

**Use MCP tools when:**
- Simple one-off queries where the result fits comfortably in context
- Interactive exploration where you want to see results immediately

## Required Workflow

**You must follow this sequence:**

1. Choose a dataset name and pass it explicitly, or create `M4Client(dataset=...)`
2. `get_schema(dataset=...)` / `get_table_info(..., dataset=...)` - Explore available tables
3. `execute_query()` - Run SQL queries

```python
from m4 import get_schema, get_table_info, execute_query

dataset = "mimic-iv"  # or "mimic-iv-demo", "eicu", "mimic-iv-note"

# Step 1: Explore schema
schema = get_schema(dataset=dataset)
print(schema['tables'])  # List of table names

# Step 2: Inspect specific tables before querying
info = get_table_info("mimiciv_hosp.patients", dataset=dataset)
print(info['schema'])  # DataFrame with column names, types
print(info['sample'])  # DataFrame with sample rows

# Step 3: Execute queries
df = execute_query(
    "SELECT gender, COUNT(*) as n FROM mimiciv_hosp.patients GROUP BY gender",
    dataset=dataset,
)
# Returns pd.DataFrame - use pandas operations freely
```

## API Reference

### Dataset Management

| Function | Returns | Description |
|----------|---------|-------------|
| `list_datasets()` | `list[str]` | Available dataset names |
| `M4Client(dataset=...)` | `M4Client` | Preferred explicit client for one dataset |
| `client.with_dataset(name)` | `M4Client` | New client with the same session context and a different dataset |
| `client.switch_dataset(name)` | `M4Client` | Mutate a client to another dataset for notebook-style sessions |

### Tabular Data (requires TABULAR modality)

| Function | Returns | Description |
|----------|---------|-------------|
| `get_schema(dataset=...)` | `dict` | `{'backend_info': str, 'tables': list[str]}` |
| `get_table_info(table, dataset=..., show_sample=True)` | `dict` | `{'schema': DataFrame, 'sample': DataFrame}` |
| `execute_query(sql, dataset=...)` | `DataFrame` | Query results as pandas DataFrame |

`backend_info` summarizes the backend and dataset. Local DuckDB paths are
hidden unless `M4_PATH_DISCLOSURE=1` is set for the process.

### Clinical Notes (requires NOTES modality)

| Function | Returns | Description |
|----------|---------|-------------|
| `search_notes(query, dataset=..., note_type, limit, snippet_length)` | `dict` | `{'results': dict[str, DataFrame]}` |
| `get_note(note_id, dataset=..., max_length)` | `dict` | `{'text': str, 'subject_id': int, ...}` |
| `list_patient_notes(subject_id, dataset=..., note_type, limit)` | `dict` | `{'notes': dict[str, DataFrame]}` |

## Error Handling

M4 uses a hierarchy of exceptions. Catch specific types to handle errors appropriately:

```
M4Error (base)
├── DatasetError      # Dataset doesn't exist or not configured
├── QueryError        # SQL syntax error, table not found, query failed
└── ModalityError     # Tool incompatible with dataset (e.g., notes on tabular-only)
```

**Recovery patterns:**

```python
from m4 import execute_query, DatasetError, QueryError, ModalityError

try:
    df = execute_query("SELECT * FROM mimiciv_hosp.patients", dataset="mimic-iv")
except DatasetError as e:
    # Dataset missing, not initialized, or misspelled.
    # Recovery: check list_datasets() and m4 status --dataset mimic-iv.
    print(f"Dataset problem: {e}")
except QueryError as e:
    # SQL error or table not found
    # Recovery: check table name with get_schema(), fix SQL syntax
    print(f"Query failed: {e}")
except ModalityError as e:
    # Tried notes function on tabular-only dataset
    # Recovery: pass dataset="mimic-iv-note" to notes functions
    print(f"Modality problem: {e}")
```

## Displaying Results

Use `show()` from the vitrine module to present query results to the researcher in the browser:

```python
from m4 import execute_query
from vitrine import show

df = execute_query(
    "SELECT gender, COUNT(*) as n FROM mimiciv_hosp.patients GROUP BY gender",
    dataset="mimic-iv",
)
df.to_csv("output/demographics.csv", index=False)  # Save for reproducibility
show(df, title="Demographics", study="my-study")   # Show for review
```

For blocking review (agent waits for researcher approval), use `show(df, wait=True, prompt="Proceed?")`. For the full display API, use the `vitrine-api` skill.

## Dataset Selection

**Important:** Dataset selection is explicit. Prefer `M4Client(dataset=...)` when several calls target the same dataset, or pass `dataset=...` to each convenience function. For a long-lived session, use `client.with_dataset(...)` to create a new client for another dataset without mutating the current one. Use `client.switch_dataset(...)` only for single-session, notebook-style workflows where mutation is expected.

```python
from m4 import M4Client, execute_query

client = M4Client(dataset="mimic-iv")
df1 = client.query("SELECT COUNT(*) FROM mimiciv_hosp.patients")

eicu_client = client.with_dataset("eicu")
df2 = eicu_client.query("SELECT COUNT(*) FROM patient")

client.switch_dataset("mimic-iv-note")  # mutates client and its execution context
df3 = execute_query("SELECT COUNT(*) FROM patient", dataset="eicu")
```

## MCP Tool Equivalence

The Python API mirrors MCP tools but with better return types:

| MCP Tool | Python Function | MCP Returns | Python Returns |
|----------|-----------------|-------------|----------------|
| `execute_query` | `execute_query()` | Formatted string | `pd.DataFrame` |
| `get_database_schema` | `get_schema()` | Formatted string | `dict` with `tables` list |
| `get_table_info` | `get_table_info()` | Formatted string | `dict` with `schema`/`sample` DataFrames |

Use the Python API when you need to:
- Chain queries in analysis pipelines
- Perform pandas operations on results
- Avoid parsing formatted output


NOTE: All queries use canonical `schema.table` names (e.g., `mimiciv_hosp.patients`, `mimiciv_icu.icustays`). These names work on both the local DuckDB backend and the BigQuery backend — no need to adjust table names per backend.
