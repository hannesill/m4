# Task: Calculate SIRS Criteria (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested SIRS calculation.

Calculate the Systemic Inflammatory Response Syndrome (SIRS) criteria
for each ICU stay using data from the first 24 hours (from 6 hours
before ICU admission to 24 hours after admission)
(Bone et al., Chest, 1992).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sirs, temp_score, heart_rate_score, resp_score, wbc_score

One row per ICU stay. The `sirs` column is the sum of the four component scores.
