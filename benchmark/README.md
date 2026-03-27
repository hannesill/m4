# ClinSkillsBench

Benchmark for evaluating whether procedural clinical skills improve AI agents' ability to compute validated clinical scores from raw ICU database tables, using MIT-LCP mimic-code derived tables as ground truth.

## Design

Each task asks an agent to compute a clinical concept (e.g., SIRS criteria) from a MIMIC-IV DuckDB database. The agent's output CSV is compared column-by-column against ground truth generated from mimic-code's validated SQL.

Tasks come in two modes:
- **standard** — pre-computed intermediate tables (e.g., `first_day_vitalsign`) are available
- **raw** — intermediate tables are dropped, forcing the agent to work from base tables

Three experimental conditions:
- **no-skill** — agent receives only the task instruction
- **with-skill** — a clinician-reviewed M4 skill is injected into the agent's context
- **self-generated** — agent is prompted to write its own procedural skill before solving

## Structure

```
benchmark/
  run.py           # Harness: task setup -> agent invocation -> evaluation
  evaluate.py      # Standalone evaluation against ground truth
  setup.py         # Database and ground truth preparation
  lib/             # Shared utilities (comparison, test runner, sandbox)
  tasks/           # Task definitions (instruction, skills, config)
  ground_truth/    # Ground truth SQL and generated CSVs (gzipped)
  agent_db/        # Task-specific DuckDB databases (intermediates selectively dropped)
  results/         # Run outputs (agent traces, CSVs, result JSON)
```

## Usage

```bash
# Setup (creates agent DB and ground truth for a task)
python benchmark/setup.py --task mimic-sirs-24h

# Run agent with skill
python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude

# Run agent without skill
python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude

# Isolated mode (sandboxed filesystem, no network)
python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude --isolated
```

## Evaluation

Reward is the mean per-column match rate (0.0-1.0) between the agent's output and ground truth. Pytest-based assertions provide pass/fail diagnostics on row coverage, required columns, and per-criterion accuracy.

## Supported agents

Claude Code, Codex, Gemini CLI. See `AGENT_COMMANDS` in `run.py` for configuration.
