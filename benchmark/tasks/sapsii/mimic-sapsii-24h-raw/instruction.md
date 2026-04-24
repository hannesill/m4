# Task: Calculate SAPS-II Score (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested SAPS-II calculation.

Calculate the Simplified Acute Physiology Score II (SAPS-II) for each
ICU stay using the worst values from the first 24 hours of ICU admission
(Le Gall et al., JAMA, 1993).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sapsii, age_score, hr_score, sysbp_score,
temp_score, pao2fio2_score, uo_score, bun_score, wbc_score, potassium_score,
sodium_score, bicarbonate_score, bilirubin_score, gcs_score, comorbidity_score,
admissiontype_score

One row per ICU stay. The `sapsii` column is the sum of the 15 component scores.
