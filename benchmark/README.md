# M4Bench

Benchmark for evaluating AI agents' ability to derive validated clinical concepts
from real EHR databases. 15 task families (28 tasks) covering severity scores,
organ failure staging, comorbidity indices, infection detection, medication data,
and temporal event classification. Ground truth from MIT-LCP mimic-code.

## Design

Each task asks an agent to compute a clinical concept (e.g., SOFA score, KDIGO
AKI staging, Charlson comorbidity index) from a MIMIC-IV DuckDB database. The
agent's output CSV is compared column-by-column against ground truth generated
from mimic-code's validated SQL.

Tasks come in two modes:
- **standard** — pre-computed intermediate tables (e.g., `first_day_vitalsign`) are available
- **raw** — intermediate tables are dropped, forcing the agent to work from base tables

Three experimental conditions:
- **no-skill** — agent receives only the task instruction
- **with-skill** — a task-specific clinician-reviewed skill is injected
- **with-skill-all** — all benchmark skills injected (real-world deployment scenario)

**Information gradient**: Task instructions describe the clinical concept
accurately but are intentionally underspecified on dataset-specific
implementation details (encoding conventions, sentinel values, item IDs,
edge-case handling). Skills fill that gap with MIMIC-specific procedural
knowledge. This creates a measurable difference between what an agent can
figure out from schema exploration alone versus what it gets from
clinician-reviewed guidance.

A contamination analysis dimension (`--schema`) tests memorization vs genuine
understanding by running tasks on obfuscated (renamed) and restructured
(merged/denormalized) versions of MIMIC-IV.

## Task Families

| Family | Tasks | Category | Key challenge |
|--------|-------|----------|---------------|
| SOFA | 2 | Severity score | 6-organ subscore aggregation, vasopressor doses |
| SIRS | 1 | Severity score | Vital sign thresholds, WBC count (raw-only) |
| SAPS-II | 2 | Severity score | 15 physiological variables + admission type |
| APSIII | 2 | Severity score | Worst-from-normal scoring, 16 variables |
| OASIS | 3 | Severity score | Vitals-only (no labs), pre-ICU LOS, eICU cross-database |
| GCS | 2 | Neurological | Component extraction, intubated patient handling, eICU cross-database |
| MELD | 2 | Organ failure | Logarithmic formula, sodium adjustment |
| KDIGO | 2 | Organ failure | Creatinine + urine output AKI staging |
| Charlson | 1 | Comorbidity | ICD code mapping with hierarchy rules (raw-only) |
| Baseline creatinine | 2 | Estimation | Decision tree + ICD lookup + MDRD formula |
| Ventilation | 2 | Classification | Episode detection, 14h gap rule, device string matching |
| Suspicion of infection | 2 | Temporal matching | Asymmetric time window (72h before / 24h after) |
| Sepsis-3 | 1 | Compositional | SOFA ≥ 2 + suspected infection (raw-only, depends on two sub-concepts) |
| Vasopressor equivalents | 2 | Medication | NE-equivalent dose, unit conversion |
| Urine output rate | 2 | Data engineering | Rolling windows, LAG functions, weight normalization |

## Structure

```
benchmark/
  run.py           # Harness: task setup → agent invocation → evaluation
  evaluate.py      # Standalone evaluation against ground truth
  setup.py         # Database and ground truth preparation
  bench.sh         # Docker wrapper for reproducible execution
  lib/             # Shared utilities (comparison, test runner, transforms, sandbox)
  tasks/           # Task definitions (instruction, skills, config) — 15 families
  ground_truth/    # Ground truth SQL and generated CSVs (gzipped)
  agent_db/        # Task-specific DuckDB databases (intermediates selectively dropped)
  results/         # Run outputs (agent traces, CSVs, result JSON)
```

## Evaluation Integrity

**Docker via `bench.sh` is the only valid evaluation mode for paper-quality
runs.** Local `python benchmark/run.py` execution is still useful for
development and debugging, including anomaly investigation, but those runs
should not be reported as benchmark evidence.

The benchmark now supports isolated per-run workdirs and per-run HOME
directories, but outside Docker the root-owned directory protections and
`benchagent` user isolation are absent. Use `bench.sh` for any run intended for
publication or formal comparison.

## Paper Plan

The canonical paper-facing execution spec lives in
`benchmark/PAPER.md`. `benchmark/METHOD.md` is retained only as historical
design context, and `benchmark/matrix.py` contains the current pilot-informed
execution plan.

## Usage

```bash
# Setup (creates agent DB and ground truth for a task)
python benchmark/setup.py --task mimic-sirs-24h
python benchmark/setup.py --all

# Run a single task
python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude

# Run all tasks in a family
python benchmark/run.py --family sofa --condition no-skill --agent claude

# Run all tasks with multiple seeds
python benchmark/run.py --all --condition no-skill --agent claude --seeds 3

# Run only raw-mode tasks (e.g., for contamination analysis)
python benchmark/run.py --all --mode raw --condition no-skill --agent claude

# Run on obfuscated schema (contamination analysis)
python benchmark/run.py --task mimic-sirs-24h-raw --condition no-skill --schema obfuscated

# Parallel execution
python benchmark/run.py --all --condition no-skill --agent claude --parallel 4
```

## Evaluation

Reward is the mean per-column match rate (0.0–1.0) between the agent's output
and ground truth. Per-column tolerances are configurable in each task's
`task.toml`. Pytest-based assertions provide pass/fail diagnostics on row
coverage, required columns, and per-criterion accuracy.

## Supported Agents

Claude Code, Codex, Gemini CLI. See `AGENT_COMMANDS` in `run.py` for configuration.

For Codex CLI, the harness uses `codex exec --full-auto` and injects task
skills into `.codex/skills/` inside each run workdir. Authenticate first with
`codex login` if you want to use ChatGPT subscription access instead of an API
key.
