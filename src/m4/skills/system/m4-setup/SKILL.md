---
name: m4-setup
description: Diagnose and repair an M4 installation. Use when `import m4` or `import vitrine` fails or runs under the wrong Python, a dataset is missing, not ready, or locked, the user's own CSV files are to become a dataset, the BigQuery backend or its credentials are wrong, M4's skills are missing from an agent, or the Vitrine board stops updating.
tier: community
category: system
kind: maintenance
---

# M4 setup and repair

Diagnose first; these commands only read:

```bash
m4 doctor --json          # Python, m4 and duckdb imports, backend, BigQuery project and credentials
m4 list-datasets --json   # per dataset: prepared, setup_state ("ready" when usable), derived tables
m4 agent-env --json       # data directory, M4 environment variables, path_recommendations.python
vitrine doctor --json     # Vitrine version and its Python
vitrine status --json     # this folder's study store and its server
```

Run them, and everything else, with the Python environment M4 is installed in:
`path_recommendations.python` names it (in an M4 checkout, `uv run m4 ...`).

| Symptom | Cause | Fix |
|---|---|---|
| `import m4` or `import vitrine` fails | Another Python | Use the environment above |
| `ConnectionError: Database file not found` | The dataset is not set up (`setup_state` is not `ready`) | The user sets it up: `m4 init mimic-iv-demo` downloads the open demo; credentialed datasets need their PhysioNet login. Ask before starting either |
| The user's own CSV files are not a dataset yet | Only a definition in M4's datasets folder makes them one | `m4 define-dataset NAME --src DIR --dry-run --json` lists the tables it would make. With the user's OK, run it without `--dry-run`, then `m4 init NAME --src DIR`. M4 reads `.csv` and `.csv.gz` files at most one folder deep: ask before moving or renaming the user's files. Report init's `conversion_warnings` (Latin-1, decimal commas kept as text) to the user |
| The user wants a dataset gone, to free disk or start over | `m4 remove-dataset` removes M4's copy | Only when the user asked: show them `m4 remove-dataset NAME --dry-run --json` first, then run it without `--dry-run`. Their own folder is kept. Add `--keep-definition` to keep a custom dataset defined |
| `ConnectionError: ... locked by another process` | Another process holds the DuckDB file | Wait for it, or ask the user which process to close |
| Schema `mimiciv_derived` does not exist | Derived tables are built per dataset, and only for full MIMIC-IV | `m4 init-derived mimic-iv` takes minutes: ask first. On the demo, compute concepts from the clinical skills' SQL |
| Data or settings from the wrong place | `M4_DATA_DIR` (the data folder itself) beats `M4_HOME`, which beats the nearest `m4_data` above the working directory | `m4 agent-env --json` shows what M4 resolved |
| Wrong backend, BigQuery project, or database file | `M4_BACKEND`, `M4_PROJECT_ID`, and `M4_DB_PATH` override `config.json` | If one of them is set, the user corrects or unsets it first; then `m4 backend duckdb`, or `m4 backend bigquery --project-id ID` with `GOOGLE_APPLICATION_CREDENTIALS` set |
| An agent lacks M4's skills | Not installed for that tool | `m4 skills catalog --json` lists what this M4 version ships; `m4 skills --tools claude,codex` installs them into the current project's `.claude/skills` and `.codex/skills`. When a host app manages the skills, repair through the host |
| The board shows no new cards | The script published from another folder, so to another store | `vitrine status --json` in the project folder shows its store; run the script from that folder or set `VITRINE_DATA_DIR`. `show()` starts a stopped server; a host app's board needs that same server, so let it run |
