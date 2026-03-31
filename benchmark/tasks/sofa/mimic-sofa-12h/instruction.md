# Task: Calculate SOFA Score (12-Hour)

Calculate the Sequential Organ Failure Assessment (SOFA) score for each
ICU stay using data from the first 12 hours (from 6 hours before ICU
admission to 12 hours after admission)
(Vincent et al., Intensive Care Medicine, 1996).

The renal component uses creatinine only (no urine output) because
12 hours is insufficient for daily UO criteria. Treat missing data
as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sofa, respiration, coagulation, liver, cardiovascular, cns, renal

One row per ICU stay. The `sofa` column is the sum of the six component scores.
