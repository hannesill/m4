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

# mimic-sepsis3-raw (3 missing)
run_one mimic-sepsis3-raw no-skill sonnet 5
run_one mimic-sepsis3-raw with-skill sonnet 2
run_one mimic-sepsis3-raw with-skill sonnet 5

# mimic-urine-output-rate-raw (5 missing)
run_one mimic-urine-output-rate-raw with-skill opus 4
run_one mimic-urine-output-rate-raw with-skill opus 5
run_one mimic-urine-output-rate-raw with-skill sonnet 1
run_one mimic-urine-output-rate-raw with-skill sonnet 2
run_one mimic-urine-output-rate-raw with-skill sonnet 5

# mimic-sofa-24h-raw (11 missing)
run_one mimic-sofa-24h-raw no-skill sonnet 5
run_one mimic-sofa-24h-raw with-skill opus 1
run_one mimic-sofa-24h-raw with-skill opus 2
run_one mimic-sofa-24h-raw with-skill opus 3
run_one mimic-sofa-24h-raw with-skill opus 4
run_one mimic-sofa-24h-raw with-skill opus 5
run_one mimic-sofa-24h-raw with-skill sonnet 1
run_one mimic-sofa-24h-raw with-skill sonnet 2
run_one mimic-sofa-24h-raw with-skill sonnet 3
run_one mimic-sofa-24h-raw with-skill sonnet 4
run_one mimic-sofa-24h-raw with-skill sonnet 5

# mimic-suspicion-infection-raw (14 missing)
run_one mimic-suspicion-infection-raw no-skill opus 3
run_one mimic-suspicion-infection-raw no-skill sonnet 3
run_one mimic-suspicion-infection-raw no-skill sonnet 4
run_one mimic-suspicion-infection-raw no-skill sonnet 5
run_one mimic-suspicion-infection-raw with-skill opus 1
run_one mimic-suspicion-infection-raw with-skill opus 2
run_one mimic-suspicion-infection-raw with-skill opus 3
run_one mimic-suspicion-infection-raw with-skill opus 4
run_one mimic-suspicion-infection-raw with-skill opus 5
run_one mimic-suspicion-infection-raw with-skill sonnet 1
run_one mimic-suspicion-infection-raw with-skill sonnet 2
run_one mimic-suspicion-infection-raw with-skill sonnet 3
run_one mimic-suspicion-infection-raw with-skill sonnet 4
run_one mimic-suspicion-infection-raw with-skill sonnet 5

echo ""
echo "=== ALL 33 TARGETED RUNS ATTEMPTED ==="
