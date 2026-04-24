---
name: gcs-calculation
description: Extract and calculate Glasgow Coma Scale (GCS) for ICU patients. Use for neurological assessment, consciousness monitoring, or trauma severity scoring.
tier: validated
category: clinical
---

# Glasgow Coma Scale (GCS) Calculation for eICU

The Glasgow Coma Scale assesses level of consciousness through three
components: Eye opening, Verbal response, and Motor response. This benchmark
task asks for the minimum first-day GCS per eICU ICU stay.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## eICU Source Tables

- `main.patient` — one row per ICU stay; use for output identifiers.
- `main.nursecharting` — primary source for GCS total and components.

The time axis is eICU offset minutes from ICU admission. For this task, include
charting from 6 hours before admission through 24 hours after admission:
`nursingchartoffset >= -360` and `nursingchartoffset <= 1440`.

## Nursecharting Labels

Use rows in `nursecharting` where `nursingchartcelltypecat` is `Scores` or
`Other Vital Signs and Infusions`.

GCS total can be charted under either of these label/name pairs:

| Label | Name |
|-------|------|
| `Glasgow coma score` | `GCS Total` |
| `Score (Glasgow Coma Scale)` | `Value` |

Components are charted under label `Glasgow coma score` with names:

| Output Component | Nursecharting Name | Normal Default |
|------------------|--------------------|----------------|
| `gcs_motor` | `Motor` | 6 |
| `gcs_verbal` | `Verbal` | 5 |
| `gcs_eyes` | `Eyes` | 4 |

## Critical Implementation Notes

1. **Validate total GCS**: Use charted total GCS only when it is numeric and
   between 3 and 15 inclusive.

2. **Component fallback**: If total GCS is not charted at a timepoint, compute
   total as `eyes + motor + verbal`, using the normal defaults above for any
   missing component at that timepoint.

3. **Minimum selection**: Return the timepoint with the lowest total GCS in the
   first-day window. If there is a tie, choose the earliest chart offset.

4. **No data default**: If a stay has no usable GCS data in the window, return
   normal values: `gcs_min = 15`, `gcs_motor = 6`, `gcs_verbal = 5`,
   `gcs_eyes = 4`.

5. **Output cardinality**: Return one row per `patientunitstayid`, including
   `uniquepid` and `patienthealthsystemstayid`.

## References

- Teasdale G, Jennett B. "Assessment of coma and impaired consciousness: A
  practical scale." Lancet. 1974;2(7872):81-84.
- MIT-LCP eICU code GCS concept, adapted to this benchmark's DuckDB schema.
