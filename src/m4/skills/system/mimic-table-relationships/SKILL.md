---
name: mimic-table-relationships
description: Join MIMIC-IV tables on the right key and time window, in the active backend's SQL dialect. Use before writing MIMIC-IV SQL that joins hosp, icu and derived tables, or when row counts look duplicated or short.
tier: community
category: system
kind: domain
---

# MIMIC-IV Table Relationships

`subject_id` (patient) → `hadm_id` (hospital admission) → `stay_id` (ICU stay). One admission can hold several ICU stays, so each event needs the right key and a time window.

## 1. Join on the key the table is recorded under

| Key | Tables |
|-----|--------|
| `stay_id` | chartevents, inputevents, ingredientevents, outputevents, procedureevents, datetimeevents. Derived: vitalsign, gcs, urine_output, `first_day_*`, scores (`sofa`: `stay_id` + `hr`) |
| `hadm_id` | admissions, diagnoses_icd, procedures_icd, prescriptions, pharmacy, emar, services. Derived: charlson |
| `subject_id` + time | labevents, microbiologyevents, omr. Derived lab panels, one row per specimen: chemistry, complete_blood_count, bg, ... |

`hadm_id` is NULL for labs and cultures taken outside an admission, including ED draws before an ICU admission: 26% of labevents and 33% of microbiologyevents in the demo, and the derived lab panels inherit the NULLs. Join these on `subject_id` plus a time window; a `hadm_id` join drops them.

`diagnoses_icd` and `procedures_icd` have no time and repeat for every ICU stay of the admission.

## 2. Bound every event by the stay's time window

Without a window, a `hadm_id` or `subject_id` join copies each event to every ICU stay of the admission or patient. M4's `first_day_lab` uses `intime - 6 h` to `intime + 24 h`:

```sql
-- Highest creatinine (itemid 50912) from 6 h before to 24 h after ICU admission
SELECT ie.stay_id, MAX(le.valuenum) AS creatinine_max
FROM mimiciv_icu.icustays ie
LEFT JOIN mimiciv_hosp.labevents le
  ON le.subject_id = ie.subject_id
 AND le.itemid = 50912
 AND le.charttime >= ie.intime - INTERVAL 6 HOUR
 AND le.charttime <= ie.intime + INTERVAL 1 DAY
GROUP BY ie.stay_id;
```

Put the window in the `LEFT JOIN ... ON` clause to keep stays without a value. Back-to-back stays can have overlapping windows, so one lab can count for both; that is intended for per-stay features.

Check a join for duplication:

```sql
SELECT COUNT(*) AS joined_rows,
       COUNT(*) - COUNT(DISTINCT le.labevent_id) AS duplicated_rows
FROM mimiciv_icu.icustays ie
JOIN mimiciv_hosp.labevents le ON le.hadm_id = ie.hadm_id;  -- unbounded: duplicates
```

## 3. Write SQL for the active backend

M4 defaults to DuckDB (`backend` in `m4 list-datasets --json`), and the derived SQL M4 builds locally is DuckDB. `schema.table` names work on both backends.

| DuckDB | BigQuery |
|--------|----------|
| `t + INTERVAL 6 HOUR` | `DATETIME_ADD(t, INTERVAL 6 HOUR)` |
| `DATE_TRUNC('hour', t)` | `DATETIME_TRUNC(t, HOUR)` |
| `DATE_DIFF('second', a, b) / 3600.0` | `DATETIME_DIFF(b, a, SECOND) / 3600` |
| `TRY_CAST(x AS INTEGER)` | `SAFE_CAST(x AS INT64)` |

DuckDB's `DATE_DIFF('hour', a, b)` counts hour boundaries crossed, not elapsed hours.

`DATETIME_ADD`, `DATETIME_SUB` or `DATETIME_DIFF` in a script mean BigQuery SQL; several clinical skills' `scripts/` are such mimic-code originals. On DuckDB, query the built `mimiciv_derived` table or translate the script.

## Derived tables

`mimiciv_derived` exists only for full MIMIC-IV: on DuckDB after `m4 init-derived mimic-iv`, on BigQuery as `physionet-data.mimiciv_derived`. The demo has none.

## References

- MIMIC-IV documentation: https://mimic.mit.edu/docs/iv/
- Johnson AEW et al. "MIMIC-IV, a freely accessible electronic health record dataset." Scientific Data. 2023;10:1.
