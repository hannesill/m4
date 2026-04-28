# Task: Calculate APS III (APACHE III) Score (Raw Tables)

All derived shortcut tables have been removed from the task database.
You must derive the requested concept from source clinical tables.

Calculate the Acute Physiology Score III (APS III) for each ICU stay
using the worst values from the first 24 hours of ICU admission
(Knaus et al., Chest, 1991).

Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, apsiii, hr_score, mbp_score, temp_score,
resp_rate_score, pao2_aado2_score, hematocrit_score, wbc_score,
creatinine_score, uo_score, bun_score, sodium_score, albumin_score,
bilirubin_score, glucose_score, acidbase_score, gcs_score

One row per ICU stay. The `apsiii` column is the sum of the 16
component scores.
