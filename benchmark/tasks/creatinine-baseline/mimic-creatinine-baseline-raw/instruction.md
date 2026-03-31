# Task: Estimate Baseline Creatinine (Raw Tables)

Only base tables are available — there are no pre-computed derived tables.

Estimate the baseline (pre-illness) serum creatinine for each hospital
admission, following the approach in Siew et al. (CJASN, 2012).
Adults only (age >= 18).

Output a CSV file to `{output_path}` with these exact columns:
hadm_id, gender, age, scr_min, ckd, mdrd_est, scr_baseline

One row per hospital admission. The `ckd` column is 1 if CKD diagnosis
present, 0 otherwise. The `scr_baseline` column contains the final
baseline determination.
