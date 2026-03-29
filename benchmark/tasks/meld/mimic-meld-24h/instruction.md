# Task: Calculate MELD Score

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the MELD-Na (Model for End-Stage Liver Disease with sodium
adjustment) score for each ICU stay using data from the first 24 hours
of ICU admission.

MELD uses logarithmic transformations of 3 lab values plus a conditional
sodium adjustment:

1. **Component scores** (all values floored at 1.0 before taking ln):
   - Creatinine: `0.957 × ln(Cr)` — cap creatinine at 4.0 if on dialysis or Cr > 4
   - Bilirubin: `0.378 × ln(Bili)`
   - INR: `1.120 × ln(INR) + 0.643`

2. **MELD Initial** = `round(Cr_score + Bili_score + INR_score, 1) × 10`
   - Cap at 40 if component sum > 4

3. **Sodium adjustment** (only if MELD Initial > 11):
   - Na score = `137 - Na` (Na bounded to 125-137)
   - `MELD = MELD_Initial + 1.32 × Na_score - 0.033 × MELD_Initial × Na_score`

The MELD score ranges from approximately 6 to 40.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, meld

One row per ICU stay.
