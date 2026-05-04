# Task: Estimate Baseline Creatinine

Estimate the baseline (pre-illness) serum creatinine for each hospital
admission, following the KDIGO AKI Clinical Practice Guideline (2012).
Use the MDRD equation without the race coefficient, consistent with
current race-free eGFR practice. Adults only (age >= 18).

Output a CSV file to `{output_path}` with these exact columns:
hadm_id, gender, age, scr_min, ckd, mdrd_est, scr_baseline

One row per hospital admission. The `ckd` column is 1 if CKD diagnosis
present, 0 otherwise. The `scr_baseline` column contains the final
baseline determination.
