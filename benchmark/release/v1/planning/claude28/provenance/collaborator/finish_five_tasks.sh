#!/usr/bin/env bash
set -uo pipefail

RESULTS_ROOT="benchmark/results/claude-28-20260726"

run_one() {
  local task="$1" condition="$2" model="$3" trial="$4"
  echo ""
  echo "=== $task | $condition | $model | trial=$trial ==="
  bash benchmark/bench.sh \
    --task "$task" \
    --condition "$condition" \
    --agent claude \
    --model "$model" \
    --trial "$trial" \
    --results-root "$RESULTS_ROOT" \
    --max-retries 2 \
    --retry-delay-seconds 15 \
    --wait-on-claude-rate-limit
}

run_one mimic-urine-output-rate with-skill sonnet 5
run_one mimic-sofa-24h-raw with-skill sonnet 3
run_one mimic-suspicion-infection-raw with-skill opus 4
run_one mimic-suspicion-infection-raw with-skill opus 5
run_one mimic-suspicion-infection-raw with-skill sonnet 5
run_one mimic-apsiii-24h-raw no-skill opus 5
run_one mimic-apsiii-24h-raw no-skill sonnet 3
run_one mimic-apsiii-24h-raw with-skill opus 5
run_one mimic-apsiii-24h-raw with-skill sonnet 1
run_one mimic-apsiii-24h-raw with-skill sonnet 2
run_one mimic-apsiii-24h-raw with-skill sonnet 3
run_one mimic-apsiii-24h-raw with-skill sonnet 4
run_one mimic-apsiii-24h-raw with-skill sonnet 5
run_one mimic-ventilation-raw no-skill opus 1
run_one mimic-ventilation-raw no-skill opus 2
run_one mimic-ventilation-raw no-skill opus 3
run_one mimic-ventilation-raw no-skill opus 4
run_one mimic-ventilation-raw no-skill opus 5
run_one mimic-ventilation-raw no-skill sonnet 1
run_one mimic-ventilation-raw no-skill sonnet 2
run_one mimic-ventilation-raw no-skill sonnet 3
run_one mimic-ventilation-raw no-skill sonnet 4
run_one mimic-ventilation-raw no-skill sonnet 5
run_one mimic-ventilation-raw with-skill opus 1
run_one mimic-ventilation-raw with-skill opus 2
run_one mimic-ventilation-raw with-skill opus 3
run_one mimic-ventilation-raw with-skill opus 4
run_one mimic-ventilation-raw with-skill opus 5
run_one mimic-ventilation-raw with-skill sonnet 3

echo ""
echo "=== ALL 29 GAP RUNS ATTEMPTED ==="
