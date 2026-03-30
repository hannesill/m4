# Task: Estimate Baseline Creatinine

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Estimate the baseline (pre-illness) serum creatinine for each hospital
admission. The baseline creatinine is determined hierarchically:

1. **If the lowest admission creatinine <= 1.1 mg/dL**: Use the observed
   minimum value (assumed to represent normal kidney function)
2. **If the patient has a CKD diagnosis**: Use the lowest admission value
   (even if elevated, it represents their chronic baseline)
3. **Otherwise**: Estimate baseline using the MDRD equation assuming
   eGFR = 75 mL/min/1.73m²

### MDRD Estimation Formula

Back-calculate creatinine from assumed eGFR = 75:

- **Male**: `scr = (75 / 186 / age^(-0.203))^(-1/1.154)`
- **Female**: `scr = (75 / 186 / age^(-0.203) / 0.742)^(-1/1.154)`

### CKD Identification

CKD is identified from ICD diagnosis codes:
- **ICD-9**: codes starting with '585'
- **ICD-10**: codes starting with 'N18'

### Requirements

- **Adults only**: Filter to patients with age >= 18
- **Minimum creatinine**: Use the minimum creatinine value across the entire
  hospital admission (from `mimiciv_derived.chemistry`)
- **Age and gender**: From `mimiciv_derived.age` and `mimiciv_hosp.patients`

Output a CSV file to `{output_path}` with these exact columns:
hadm_id, gender, age, scr_min, ckd, mdrd_est, scr_baseline

One row per hospital admission. The `ckd` column is 1 if CKD diagnosis
present, 0 otherwise. The `scr_baseline` column contains the final baseline
determination following the hierarchical rules above.
