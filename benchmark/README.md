# M4Bench

Benchmark for evaluating AI agents' ability to derive validated clinical concepts
from real EHR databases. 15 task families (28 tasks) covering severity scores,
organ failure staging, comorbidity indices, infection detection, medication data,
and temporal event classification. Ground truth SQL is adapted from MIT-LCP
mimic-code with benchmark-specific conventions documented inline, such as
treating missing component scores as normal when the task instruction requires
that behavior.

## Design

Each task asks an agent to compute a clinical concept (e.g., SOFA score, KDIGO
AKI staging, Charlson comorbidity index) from a MIMIC-IV DuckDB database. The
agent's output CSV is compared column-by-column against ground truth generated
from validated mimic-code concepts adapted to the benchmark's explicit task
semantics.

Tasks come in two modes:
- **standard** — validated target tables are removed, but intermediate feature
  tables (e.g., `first_day_vitalsign`) are available
- **raw** — the target table and task-relevant upstream derived tables are
  removed, forcing the agent to rebuild the requested concept from source
  tables or remaining non-target context. Raw mode is not a guarantee that the
  entire `mimiciv_derived` schema is absent.

Two primary experimental conditions:
- **no-skill** — agent receives only the task instruction
- **with-skill** — a task-specific clinician-reviewed skill is injected

A supplementary condition, **with-skill-all** (all benchmark skills injected),
probes whether skill discovery works when the agent must find relevant knowledge
from a larger library. This is a Tier 6 noise probe, not the headline comparison.

**Information gradient**: Task instructions describe the clinical concept
accurately but are intentionally underspecified on dataset-specific
implementation details (encoding conventions, sentinel values, item IDs,
edge-case handling). Skills fill that gap with MIMIC-specific procedural
knowledge. This creates a measurable difference between what an agent can
figure out from schema exploration alone versus what it gets from
clinician-reviewed guidance.

Benchmark skill snapshots are intentionally benchmark-safe: they should not
include runnable examples that query dropped target concept tables, and they do
not ship the production SQL scripts. Run `python benchmark/preflight.py` before
launching a paper campaign to check that this separation still holds.

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
runs.** `benchmark/matrix.py` now uses `bench.sh` by default for execution, so
matrix-driven campaigns can be publishable as long as they use a fresh
`--results-root`. Local execution is still useful for development and anomaly
investigation, but those runs should not be reported as benchmark evidence.

The benchmark now supports isolated per-run workdirs and per-run HOME
directories, but outside Docker the root-owned directory protections and
`benchagent` user isolation are absent. Use `bench.sh` for any run intended for
publication or formal comparison.

## Paper Plan

The canonical paper-facing execution spec lives in
`benchmark/PAPER.md`, and `benchmark/matrix.py` contains the current
pilot-informed execution plan.

## Usage

```bash
# Setup (creates agent DB and ground truth for a task)
python benchmark/setup.py --task mimic-sirs-24h
python benchmark/setup.py --all

# Preflight before paper-quality runs
python benchmark/preflight.py

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

# Paper-quality GPT-primary matrix campaign (Docker-backed)
python benchmark/matrix.py --tier 1 --agent codex --results-root benchmark/results/paper-20260406

# Sparse external-provider comparison
python benchmark/matrix.py --profile provider-comparison --agent claude --results-root benchmark/results/paper-20260406-claude-sentinel
```

## Evaluation

Reward is the mean per-column match rate (0.0–1.0) between the agent's output
and ground truth. Per-column tolerances are configurable in each task's
`task.toml`. Pytest-based assertions provide pass/fail diagnostics on row
coverage, required columns, and per-criterion accuracy.

## Supported Agents

Claude Code, Codex, Gemini CLI. See `AGENT_COMMANDS` in `run.py` for configuration.

For Codex CLI, the harness uses `codex exec --dangerously-bypass-approvals-and-sandbox`
because Docker already provides the outer sandbox, and it injects task
skills into `.codex/skills/` inside each run workdir. Authenticate first with
`codex login` if you want to use ChatGPT subscription access instead of an API
key.

`benchmark/matrix.py` uses agent-specific default model sets:
- Claude: `opus`, `sonnet`
- Codex: `gpt-5.5`, `gpt-5.4-mini`
- Gemini: `gemini-3.1-pro-preview`, `gemini-3-flash-preview`

The default matrix profile is GPT-primary: run the powered campaign with
`--agent codex`, then use `--profile provider-comparison` for sparse Claude or
Gemini sentinel runs. Provider-comparison runs are supplementary and should not
be described as powered benchmark-wide estimates.

Reasoning policy is pinned by default through `--reasoning-effort auto`: Codex
and Claude Code run at `medium`, while Gemini CLI is recorded as
`provider-default` because it does not expose the same named effort scale. Pass
`--reasoning-effort default` to leave each CLI/provider default untouched, or an
explicit supported level for Codex/Claude ablations.

For Claude subscription campaigns, the matrix executes one `bench.sh` run per
cell so the host can refresh OAuth-backed auth between Docker runs. Do not
store expiring Claude OAuth tokens in `benchmark/.env`; that file should only
hold stable Anthropic API keys. Subscription-backed Claude runs should come
from `claude login` on macOS so `bench.sh` can pull a fresh keychain token.
