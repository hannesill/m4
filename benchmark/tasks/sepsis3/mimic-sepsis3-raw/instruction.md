# Task: Identify Sepsis-3 Patients (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and some pre-computed intermediate tables in `mimiciv_derived`.
Note: `mimiciv_derived.sepsis3`, `mimiciv_derived.sofa`, and
`mimiciv_derived.suspicion_of_infection` are NOT available. You must
derive these concepts from the available tables.

Identify patients meeting the Sepsis-3 criteria
(Singer et al., JAMA, 2016; Seymour et al., JAMA, 2016).

### Sepsis-3 Definition

A patient has sepsis when:
1. **SOFA score >= 2** (using 24-hour rolling worst values)
2. **Suspected infection** (systemic antibiotic + culture within time window)
3. The SOFA measurement time falls within **48 hours before** to
   **24 hours after** the suspected infection time

### First Event Selection

Return only the first suspected infection event per stay, using
ROW_NUMBER ordered by:
1. `suspected_infection_time` (NULLS FIRST)
2. `antibiotic_time` (NULLS FIRST)
3. `culture_time` (NULLS FIRST)
4. SOFA measurement time (NULLS FIRST)

### Requirements

- `sepsis3` column: TRUE when sofa_score >= 2 AND suspected_infection = 1
- One row per ICU stay (earliest matching event)
- `sofa_time` is the SOFA measurement endtime
- Include SOFA component scores (respiration, coagulation, liver,
  cardiovascular, cns, renal) at the matching SOFA time

Output a CSV file to `{output_path}` with these exact columns:
subject_id, stay_id, antibiotic_time, culture_time, suspected_infection_time,
sofa_time, sofa_score, respiration, coagulation, liver, cardiovascular,
cns, renal, sepsis3
