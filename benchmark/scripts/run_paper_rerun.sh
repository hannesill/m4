#!/usr/bin/env bash
# Audited v1.1 rerun campaign for the paper. Schedules 800 runs across:
#   tier 1: full NS+WS replication (28 tasks × 2 models × 5 trials = 560 runs)
#   tier 2: SQL-strip ablation (4 tasks × 2 models × 5 trials = 40 runs)
#   tier 3: decoy-skill matched-context (10 tasks × 2 models × 5 trials = 100 runs)
#   tier 4: raw-SQL matched-content control (10 tasks × 2 models × 5 trials = 100 runs)
#
# Usage:
#   bash benchmark/scripts/run_paper_rerun.sh [PARALLEL] [RESULTS_ROOT]
# Defaults:
#   PARALLEL=4
#   RESULTS_ROOT=benchmark/results/codex-rerun-v1.1
#
# Pre-flight:
#   1. Ensure skill variants are built:
#        uv run python benchmark/scripts/build_skill_variants.py
#   2. Ensure Docker image is current (bench.sh handles container).
#   3. Set OPENAI_API_KEY (or whichever the codex CLI expects).
#
# After completion:
#   uv run python benchmark/paper/scripts/make_codex_tables.py
#   uv run python benchmark/paper/scripts/make_supplementary.py
#   latexmk -pdf -interaction=nonstopmode benchmark/paper/main.tex

set -euo pipefail

PARALLEL="${1:-4}"
RESULTS_ROOT="${2:-benchmark/results/codex-rerun-v1.1}"

cd "$(dirname "$0")/../.."   # repo root

echo "==> Building skill variants (NO-SQL + raw-SQL + decoy)"
uv run python benchmark/scripts/build_skill_variants.py

echo "==> Verifying matrix"
uv run python benchmark/matrix.py \
    --profile rerun-v1.1 \
    --agent codex \
    --summary

echo "==> Kicking off rerun"
echo "    parallel=${PARALLEL}"
echo "    results-root=${RESULTS_ROOT}"
mkdir -p "${RESULTS_ROOT}"

uv run python benchmark/matrix.py \
    --profile rerun-v1.1 \
    --agent codex \
    --tier all \
    --parallel "${PARALLEL}" \
    --skip-existing \
    --results-root "${RESULTS_ROOT}"

echo "==> Aggregating analysis CSVs from the new results root"
uv run python benchmark/report_results.py \
    --results-root "${RESULTS_ROOT}" \
    --profile rerun-v1.1 \
    --agent codex \
    --seeds 5

echo "==> Done. Regenerating tables and figures."
export M4BENCH_PAPER_ROOT="${RESULTS_ROOT}"
uv run python benchmark/paper/scripts/make_codex_tables.py
uv run python benchmark/paper/scripts/make_supplementary.py

echo "==> Build paper PDF"
( cd benchmark/paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex )

echo "==> Done. Inspect benchmark/paper/main.pdf"
