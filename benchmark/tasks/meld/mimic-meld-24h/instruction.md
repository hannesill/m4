# Task: Calculate MELD Score

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the MELD-Na (Model for End-Stage Liver Disease with sodium
adjustment) score for each ICU stay using data from the first 24 hours
of ICU admission (Kamath et al., Hepatology, 2001; Kim et al., NEJM, 2008).

MELD uses logarithmic transformations of 3 lab values (creatinine,
bilirubin, INR) plus a conditional sodium adjustment:

- All lab values are floored at 1.0 before taking the natural log
- Creatinine is capped at 4.0 mg/dL for patients on dialysis or with
  creatinine > 4.0
- The initial MELD score is capped at 40
- The sodium adjustment is only applied when the initial MELD > 11
- Sodium is bounded to the range 125-137 mEq/L for scoring

The MELD score ranges from approximately 6 to 40.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, meld

One row per ICU stay.
