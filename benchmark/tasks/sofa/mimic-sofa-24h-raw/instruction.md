# Task: Calculate SOFA Score (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested SOFA calculation.

Calculate the Sequential Organ Failure Assessment (SOFA) score for each
ICU stay using data from the first 24 hours (from 6 hours before ICU
admission to 24 hours after admission)
(Vincent et al., Intensive Care Medicine, 1996).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sofa, respiration, coagulation, liver, cardiovascular, cns, renal

One row per ICU stay. The `sofa` column is the sum of the six component scores.
