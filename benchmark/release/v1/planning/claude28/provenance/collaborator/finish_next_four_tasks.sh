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

for task in mimic-urine-output-rate mimic-apsiii-24h-raw mimic-sapsii-24h-raw mimic-ventilation-raw; do
  for condition in no-skill with-skill; do
    for model in opus sonnet; do
      for trial in 1 2 3 4 5; do
        run_one "$task" "$condition" "$model" "$trial"
      done
    done
  done
done

echo ""
echo "=== ALL 80 TARGETED RUNS ATTEMPTED ==="
