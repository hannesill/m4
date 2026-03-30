# Task: Identify Suspicion of Infection (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.
Note: `mimiciv_derived.antibiotic` is NOT available. You must identify systemic
antibiotics from the raw prescriptions table.

Identify suspected infection events by pairing systemic antibiotic
administration with culture collection within defined time windows.

### Definition

Suspected infection requires BOTH:
1. Systemic antibiotic administration
2. Culture collection within the time window:
   - Culture obtained up to **72 hours BEFORE** antibiotic start, OR
   - Culture obtained up to **24 hours AFTER** antibiotic start

### Identifying Systemic Antibiotics

From `mimiciv_hosp.prescriptions`, identify antibiotic prescriptions and
exclude topical routes. The following routes should be excluded:
- OU (both eyes), OS (left eye), OD (right eye)
- AU (both ears), AS (left ear), AD (right ear)
- TP (topical)

Also exclude topical formulations (creams, gels, ophthalmic ointments).

### Matching Rules

- Each antibiotic prescription is matched to at most one culture in each
  direction (before and after)
- **Culture-before-antibiotic takes priority** when both exist
- If multiple cultures match in a direction, use the earliest
  (order by chartdate NULLS FIRST, then charttime — date-only cultures
  sort before timestamped cultures on the same date)
- `ab_id` = ROW_NUMBER per subject, ordered by starttime, stoptime, antibiotic name

### Suspected Infection Time

- If culture came BEFORE antibiotic: `suspected_infection_time` = culture time
- If antibiotic came BEFORE culture: `suspected_infection_time` = antibiotic time
- If no culture matched: `suspected_infection` = 0, `suspected_infection_time` = NULL

### Culture Positivity

A culture is positive if `org_name` is non-null, non-empty, and `org_itemid != 90856`.

### Handling Cultures with Only Dates

Some cultures in `mimiciv_hosp.microbiologyevents` have `chartdate` but NULL
`charttime`. For these:
- 72h window becomes: antibiotic date >= culture date AND antibiotic date <= culture date + 3 days
- 24h window becomes: antibiotic date >= culture date - 1 day AND antibiotic date <= culture date

### Data Sources

- **Antibiotics**: `mimiciv_hosp.prescriptions` (filter for systemic routes yourself)
- **Cultures**: `mimiciv_hosp.microbiologyevents` — group by `micro_specimen_id` first

Output a CSV file to `{output_path}` with these exact columns:
subject_id, stay_id, hadm_id, ab_id, antibiotic, antibiotic_time, suspected_infection, suspected_infection_time, culture_time, specimen, positive_culture

One row per antibiotic prescription. The `suspected_infection` column is 1 if
the antibiotic-culture pairing criteria are met, 0 otherwise.
