# Task: Identify Suspicion of Infection (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested suspicion-of-infection calculation.
You must identify systemic antibiotics from the raw prescriptions table.

Identify suspected infection events by pairing systemic antibiotic
administration with culture collection within defined time windows,
following the operationalization from Seymour et al. (JAMA, 2016).

`ab_id` = ROW_NUMBER per subject, ordered by starttime, stoptime,
antibiotic name.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, stay_id, hadm_id, ab_id, antibiotic, antibiotic_time, suspected_infection, suspected_infection_time, culture_time, specimen, positive_culture

One row per antibiotic prescription. The `suspected_infection` column is 1 if
the antibiotic-culture pairing criteria are met, 0 otherwise.
