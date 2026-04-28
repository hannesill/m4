# Task: Identify Suspicion of Infection (Raw Tables)

All derived shortcut tables have been removed from the task database.
You must derive the requested concept from source clinical tables.
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
