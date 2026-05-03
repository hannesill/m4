# M4Bench Reviewer Reproduction Guide

This guide describes the release-facing path for rebuilding the benchmark
artifacts and rerunning the audited Codex campaign. It assumes a fresh checkout
of this repository, Docker, `uv`, and credentialed PhysioNet access to MIMIC-IV
v3.1 and eICU-CRD v2.0.

The default `benchmark/matrix.py` profile is the audited v1.1 submission
profile. The explicit `--profile rerun-v1.1` flag is retained as a stable alias
for provenance and for scripts or logs that cite the v1.1 design.

## 1. Environment

From the repository root:

```bash
uv sync
uv run pytest
```

Install Docker and confirm the daemon is running:

```bash
docker version
```

For Codex runs, authenticate either with the Codex CLI or with an API key:

```bash
codex login
```

or create `benchmark/.env`:

```bash
OPENAI_API_KEY=sk-...
```

`benchmark/bench.sh` stages only allowlisted auth files or environment keys into
per-run containers; it does not mount user-global agent histories or benchmark
answer directories into the agent runtime.

## 2. Download Credentialed Data

Complete PhysioNet credentialing and accept the data use agreements for:

- MIMIC-IV v3.1: `https://physionet.org/files/mimiciv/3.1/`
- eICU Collaborative Research Database v2.0:
  `https://physionet.org/files/eicu-crd/2.0/`

Download the raw CSV files into the locations expected by M4:

```bash
mkdir -p m4_data/raw_files/mimic-iv m4_data/raw_files/eicu

wget -r -N -c -np --cut-dirs=2 -nH --user YOUR_USERNAME --ask-password \
  https://physionet.org/files/mimiciv/3.1/ \
  -P m4_data/raw_files/mimic-iv

wget -r -N -c -np --cut-dirs=2 -nH --user YOUR_USERNAME --ask-password \
  https://physionet.org/files/eicu-crd/2.0/ \
  -P m4_data/raw_files/eicu
```

Expected layout after download:

```text
m4_data/raw_files/mimic-iv/hosp/*.csv.gz
m4_data/raw_files/mimic-iv/icu/*.csv.gz
m4_data/raw_files/eicu/*.csv.gz
```

## 3. Initialize M4 Databases

Convert raw CSVs to Parquet and create DuckDB databases:

```bash
printf "n\n" | uv run m4 init mimic-iv
uv run m4 init-derived mimic-iv
uv run m4 init eicu
```

The benchmark expects these source databases:

```text
m4_data/databases/mimic_iv.duckdb
m4_data/databases/eicu.duckdb
```

If a previous database was created with an older schema layout, rebuild it:

```bash
printf "n\n" | uv run m4 init mimic-iv --force
uv run m4 init-derived mimic-iv --force
uv run m4 init eicu --force
```

## 4. Build Benchmark Artifacts

Create task-specific agent databases and deterministic ground truth files:

```bash
uv run python benchmark/setup.py --all --verify
```

Build transformed schema probes used by the contamination/readiness checks:

```bash
uv run python benchmark/setup.py --schema obfuscated --all
uv run python benchmark/setup.py --schema restructured --all
uv run python benchmark/setup.py --verify-equivalence
```

Generated artifacts are intentionally not committed:

```text
benchmark/agent_db/
benchmark/ground_truth/*.csv.gz
benchmark/ground_truth/*.manifest.json
benchmark/results/
```

The tracked SQL, task definitions, evaluator, and scripts are sufficient to
regenerate them from the credentialed source data.

## 5. Preflight and Isolation Canary

Run preflight before any release-grade campaign:

```bash
uv run python benchmark/preflight.py \
  --results-root benchmark/results/reviewer-canary-YYYYMMDD
```

Then run the adversarial filesystem canary through the same Docker-backed path
used for model runs:

```bash
bash benchmark/bench.sh \
  --leak-canary \
  --agent codex \
  --model gpt-5.4-mini \
  --results-root benchmark/results/reviewer-canary-YYYYMMDD
```

The canary must report that the agent cannot read `benchmark/ground_truth`,
`benchmark/tasks`, `benchmark/agent_db`, previous `benchmark/results`, evaluator
internals, or auth staging directories.

## 6. Smoke Test

Before launching the full campaign, run one Docker-backed benchmark attempt:

```bash
bash benchmark/bench.sh \
  --task mimic-sirs-24h \
  --condition no-skill \
  --agent codex \
  --model gpt-5.4-mini \
  --trial 1 \
  --results-root benchmark/results/reviewer-smoke-YYYYMMDD
```

Aggregate the smoke result:

```bash
uv run python benchmark/report_results.py \
  --results-root benchmark/results/reviewer-smoke-YYYYMMDD \
  --profile rerun-v1.1 \
  --agent codex \
  --seeds 5
```

The smoke root will be incomplete relative to the v1.1 matrix; this is expected.
Use it only to verify local execution, result JSON writing, and analysis export.

## 7. Full v1.1 Campaign

The full audited submission campaign schedules 800 Codex runs:

- Tier 1: 28 native tasks, no-skill and with-skill, 2 models, 5 trials
- Tier 2: SQL-stripped skill ablation on 4 tasks
- Tier 3: decoy-skill matched-context control on 10 tasks
- Tier 4: raw-SQL matched-content control on 10 tasks

Run through the wrapper script:

```bash
bash benchmark/scripts/run_paper_rerun.sh \
  4 \
  benchmark/results/codex-rerun-v1.1
```

The first argument is parallelism. Choose a value that fits local API rate
limits, Docker capacity, and disk throughput.

Equivalent explicit matrix command:

```bash
uv run python benchmark/matrix.py \
  --agent codex \
  --tier all \
  --parallel 4 \
  --skip-existing \
  --results-root benchmark/results/codex-rerun-v1.1
```

The following command is equivalent and retained for exact provenance:

```bash
uv run python benchmark/matrix.py \
  --profile rerun-v1.1 \
  --agent codex \
  --tier all \
  --parallel 4 \
  --skip-existing \
  --results-root benchmark/results/codex-rerun-v1.1
```

Resume interrupted runs with the same command and `--skip-existing`. Skip logic
matches task, condition, model, schema, reasoning-effort policy, and trial id.

## 8. Regenerate Analysis Outputs

If the wrapper script completed, it already runs the analysis export. To rerun
it manually:

```bash
uv run python benchmark/report_results.py \
  --results-root benchmark/results/codex-rerun-v1.1 \
  --profile rerun-v1.1 \
  --agent codex \
  --seeds 5
```

Expected analysis outputs:

```text
benchmark/results/codex-rerun-v1.1/analysis/runs.csv
benchmark/results/codex-rerun-v1.1/analysis/cells.csv
benchmark/results/codex-rerun-v1.1/analysis/native_skill_deltas.csv
benchmark/results/codex-rerun-v1.1/analysis/control_condition_summary.csv
benchmark/results/codex-rerun-v1.1/analysis/CODEX_FULL_REPORT.md
```

Paper sources are intentionally local-only in this repository. If you have the
private `benchmark/paper/` tree locally, use its scripts against the exported
analysis directory to regenerate manuscript tables and figures.

## 9. Supplementary Provider Runs

Provider-comparison campaigns are supplementary and should not be reported as
powered benchmark-wide estimates:

```bash
uv run python benchmark/matrix.py \
  --profile provider-comparison \
  --agent claude \
  --tier all \
  --parallel 2 \
  --skip-existing \
  --results-root benchmark/results/claude-provider-YYYYMMDD
```

For Claude Docker-backed runs, use the login helper first:

```bash
bash benchmark/claude_login_container.sh
```

For local open-source Pi/Ollama runs, follow the Pi/Ollama setup in
`benchmark/README.md`.

## 10. Known Practical Notes

- The full v1.1 campaign is API- and time-intensive. Record wall time, model
  versions, CLI versions, and total cost for any released rerun.
- The normal preflight is the required gate. The optional
  `--ground-truth-self-check` evaluates every answer file against itself and can
  be slow on large local datasets.
- Do not report local `benchmark/run.py` debugging runs as release-grade
  evidence. Release-grade evidence must go through `benchmark/bench.sh` or an
  equivalent isolation path.
- Because source clinical data are credentialed, reviewers must obtain MIMIC-IV
  and eICU access through PhysioNet; generated CSV answers and per-run outputs
  should be released only if they comply with the relevant data use agreements.
