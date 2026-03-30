# Task: Identify Suspicion of Infection

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Identify suspected infection events by pairing systemic antibiotic
administration with culture collection within defined time windows,
following the operationalization from Seymour et al. (JAMA, 2016).

### Definition

Suspected infection requires BOTH:
1. Systemic antibiotic administration (exclude topical routes)
2. Culture collection within the time window:
   - Culture obtained up to **72 hours BEFORE** antibiotic start, OR
   - Culture obtained up to **24 hours AFTER** antibiotic start

### Matching Rules

- Each antibiotic prescription is matched to at most one culture in each
  direction (before and after)
- **Culture-before-antibiotic takes priority** when both exist
- If multiple cultures match in a direction, use the earliest
- `ab_id` = ROW_NUMBER per subject, ordered by starttime, stoptime,
  antibiotic name

### Suspected Infection Time

- If culture came BEFORE antibiotic: `suspected_infection_time` = culture time
- If antibiotic came BEFORE culture: `suspected_infection_time` = antibiotic time
- If no culture matched: `suspected_infection` = 0, `suspected_infection_time` = NULL

### Output

Output a CSV file to `{output_path}` with these exact columns:
subject_id, stay_id, hadm_id, ab_id, antibiotic, antibiotic_time, suspected_infection, suspected_infection_time, culture_time, specimen, positive_culture

One row per antibiotic prescription. The `suspected_infection` column is 1 if
the antibiotic-culture pairing criteria are met, 0 otherwise.
