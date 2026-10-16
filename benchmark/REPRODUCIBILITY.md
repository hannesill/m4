# M4Bench Reproduction Guide

This guide describes the release-facing path for rebuilding the benchmark
artifacts and rerunning the audited Codex campaign. It assumes a fresh checkout
of this repository, Docker, `uv`, and credentialed PhysioNet access to MIMIC-IV
v3.1 and eICU-CRD v2.0.

The default `benchmark/matrix.py` profile is the paper's primary profile,
called v1.1 in scripts and logs. The explicit `--profile rerun-v1.1` flag is a
stable alias for it.

## 1. Environment

From the repository root:

```bash
uv sync
uv run pytest
```

Benchmark-specific coverage lives in `tests/test_benchmark_*.py` and
`tests/test_release_*.py`; the full
pytest command above also exercises the surrounding M4 data and CLI plumbing
used by the benchmark.

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
  --results-root benchmark/results/canary-YYYYMMDD
```

Then run the adversarial filesystem canary through the same Docker-backed path
used for model runs:

```bash
bash benchmark/bench.sh \
  --leak-canary \
  --agent codex \
  --model gpt-5.4-mini \
  --results-root benchmark/results/canary-YYYYMMDD
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
  --results-root benchmark/results/smoke-YYYYMMDD
```

Aggregate the smoke result:

```bash
uv run python benchmark/report_results.py \
  --results-root benchmark/results/smoke-YYYYMMDD \
  --profile rerun-v1.1 \
  --agent codex \
  --seeds 5
```

The smoke root will be incomplete relative to the v1.1 matrix; this is expected.
Use it only to verify local execution, result JSON writing, and analysis export.

## 7. Full v1.1 Campaign

The full audited submission campaign schedules 760 Codex runs:

- Tier 1: 28 native tasks, no-skill and with-skill, 2 models, 5 trials
- Tier 2: raw-SQL matched-content control on 10 tasks
- Tier 3: decoy-skill matched-context control on 10 tasks

Canonical with-skill artifacts are SQL-free. Raw SQL is used only in the
explicit matched-content control.

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

## 7a. Validity Follow-Ups

Two targeted follow-up profiles address the main construct-validity
questions without rerunning the full v1.1 matrix:

```bash
uv run python benchmark/matrix.py \
  --profile operational-spec \
  --agent codex \
  --tier all \
  --parallel 4 \
  --skip-existing \
  --results-root benchmark/results/codex-operational-spec-YYYYMMDD
```

The `operational-spec` profile schedules the eight native-schema sentinel tasks
under the `operational-spec` condition. Each scheduled task must include a
task-local `operational-spec.md` file; this file should provide formulas, output
grain, time-window rules, missingness conventions, precedence rules,
tie-breakers, scoring bins, and tolerances while excluding task-specific SQL,
dataset item IDs, and reference-code recipes.

```bash
uv run python benchmark/matrix.py \
  --profile schema-skill \
  --agent codex \
  --tier all \
  --parallel 4 \
  --skip-existing \
  --results-root benchmark/results/codex-schema-skill-YYYYMMDD
```

The `schema-skill` profile schedules transformed-schema `with-skill` runs over
MIMIC tasks with both obfuscated and restructured task databases. Use `--profile
validity-followup` to run both follow-up tiers into one result root.

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

The benchmark release tree includes frozen planning metadata and generated
tables under `benchmark/release/v1/`, so the analysis can be inspected
without the manuscript checkout. If you intentionally
want to regenerate tables into a separate manuscript workspace, set
`M4BENCH_PAPER_DIR` and `M4BENCH_M4_DIR` explicitly:

```bash
export M4BENCH_PAPER_DIR=/path/to/m4bench-paper
export M4BENCH_M4_DIR=/path/to/m4
export M4BENCH_PAPER_ROOT=benchmark/results/codex-rerun-v1.1
uv run python benchmark/release/v1/scripts/make_codex_tables.py
```

To regenerate the final submitted tables from the frozen release and rerun
roots, use:

```bash
export M4BENCH_PAPER_DIR=/path/to/m4bench-paper
export M4BENCH_M4_DIR=/path/to/m4
uv run python benchmark/release/v1/scripts/make_release_metadata.py
uv run python benchmark/release/v1/scripts/make_final_results.py
uv run python benchmark/release/v1/scripts/make_followup_manifest.py
uv run python benchmark/release/v1/scripts/make_followup_tables.py
```

Those commands need the retained run roots and credentialed reference outputs.
Without credentialed data, regenerate and check the camera-ready tables from
the open evidence packages instead:

```bash
python3 benchmark/release/v1/scripts/verify_public_evidence.py evidence       # July Claude package
uv run python benchmark/release/v1/scripts/verify_public_evidence.py evidence-submission  # submitted campaigns
python3 benchmark/release/v1/scripts/make_claude28_tables.py --check
```

See `benchmark/release/v1/README.md` ("Camera-Ready Release") for package
checksums, what each check covers, and the tables that still need private
evidence.

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

The July 2026 full-coverage Claude replication (28 tasks x Opus/Sonnet x
no-skill/with-skill x 5 trials) was launched in several batches from two
machines; the retained commands, batch scripts, and source diffs are in
`benchmark/release/v1/planning/claude28/provenance/`. Those batches mixed
Claude Code versions (2.1.119 and 2.1.220) and model-routing settings. A new
campaign intended as a uniform-harness contrast should freeze one CLI version,
one routing policy, and one source commit for every cell, use a fresh results
root, and record all three in the campaign manifest.

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
- Source clinical data are credentialed: obtain MIMIC-IV and eICU access
  through PhysioNet. Reference outputs, agent `output.csv` files, and raw traces
  hold row-level derived data and must not be shared.
- Treat raw run directories as secret-bearing. The agent container holds the
  agent CLI's own login file (for example `~/.codex/auth.json`), and an agent
  exploring the container can print it into its trace. Use a dedicated
  account or API key for campaigns, and publish run evidence only through
  `release/v1/scripts/package_public_evidence.py` followed by
  `scan_public_evidence.py`.
- Record the git commit, working-tree state, and container image digest for
  each campaign. `release/v1/README.md` describes the code state behind the
  released campaigns.
