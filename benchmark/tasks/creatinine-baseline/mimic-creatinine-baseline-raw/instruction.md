# Task: Estimate Baseline Creatinine (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.
There are no pre-computed intermediate or derived tables.

Estimate the baseline (pre-illness) serum creatinine for each hospital
admission using a hierarchical approach:

1. **If the lowest admission creatinine <= 1.1 mg/dL**: Use the observed
   minimum value (assumed to represent normal kidney function)
2. **If the patient has a CKD diagnosis** (identified from ICD codes):
   Use the lowest admission value (even if elevated, it represents their
   chronic baseline)
3. **Otherwise**: Estimate baseline using the MDRD equation, back-calculating
   creatinine from an assumed eGFR of 75 mL/min/1.73m²

### Requirements

- **Adults only**: Filter to patients with age >= 18
- **Minimum creatinine**: Use the minimum creatinine value across the
  entire hospital admission from `labevents`
- Gender and age are needed for the MDRD estimation

Output a CSV file to `{output_path}` with these exact columns:
hadm_id, gender, age, scr_min, ckd, mdrd_est, scr_baseline

One row per hospital admission. The `ckd` column is 1 if CKD diagnosis
present, 0 otherwise. The `scr_baseline` column contains the final baseline
determination following the hierarchical rules above.
