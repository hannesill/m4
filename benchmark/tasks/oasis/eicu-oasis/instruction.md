# Task: Calculate OASIS Score (eICU)

Calculate the Oxford Acute Severity of Illness Score (OASIS) for each
ICU stay using data from the first 24 hours of ICU admission
(Johnson et al., Critical Care Medicine, 2013).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, oasis, preiculos_score, age_score, gcs_score,
heart_rate_score, mbp_score, resp_rate_score, temp_score, urineoutput_score,
mechvent_score, electivesurgery_score

One row per ICU stay. The `oasis` column is the sum of the 10 component scores.
