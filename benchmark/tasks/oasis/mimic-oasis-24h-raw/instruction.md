# Task: Calculate OASIS Score (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested OASIS calculation.

Calculate the Oxford Acute Severity of Illness Score (OASIS) for each
ICU stay using data from the first 24 hours of ICU admission
(Johnson et al., Critical Care Medicine, 2013).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, oasis, preiculos_score, age_score, gcs_score,
heart_rate_score, mbp_score, resp_rate_score, temp_score, urineoutput_score,
mechvent_score, electivesurgery_score

One row per ICU stay. The `oasis` column is the sum of the 10 component scores.
