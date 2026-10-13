# How the July 2026 Claude campaign was launched

Campaign root: `benchmark/results/claude-28-20260726/` (manifest created 2026-07-26T18:45:02Z).
Canonical runs started between 2026-07-26T18:45Z and 2026-07-29T10:48Z. Run-directory timestamps are UTC.

## Environment
- Every run went through `benchmark/bench.sh` inside Docker (image `m4bench:latest`, built from
  `benchmark/Dockerfile`, which pins `@anthropic-ai/claude-code@2.1.119`). All traces report that CLI version.
- Auth was staged with `benchmark/claude_login_container.sh` (result.json: `claude_auth_method: claude-login`,
  `claude_home_ephemeral: true`).
- Every result.json reports `publishable: true`, `filesystem_canary.passed: true`,
  `contamination_lint.passed: true`, `schema: native`, `resolved_reasoning_effort: medium`.
- Model strings in token usage: `claude-opus-4-7`, `claude-sonnet-4-6`.

## Launch paths
1. `benchmark/matrix.py`, used for the first batch (mimic-sepsis3-raw, mimic-urine-output-rate-raw) and the
   last batch (mimic-creatinine-baseline-raw, mimic-gcs-24h-raw, mimic-kdigo-48h). Invocations, from shell history:

       uv run python benchmark/matrix.py --agent claude --tier 1 --seeds 5 --parallel 3 \
         --skip-existing --results-root benchmark/results/claude-28-20260726

       uv run python benchmark/matrix.py --agent claude --tier 1 --seeds 5 --parallel 1 \
         --skip-existing --wait-on-claude-rate-limit --max-retries 2 \
         --results-root benchmark/results/claude-28-20260726

   For the last batch, a local task filter in matrix.py restricted the matrix to the tasks being run.
   The filter was edited between batches; code_diff.patch shows its final state.
2. Per-cell scripts that call bench.sh directly, used for the middle tasks and for gap filling
   (copied into this folder): finish_four_tasks.sh, finish_next_four_tasks.sh,
   finish_remaining_gaps.sh, finish_five_tasks.sh.
3. A small number of single bench.sh invocations typed by hand for individual retries, with the same flags
   as the scripts.

## Code version
- git HEAD f0f21bd67d9f30e733c327759d954d0480722bea, branch m4bench, identical to origin/m4bench
  (no later commits on the remote as of 2026-09-29).
- Local uncommitted differences, all captured in code_diff.patch:
  - run.py, matrix.py, tests/test_benchmark_matrix.py: rate-limit retry handling, the extended
    provider-comparison task list, treating rate-limited results as not completed, and the task filter.
    These affect which cells run and how retries behave. They do not touch the agent, the evaluator,
    task specs, or native ground truth.
  - ground_truth/obfuscated/*.sql: comment-only changes produced by rerunning benchmark/setup.py.
    Not used by native-schema runs.
- The run.py change was made at 2026-07-26T20:43Z. The 17 canonical runs that started before that
  time used run.py exactly as in f0f21bd.
- No repository file was modified after the last canonical run except two summary CSVs.

## Canonical selection
200 cells = 10 tasks x {no-skill, with-skill} x {opus, sonnet} x 5 trials. Where a cell has more than one
run directory, the newest result.json is canonical (same rule as matrix.py). The 16 older directories are
failed attempts (nonzero exit, timeout, rate limit, or no output) and are listed as superseded in the manifest.
