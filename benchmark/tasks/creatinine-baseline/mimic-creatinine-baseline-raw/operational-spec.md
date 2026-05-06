# Operational Spec: Baseline Creatinine

## Output Contract

Return one row per hospital admission. The key is `hadm_id`.

Required columns, in order:
`hadm_id, gender, age, scr_min, ckd, mdrd_est, scr_baseline`.

Include adults only, with age at least 18 years.

## Inputs and Units

Use serum creatinine values in mg/dL. `scr_min` is the lowest serum creatinine
measured during the hospital admission. `ckd` is 1 when a chronic kidney disease
diagnosis is present for the admission and 0 otherwise. Chronic kidney disease
is identified by standard CKD diagnosis codes, including ICD-9 code family 585
and ICD-10 code family N18.

## MDRD Back-Calculation

When baseline creatinine must be estimated, use the race-free MDRD equation
back-calculated from an assumed eGFR of 75 mL/min/1.73 m2.

For male patients:
`mdrd_est = (75 / 186 / age^(-0.203))^(-1 / 1.154)`

For female patients:
`mdrd_est = (75 / 186 / age^(-0.203) / 0.742)^(-1 / 1.154)`

Do not apply a race coefficient.

## Baseline Hierarchy

Determine `scr_baseline` using this hierarchy:

1. If `scr_min <= 1.1`, set `scr_baseline = scr_min`.
2. Otherwise, if `ckd = 1`, set `scr_baseline = scr_min`.
3. Otherwise, set `scr_baseline = mdrd_est`.

## Missingness and Rounding

If no admission creatinine is available, `scr_min` and `scr_baseline` are null.
If age or gender is missing when MDRD estimation is needed, `mdrd_est` and
`scr_baseline` are null unless the hierarchy selected `scr_min`. Numeric
comparisons are tolerant to small rounding differences of about 0.01.
