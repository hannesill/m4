# Final Results Update

Combined evidence treats the May 4 clinician-review reruns as replacements for matching May 2 run keys.

## Codex

- Final runs: 760; rerun replacements applied: 170; cells: 152.
- Strict diagnostic passes: 87/760.
- Native task-balanced delta: 0.136 [0.085, 0.191], sign-flip p<0.0001.
- Positive tasks: 26/28.

| Task | May 2 delta | Final delta | Change |
|---|---:|---:|---:|
| `mimic-oasis-24h` | 0.057 | 0.296 | 0.239 |
| `mimic-oasis-24h-raw` | 0.042 | 0.221 | 0.179 |
| `eicu-oasis` | 0.113 | 0.272 | 0.159 |
| `mimic-creatinine-baseline-raw` | 0.140 | 0.180 | 0.040 |
| `mimic-vasopressor-equivalents-raw` | 0.099 | 0.123 | 0.024 |
| `mimic-creatinine-baseline` | 0.130 | 0.142 | 0.012 |
| `mimic-urine-output-rate` | 0.468 | 0.460 | -0.008 |
| `eicu-gcs` | 0.046 | 0.054 | 0.007 |
| `mimic-gcs-24h-raw` | 0.030 | 0.023 | -0.007 |
| `mimic-sapsii-24h` | 0.048 | 0.055 | 0.007 |

## Claude

- Final runs: 190; rerun replacements applied: 30; cells: 38.
- Strict diagnostic passes: 14/190.
- Native sentinel task-balanced delta: 0.166 [0.085, 0.259].
- Positive sentinel tasks: 8/8.

| Task | May 2 delta | Final delta | Change |
|---|---:|---:|---:|
| `mimic-oasis-24h` | 0.016 | 0.158 | 0.142 |
| `mimic-creatinine-baseline-raw` | 0.200 | 0.229 | 0.029 |
| `mimic-sepsis3-raw` | 0.047 | 0.047 | 0.000 |
| `mimic-sofa-24h-raw` | 0.001 | 0.001 | 0.000 |
| `mimic-suspicion-infection` | 0.143 | 0.143 | 0.000 |
| `mimic-urine-output-rate-raw` | 0.438 | 0.438 | 0.000 |
| `mimic-vasopressor-equivalents-raw` | 0.099 | 0.099 | 0.000 |
| `mimic-ventilation` | 0.211 | 0.211 | 0.000 |

## Exploratory local OSS

- Runs: 110; publishable runs: 0; cells: 22.
- Strict diagnostic passes: 0/110.
- Native sentinel task-balanced delta: 0.008 [-0.072, 0.088].
- Positive sentinel tasks: 3/8.
- All runs are non-publishable under the release criteria because they use the local Ollama host exception; this arm is exploratory only.

| Task | No skill | With skill | Delta |
|---|---:|---:|---:|
| `mimic-urine-output-rate-raw` | 0.000 | 0.170 | 0.170 |
| `mimic-suspicion-infection` | 0.102 | 0.256 | 0.154 |
| `mimic-creatinine-baseline-raw` | 0.219 | 0.324 | 0.105 |
| `mimic-sepsis3-raw` | 0.000 | 0.000 | 0.000 |
| `mimic-ventilation` | 0.026 | 0.000 | -0.026 |
| `mimic-oasis-24h` | 0.048 | 0.000 | -0.048 |
| `mimic-sofa-24h-raw` | 0.124 | 0.000 | -0.124 |
| `mimic-vasopressor-equivalents-raw` | 0.165 | 0.000 | -0.165 |

## Interpretation

The headline result is stable. The Codex task-balanced native skill effect moves from 0.112 to 0.136; the positive-task count remains 26/28. The largest local changes are in the clinician-reviewed OASIS tasks, with creatinine-baseline raw also increasing after rerun.

Claude remains a sentinel arm. The creatinine-baseline raw rerun increases the sentinel average, but the provider arm still covers only eight paired tasks and should not be promoted to co-primary evidence.

The local gpt-oss-20b arm is useful as a reproducibility and open-model stress test, but it should not be mixed into the primary tables: reward is near zero, gains are positive on only three of eight paired sentinel tasks, no run is publishable under the paper criteria, and egress logs are absent.
