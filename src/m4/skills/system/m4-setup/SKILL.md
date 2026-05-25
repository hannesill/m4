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
from m4 import list_datasets, get_active_dataset
print("active:", get_active_dataset())
print("datasets:", list_datasets())
PY
uv run m4 status --all
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

Custom datasets live in `m4_data/datasets/*.json` and should appear in `m4 status --all`.

Common checks:

```bash
cat m4_data/config.json
find m4_data/databases -maxdepth 1 -type f -name '*.duckdb' -print
find m4_data/datasets -maxdepth 1 -type f -name '*.json' -print
```

Use `set_dataset("name")` before querying, then inspect schema with `get_schema()` and `get_table_info()`.

## Skill Installation Repair

The canonical bundled skills are under `src/m4/skills`. Installed tool directories are generated copies.

```bash
uv run m4 skills --tools claude,codex
uv run m4 skills --list
```

Filtered installs are additive; existing non-matching skills are left in place. If an installed skill is stale, reinstall from the bundled source.

## Backend Repair

Check `m4_data/config.json`:

| Field | Meaning |
|-------|---------|
| `backend` | `duckdb` or `bigquery` |
| `active_dataset` | Dataset used by API calls |
| `bigquery_project_id` | Billing/project id for BigQuery |

For local work, `backend: "duckdb"` requires the matching file in `m4_data/databases`. For BigQuery work, credentialed datasets require valid Google credentials and a configured project.

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
- Do not guess table names. Call `get_schema()` and `get_table_info()` after `set_dataset()`.
- If a dataset appears in `m4 status --all` but not in `list_datasets()`, check `m4_data/datasets/*.json` and reload through the M4 API.
- If skills reference missing functions or outdated tables, compare the installed copy with `src/m4/skills` and reinstall from the canonical source.
