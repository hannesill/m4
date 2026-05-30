---
name: m4-setup
description: Diagnose and repair common M4 environment, dataset, skill installation, backend, and vitrine setup problems. Use when M4 tools, datasets, skills, or visualization are missing or broken.
tier: community
category: system
---

# M4 Setup And Repair

Use this skill when the M4 environment looks incomplete, a dataset is missing, skills are stale, or vitrine is unavailable.

## When to Use This Skill

- `from m4 import ...` fails or the wrong Python environment is active
- `list_datasets()` or `m4 status --all` does not show expected datasets
- M4 skills are missing, stale, or inconsistent across tools
- DuckDB/BigQuery backend configuration is wrong
- `vitrine` imports fail or the display server is not reachable

## Fast Diagnostics

Run commands from the M4 repo root unless the user is intentionally working elsewhere.

```bash
pwd
uv run python - <<'PY'
from m4 import list_datasets
print("datasets:", list_datasets())
PY
uv run m4 status --all
uv run m4 agent-env --dataset mimic-iv-demo --json
uv run m4 skills --list
uv run vitrine status
```

If plain `python` cannot import `m4`, use `uv run python`; M4 is usually installed in the project virtual environment.

## Dataset Checks

Expected built-in datasets:

| Dataset | Notes |
|---------|-------|
| `mimic-iv-demo` | Local demo tabular dataset |
| `mimic-iv` | MIMIC-IV tabular data and derived tables |
| `mimic-iv-note` | MIMIC-IV notes |
| `eicu` | eICU tabular data |

Custom datasets live under the M4 data directory in `datasets/*.json` and should
appear in `m4 status --all`. By default the data directory is `m4_data`; if
`M4_DATA_DIR` is set, it must point directly at the data directory.

Common checks:

```bash
uv run m4 agent-env --json
M4_CONFIG_DIR="${M4_HOME:-${M4_DATA_DIR:-m4_data}}"
cat "$M4_CONFIG_DIR/config.json"
find "${M4_DATA_DIR:-m4_data}/databases" -maxdepth 1 -type f -name '*.duckdb' -print
find "${M4_DATA_DIR:-m4_data}/datasets" -maxdepth 1 -type f -name '*.json' -print
```

Pass `dataset="name"` when querying, then inspect schema with `get_schema(dataset=...)` and `get_table_info(..., dataset=...)`.

## Skill Installation Repair

The canonical bundled skills are under `src/m4/skills`. Installed tool directories are generated copies.

```bash
uv run m4 skills --tools claude,codex
uv run m4 skills --list
```

Filtered installs are additive; existing non-matching skills are left in place. If an installed skill is stale, reinstall from the bundled source.

## Backend Repair

Check `${M4_HOME:-${M4_DATA_DIR:-m4_data}}/config.json`:

| Field | Meaning |
|-------|---------|
| `backend` | `duckdb` or `bigquery` |
| `bigquery_project_id` | Billing/project id for BigQuery |

For local work, `backend: "duckdb"` requires the matching file in the data
directory's `databases/` folder. For BigQuery work, credentialed datasets
require valid Google credentials and a configured project.

## Vitrine Repair

```bash
uv run python - <<'PY'
import vitrine
print("vitrine import ok")
print(vitrine.server_status())
PY
uv run vitrine restart
```

Use the `vitrine-api` skill for display API details.

## Recovery Rules

- Prefer `uv run ...` commands to avoid using the wrong environment.
- Do not guess table names. Call `get_schema(dataset=...)` and `get_table_info(..., dataset=...)`.
- If a dataset appears in `m4 status --all` but not in `list_datasets()`, check the data directory's `datasets/*.json` files and reload through the M4 API.
- If skills reference missing functions or outdated tables, compare the installed copy with `src/m4/skills` and reinstall from the canonical source.
