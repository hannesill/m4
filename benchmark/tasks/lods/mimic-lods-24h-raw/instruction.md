# Task: Calculate LODS Score (Raw Tables)

Only base tables are available — there are no pre-computed derived tables.

Calculate the Logistic Organ Dysfunction Score (LODS) for each ICU stay
using data from the first 24 hours of ICU admission
(Le Gall et al., JAMA, 1996).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, lods, neurologic, cardiovascular, renal,
pulmonary, hematologic, hepatic

One row per ICU stay. The `lods` column is the sum of the six component scores.
