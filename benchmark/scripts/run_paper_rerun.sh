#!/usr/bin/env bash
# Audited v1.1 rerun campaign for the paper. Schedules 760 runs across:
#   tier 1: full NS+WS replication (28 tasks × 2 models × 5 trials = 560 runs)
#   tier 3: decoy-skill matched-context (10 tasks × 2 models × 5 trials = 100 runs)
#   tier 2: raw-SQL matched-content control (10 tasks × 2 models × 5 trials = 100 runs)
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
# After completion, set M4BENCH_PAPER_DIR if the paper is not a sibling
# checkout at ../m4bench-paper, then run the release scripts below.

set -euo pipefail

PARALLEL="${1:-4}"
RESULTS_ROOT="${2:-benchmark/results/codex-rerun-v1.1}"

cd "$(dirname "$0")/../.."   # repo root

echo "==> Building skill variants (raw-SQL + decoy)"
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
PAPER_DIR="${M4BENCH_PAPER_DIR:-../m4bench-paper}"
if [[ ! -f "${PAPER_DIR}/main.tex" ]]; then
    echo "Paper source not found at ${PAPER_DIR}. Set M4BENCH_PAPER_DIR to regenerate manuscript tables/PDF."
    exit 0
fi
export M4BENCH_PAPER_DIR="$(cd "${PAPER_DIR}" && pwd)"
export M4BENCH_M4_DIR="$(pwd)"
export M4BENCH_PAPER_ROOT="${RESULTS_ROOT}"
uv run python benchmark/release/v1/scripts/make_codex_tables.py

echo "==> Build paper PDF"
( cd "${M4BENCH_PAPER_DIR}" && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex )

echo "==> Done. Inspect ${M4BENCH_PAPER_DIR}/main.pdf"
