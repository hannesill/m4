# Task: Identify Sepsis-3 Patients (Raw Tables)

Only the pre-computed tables for SOFA, suspected infection, and
Sepsis-3 are unavailable. Other intermediate derived tables may
still be present. You must derive the missing concepts yourself.

Identify patients meeting the Sepsis-3 criteria: SOFA score >= 2
coinciding with suspected infection within a defined time window
(Singer et al., JAMA, 2016; Seymour et al., JAMA, 2016).

The SOFA measurement time must fall within 48 hours before to
24 hours after the suspected infection time.

Each ICU stay may have multiple matching events. Return only the first,
using ROW_NUMBER ordered by:
1. `suspected_infection_time` (NULLS FIRST)
2. `antibiotic_time` (NULLS FIRST)
3. `culture_time` (NULLS FIRST)
4. SOFA measurement time (NULLS FIRST)

`sepsis3` = TRUE when sofa_score >= 2 AND suspected_infection = 1.
`sofa_time` is the SOFA measurement endtime.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, stay_id, antibiotic_time, culture_time, suspected_infection_time,
sofa_time, sofa_score, respiration, coagulation, liver, cardiovascular,
cns, renal, sepsis3
